import jwt
import pytest
from django.conf import settings

from apps.accounts.models import MfaDevice, RecoveryCode
from apps.accounts.tests.helpers import (
    MFA_CONFIRM_URL,
    MFA_ENROL_URL,
    MFA_RECOVERY_URL,
    MFA_STEP_UP_URL,
    totp_code,
)
from apps.audit.models import AuditLog
from apps.core import crypto

pytestmark = pytest.mark.django_db

ADMIN_ONLY = [
    (MFA_ENROL_URL, None),
    (MFA_CONFIRM_URL, {"code": "123456"}),
    (MFA_STEP_UP_URL, {"code": "123456"}),
    (MFA_RECOVERY_URL, {"code": "123456"}),
]


def claims_of(token):
    return jwt.decode(
        token, settings.JWT_PUBLIC_KEY, algorithms=["EdDSA"], issuer=settings.JWT_ISSUER
    )


@pytest.fixture
def admin(make_user):
    return make_user(roles=("community_admin",), email="admin@example.com")


@pytest.fixture
def started(admin, client_for):
    """An admin who has begun enrolment: (client, secret)."""
    client = client_for(admin)
    secret = client.post(MFA_ENROL_URL).json()["secret"]
    return client, secret


@pytest.mark.parametrize(("url", "body"), ADMIN_ONLY)
def test_anonymous_callers_are_rejected(api_client, url, body):
    assert api_client.post(url, body).status_code == 401


@pytest.mark.parametrize(("url", "body"), ADMIN_ONLY)
def test_ordinary_members_cannot_use_admin_mfa(make_user, client_for, url, body):
    member = make_user(email="m@example.com")
    assert client_for(member).post(url, body).status_code == 403


def test_enrolment_returns_a_secret_and_provisioning_uri(admin, client_for):
    response = client_for(admin).post(MFA_ENROL_URL)
    assert response.status_code == 200
    body = response.json()
    assert body["otpauth_uri"].startswith("otpauth://totp/")
    assert (
        "admin%40example.com" in body["otpauth_uri"] or "admin@example.com" in body["otpauth_uri"]
    )
    assert "WO%20Community" in body["otpauth_uri"]
    assert body["secret"] in body["otpauth_uri"]
    assert response["Cache-Control"] == "no-store"


def test_secret_is_stored_encrypted(started):
    _, secret = started
    device = MfaDevice.objects.get()
    assert secret not in device.secret_encrypted
    assert crypto.decrypt(device.secret_encrypted) == secret
    assert device.confirmed_at is None


def test_restarting_enrolment_replaces_the_pending_secret(admin, client_for):
    client = client_for(admin)
    first = client.post(MFA_ENROL_URL).json()["secret"]
    second = client.post(MFA_ENROL_URL).json()["secret"]
    assert first != second
    assert MfaDevice.objects.count() == 1
    assert client.post(MFA_CONFIRM_URL, {"code": totp_code(first)}).status_code == 400


def test_confirming_without_starting_is_rejected(admin, client_for):
    response = client_for(admin).post(MFA_CONFIRM_URL, {"code": "123456"})
    assert response.status_code == 400
    assert "code" in response.json()["errors"]


def test_wrong_code_does_not_switch_mfa_on(started):
    client, secret = started
    wrong = "000000" if totp_code(secret) != "000000" else "111111"
    response = client.post(MFA_CONFIRM_URL, {"code": wrong})
    assert response.status_code == 400
    assert MfaDevice.objects.get().confirmed_at is None
    assert AuditLog.objects.filter(action="mfa.failed").exists()


def test_malformed_codes_are_rejected(started):
    client, _ = started
    for code in ["", "abc", "12345", "1234567"]:
        assert client.post(MFA_CONFIRM_URL, {"code": code}).status_code == 400


def test_unknown_fields_are_rejected(started):
    client, secret = started
    assert (
        client.post(MFA_CONFIRM_URL, {"code": totp_code(secret), "admin": True}).status_code == 400
    )


def test_confirming_returns_recovery_codes_and_an_mfa_verified_token(started):
    client, secret = started
    response = client.post(MFA_CONFIRM_URL, {"code": totp_code(secret)})
    assert response.status_code == 200
    body = response.json()
    assert len(body["recovery_codes"]) == 10
    assert len(set(body["recovery_codes"])) == 10
    assert all(len(c) == 13 and c[6] == "-" for c in body["recovery_codes"])
    assert response["Cache-Control"] == "no-store"
    assert MfaDevice.objects.get().confirmed_at is not None
    assert AuditLog.objects.filter(action="mfa.enrolled").exists()


def test_recovery_codes_are_stored_only_as_hashes(started):
    client, secret = started
    codes = client.post(MFA_CONFIRM_URL, {"code": totp_code(secret)}).json()["recovery_codes"]
    stored = " ".join(RecoveryCode.objects.values_list("code_hash", flat=True))
    assert RecoveryCode.objects.count() == 10
    for code in codes:
        assert code not in stored
        assert code.replace("-", "") not in stored


def test_a_session_token_becomes_mfa_verified_after_confirming(admin, client_for):
    # A token tied to a real session (as login issues) keeps the MFA check on refresh.
    from apps.accounts import sessions

    _, family = sessions.start(admin, user_agent="t", ip="1.2.3.4")
    from rest_framework.test import APIClient

    from apps.accounts import tokens

    client = APIClient()
    client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {tokens.issue_access_token(admin, session_id=family.pk)}"
    )
    secret = client.post(MFA_ENROL_URL).json()["secret"]
    token = client.post(MFA_CONFIRM_URL, {"code": totp_code(secret)}).json()["access_token"]
    claims = claims_of(token)
    assert claims["sid"] == str(family.pk)
    assert claims["mfa_at"] > 0
    family.refresh_from_db()
    assert family.mfa_verified_at is not None
    fresh = APIClient()  # the first client still holds the pre-MFA token
    response = fresh.get("/api/v1/admin/members", HTTP_AUTHORIZATION=f"Bearer {token}")
    assert response.status_code == 200


def test_cannot_enrol_again_once_confirmed(started):
    client, secret = started
    client.post(MFA_CONFIRM_URL, {"code": totp_code(secret)})
    response = client.post(MFA_ENROL_URL)
    assert response.status_code == 409
    assert response.json()["code"] == "mfa_already_enrolled"
    assert crypto.decrypt(MfaDevice.objects.get().secret_encrypted) == secret


def test_confirming_records_the_time_step_that_was_used(started):
    client, secret = started
    assert client.post(MFA_CONFIRM_URL, {"code": totp_code(secret)}).status_code == 200
    assert MfaDevice.objects.get().last_used_step > 0


def test_repeated_wrong_codes_lock_further_attempts(started):
    client, secret = started
    wrong = "000000" if totp_code(secret) != "000000" else "111111"
    for _ in range(settings.MFA_MAX_FAILURES):
        assert client.post(MFA_CONFIRM_URL, {"code": wrong}).status_code == 400
    locked = client.post(MFA_CONFIRM_URL, {"code": totp_code(secret)})
    assert locked.status_code == 429
    assert MfaDevice.objects.get().confirmed_at is None
