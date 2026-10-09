from datetime import timedelta

import jwt
import pyotp
import pytest
from django.conf import settings
from django.utils import timezone

from apps.accounts import mfa
from apps.accounts.models import MfaDevice, RecoveryCode, RefreshTokenFamily
from apps.accounts.tests.helpers import (
    AJAX,
    LOGIN_URL,
    MFA_RECOVERY_URL,
    MFA_STEP_UP_URL,
    MFA_VERIFY_URL,
    PASSWORD,
    REFRESH_URL,
    totp_code,
)
from apps.audit.models import AuditLog
from apps.core import crypto

pytestmark = pytest.mark.django_db

COOKIE = settings.REFRESH_COOKIE_NAME
MEMBERS = "/api/v1/admin/members"


def claims_of(token):
    return jwt.decode(
        token, settings.JWT_PUBLIC_KEY, algorithms=["EdDSA"], issuer=settings.JWT_ISSUER
    )


@pytest.fixture
def enrolled(make_user):
    """A community admin with MFA switched on: (user, secret, recovery_codes)."""
    user = make_user(
        roles=("community_admin",), email="admin@example.com", email_verified_at=timezone.now()
    )
    secret = pyotp.random_base32()
    MfaDevice.objects.create(
        user=user, secret_encrypted=crypto.encrypt(secret), confirmed_at=timezone.now()
    )
    return user, secret, mfa._issue_recovery_codes(user)


def password_step(client, email="admin@example.com"):
    return client.post(LOGIN_URL, {"email": email, "password": PASSWORD})


def finish(client, token, code):
    return client.post(MFA_VERIFY_URL, {"mfa_token": token, "code": code})


def full_login(client, secret, offset=0):
    token = password_step(client).json()["mfa_token"]
    return finish(client, token, totp_code(secret, offset))


# --- the two step login ---------------------------------------------------------------


def test_password_step_returns_a_challenge_and_no_session(api_client, enrolled):
    response = password_step(api_client)
    assert response.status_code == 202
    body = response.json()
    assert body["mfa_required"] is True
    assert body["mfa_token"]
    assert "access_token" not in body
    assert COOKIE not in response.cookies
    assert response["Cache-Control"] == "no-store"
    assert RefreshTokenFamily.objects.count() == 0


def test_correct_code_completes_login_with_an_mfa_verified_session(api_client, enrolled):
    _, secret, _ = enrolled
    response = full_login(api_client, secret)
    assert response.status_code == 200
    assert response.cookies[COOKIE]["httponly"]
    claims = claims_of(response.json()["access_token"])
    assert abs(claims["mfa_at"] - timezone.now().timestamp()) < 10
    assert claims["sid"] == str(RefreshTokenFamily.objects.get().pk)
    assert response.json()["mfa_enrolment_required"] is False
    entry = AuditLog.objects.get(action="auth.login")
    assert entry.after == {"mfa": "totp"}


def test_admin_endpoints_work_after_the_second_step(api_client, enrolled):
    _, secret, _ = enrolled
    token = full_login(api_client, secret).json()["access_token"]
    assert api_client.get(MEMBERS, HTTP_AUTHORIZATION=f"Bearer {token}").status_code == 200


def test_wrong_code_is_refused_and_creates_no_session(api_client, enrolled):
    _, secret, _ = enrolled
    token = password_step(api_client).json()["mfa_token"]
    wrong = "000000" if totp_code(secret) != "000000" else "111111"
    response = finish(api_client, token, wrong)
    assert response.status_code == 400
    assert "code" in response.json()["errors"]
    assert RefreshTokenFamily.objects.count() == 0


def test_the_challenge_survives_a_typo(api_client, enrolled):
    _, secret, _ = enrolled
    token = password_step(api_client).json()["mfa_token"]
    wrong = "000000" if totp_code(secret) != "000000" else "111111"
    finish(api_client, token, wrong)
    assert finish(api_client, token, totp_code(secret)).status_code == 200


def test_a_spent_code_cannot_be_replayed_on_a_new_login(api_client, enrolled):
    _, secret, _ = enrolled
    code = totp_code(secret)
    first = finish(api_client, password_step(api_client).json()["mfa_token"], code)
    assert first.status_code == 200
    second = finish(api_client, password_step(api_client).json()["mfa_token"], code)
    assert second.status_code == 400


def test_an_earlier_time_step_is_refused_once_a_later_one_was_used(api_client, enrolled):
    _, secret, _ = enrolled
    assert full_login(api_client, secret, offset=1).status_code == 200
    assert full_login(api_client, secret, offset=0).status_code == 400


def test_a_challenge_can_only_be_redeemed_once(api_client, enrolled):
    _, secret, _ = enrolled
    token = password_step(api_client).json()["mfa_token"]
    assert finish(api_client, token, totp_code(secret)).status_code == 200
    again = finish(api_client, token, totp_code(secret, offset=1))
    assert again.status_code == 401
    assert again.json()["code"] == "invalid_mfa_challenge"


@pytest.mark.parametrize("token", ["garbage", "a:b:c", ""])
def test_forged_challenges_are_refused(api_client, enrolled, token):
    response = finish(api_client, token or "x", "123456")
    assert response.status_code == 401


def test_a_tampered_challenge_is_refused(api_client, enrolled):
    token = password_step(api_client).json()["mfa_token"]
    forged = token[:-3] + ("aaa" if not token.endswith("aaa") else "bbb")
    assert finish(api_client, forged, "123456").status_code == 401


def test_an_expired_challenge_is_refused(api_client, enrolled, settings):
    _, secret, _ = enrolled
    token = password_step(api_client).json()["mfa_token"]
    settings.MFA_CHALLENGE_TTL_SECONDS = -1
    assert finish(api_client, token, totp_code(secret)).status_code == 401


def test_challenge_is_void_if_the_account_is_suspended_meanwhile(api_client, enrolled):
    user, secret, _ = enrolled
    token = password_step(api_client).json()["mfa_token"]
    user.status = "suspended"
    user.save()
    assert finish(api_client, token, totp_code(secret)).status_code == 401


def test_repeated_wrong_codes_lock_the_account_out_of_code_checks(api_client, enrolled):
    _, secret, _ = enrolled
    token = password_step(api_client).json()["mfa_token"]
    wrong = "000000" if totp_code(secret) != "000000" else "111111"
    for _ in range(settings.MFA_MAX_FAILURES):
        assert finish(api_client, token, wrong).status_code == 400
    locked = finish(api_client, token, totp_code(secret))
    assert locked.status_code == 429
    assert RefreshTokenFamily.objects.count() == 0


def test_wrong_password_never_reaches_the_challenge(api_client, enrolled):
    response = api_client.post(
        LOGIN_URL, {"email": "admin@example.com", "password": "nope-nope-nope"}
    )
    assert response.status_code == 401
    assert "mfa_token" not in response.json()


# --- recovery codes -------------------------------------------------------------------


def test_a_recovery_code_logs_in_once(api_client, enrolled):
    _, _, codes = enrolled
    token = password_step(api_client).json()["mfa_token"]
    assert finish(api_client, token, codes[0]).status_code == 200
    assert AuditLog.objects.filter(action="mfa.recovery_used").exists()
    assert AuditLog.objects.get(action="auth.login").after == {"mfa": "recovery"}
    again = finish(api_client, password_step(api_client).json()["mfa_token"], codes[0])
    assert again.status_code == 400


def test_recovery_codes_ignore_case_and_dashes(api_client, enrolled):
    _, _, codes = enrolled
    token = password_step(api_client).json()["mfa_token"]
    assert finish(api_client, token, codes[1].replace("-", "").upper()).status_code == 200


def test_unknown_recovery_codes_fail(api_client, enrolled):
    token = password_step(api_client).json()["mfa_token"]
    assert finish(api_client, token, "abcdef-123456").status_code == 400


# --- admins without MFA ---------------------------------------------------------------


def test_admin_without_a_device_can_log_in_but_is_told_to_enrol(api_client, make_user):
    make_user(
        roles=("community_admin",), email="new.admin@example.com", email_verified_at=timezone.now()
    )
    response = password_step(api_client, email="new.admin@example.com")
    assert response.status_code == 200
    body = response.json()
    assert body["mfa_enrolment_required"] is True
    claims = claims_of(body["access_token"])
    assert "mfa_at" not in claims
    denied = api_client.get(MEMBERS, HTTP_AUTHORIZATION=f"Bearer {body['access_token']}")
    assert denied.status_code == 403
    assert denied.json()["code"] == "mfa_required"


def test_ordinary_members_are_never_asked_to_enrol(api_client, make_user):
    make_user(email="member@example.com", email_verified_at=timezone.now())
    assert (
        password_step(api_client, email="member@example.com").json()["mfa_enrolment_required"]
        is False
    )


# --- the session keeps its MFA state ---------------------------------------------------


def test_refresh_keeps_the_mfa_claim(api_client, enrolled):
    _, secret, _ = enrolled
    login = full_login(api_client, secret)
    api_client.cookies[COOKIE] = login.cookies[COOKIE].value
    refreshed = api_client.post(REFRESH_URL, **AJAX)
    assert refreshed.status_code == 200
    first, second = (claims_of(r.json()["access_token"]) for r in (login, refreshed))
    assert second["mfa_at"] == first["mfa_at"]
    assert second["sid"] == first["sid"]
    token = refreshed.json()["access_token"]
    assert api_client.get(MEMBERS, HTTP_AUTHORIZATION=f"Bearer {token}").status_code == 200


def test_refreshing_does_not_make_an_old_mfa_check_look_new(api_client, enrolled):
    _, secret, _ = enrolled
    login = full_login(api_client, secret)
    RefreshTokenFamily.objects.update(mfa_verified_at=timezone.now() - timedelta(hours=13))
    api_client.cookies[COOKIE] = login.cookies[COOKIE].value
    token = api_client.post(REFRESH_URL, **AJAX).json()["access_token"]
    response = api_client.get(MEMBERS, HTTP_AUTHORIZATION=f"Bearer {token}")
    assert response.status_code == 403
    assert response.json()["code"] == "mfa_required"


def stale_session(api_client, secret):
    """Log in, then age the session's MFA check to 20 minutes and refresh."""
    login = full_login(api_client, secret)
    RefreshTokenFamily.objects.update(mfa_verified_at=timezone.now() - timedelta(minutes=20))
    api_client.cookies[COOKIE] = login.cookies[COOKIE].value
    return api_client.post(REFRESH_URL, **AJAX).json()["access_token"]


def test_step_up_refreshes_the_check_for_destructive_actions(api_client, enrolled, make_user):
    _, secret, _ = enrolled
    target = make_user(email="target@example.com")
    stale = stale_session(api_client, secret)
    suspend = f"{MEMBERS}/{target.pk}/suspend"

    blocked = api_client.post(suspend, {"reason": "x"}, HTTP_AUTHORIZATION=f"Bearer {stale}")
    assert blocked.status_code == 403
    assert blocked.json()["code"] == "step_up_required"

    stepped = api_client.post(
        MFA_STEP_UP_URL, {"code": totp_code(secret, offset=1)}, HTTP_AUTHORIZATION=f"Bearer {stale}"
    )
    assert stepped.status_code == 200
    fresh = stepped.json()["access_token"]
    assert claims_of(fresh)["mfa_at"] > claims_of(stale)["mfa_at"]
    assert AuditLog.objects.filter(action="mfa.step_up").exists()

    done = api_client.post(suspend, {"reason": "x"}, HTTP_AUTHORIZATION=f"Bearer {fresh}")
    assert done.status_code == 200


def test_step_up_persists_across_a_refresh(api_client, enrolled):
    _, secret, _ = enrolled
    stale = stale_session(api_client, secret)
    api_client.post(
        MFA_STEP_UP_URL, {"code": totp_code(secret, offset=1)}, HTTP_AUTHORIZATION=f"Bearer {stale}"
    )
    family = RefreshTokenFamily.objects.get()
    assert family.mfa_verified_at > timezone.now() - timedelta(minutes=1)


def test_step_up_with_a_wrong_code_changes_nothing(api_client, enrolled):
    _, secret, _ = enrolled
    stale = stale_session(api_client, secret)
    wrong = "000000" if totp_code(secret, 1) != "000000" else "111111"
    response = api_client.post(
        MFA_STEP_UP_URL, {"code": wrong}, HTTP_AUTHORIZATION=f"Bearer {stale}"
    )
    assert response.status_code == 400
    assert RefreshTokenFamily.objects.get().mfa_verified_at < timezone.now() - timedelta(minutes=15)


def test_step_up_needs_a_token_tied_to_a_session(enrolled, client_for):
    user, secret, _ = enrolled
    response = client_for(user, mfa_age=5).post(MFA_STEP_UP_URL, {"code": totp_code(secret)})
    assert response.status_code == 403


def test_step_up_cannot_touch_a_revoked_session(api_client, enrolled):
    _, secret, _ = enrolled
    stale = stale_session(api_client, secret)
    RefreshTokenFamily.objects.update(revoked_at=timezone.now())
    response = api_client.post(
        MFA_STEP_UP_URL, {"code": totp_code(secret, offset=1)}, HTTP_AUTHORIZATION=f"Bearer {stale}"
    )
    assert response.status_code == 403


# --- regenerating recovery codes ---------------------------------------------------------


def test_regenerating_replaces_every_recovery_code(api_client, enrolled):
    _, secret, old_codes = enrolled
    token = full_login(api_client, secret).json()["access_token"]
    response = api_client.post(
        MFA_RECOVERY_URL,
        {"code": totp_code(secret, offset=1)},
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )
    assert response.status_code == 200
    new_codes = response.json()["recovery_codes"]
    assert len(new_codes) == 10
    assert set(new_codes).isdisjoint(old_codes)
    assert RecoveryCode.objects.count() == 10
    attempt = finish(api_client, password_step(api_client).json()["mfa_token"], old_codes[0])
    assert attempt.status_code == 400
    ok = finish(api_client, password_step(api_client).json()["mfa_token"], new_codes[0])
    assert ok.status_code == 200


def test_a_recovery_code_cannot_authorise_regeneration(api_client, enrolled):
    _, secret, codes = enrolled
    token = full_login(api_client, secret).json()["access_token"]
    response = api_client.post(
        MFA_RECOVERY_URL, {"code": codes[0]}, HTTP_AUTHORIZATION=f"Bearer {token}"
    )
    assert response.status_code == 400
    assert RecoveryCode.objects.filter(used_at__isnull=True).count() == 10
