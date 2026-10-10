import pyotp
import pytest
from django.conf import settings
from django.utils import timezone

from apps.accounts import sessions
from apps.accounts.models import ConsentRecord, MfaDevice, SocialIdentity, User
from apps.accounts.tests.helpers import (
    AJAX,
    LOGIN_URL,
    MFA_VERIFY_URL,
    PASSWORD,
    REFRESH_URL,
    registration_payload,
    totp_code,
)
from apps.analytics.models import AnalyticsEvent
from apps.audit.models import AuditLog
from apps.core import crypto
from apps.core.identity import IdentityProviderUnavailable

pytestmark = pytest.mark.django_db

URL = "/api/v1/auth/google"
EMAIL = "ada@example.com"


def token(subject="g-1", email=EMAIL, verified=True, name="Ada Founder"):
    return f"fake|{subject}|{email}|{'1' if verified else '0'}|{name}"


def registration(**overrides):
    base = registration_payload()
    body = {
        "accepted_terms": True,
        "accepted_privacy": True,
        "accepted_conduct": True,
        "profile": base["profile"],
        "startup": base["startup"],
    }
    body.update(overrides)
    return body


def sign_in(client, **body):
    return client.post(URL, {"id_token": token(), **body})


# --- existing members ---


def test_a_member_with_this_address_is_signed_in_and_linked(api_client, make_user):
    member = make_user(email=EMAIL, email_verified_at=timezone.now())
    response = sign_in(api_client)
    assert response.status_code == 200
    body = response.json()
    assert body["user"]["id"] == str(member.pk) and body["access_token"]
    assert settings.REFRESH_COOKIE_NAME in response.cookies
    assert response["Cache-Control"] == "no-store"
    assert SocialIdentity.objects.get().user_id == member.pk
    assert AuditLog.objects.filter(action="auth.google_linked").count() == 1
    assert AuditLog.objects.filter(action="auth.login", after={"method": "google"}).count() == 1


def test_linking_keeps_the_password_of_a_member_whose_address_was_confirmed(api_client, make_user):
    member = make_user(email=EMAIL, email_verified_at=timezone.now())
    password_before = member.password
    sign_in(api_client)
    member.refresh_from_db()
    assert member.password == password_before
    assert api_client.post(LOGIN_URL, {"email": EMAIL, "password": PASSWORD}).status_code == 200


def test_the_session_works_like_any_other(api_client, make_user):
    make_user(email=EMAIL, email_verified_at=timezone.now())
    access = sign_in(api_client).json()["access_token"]
    assert api_client.get("/api/v1/me", HTTP_AUTHORIZATION=f"Bearer {access}").status_code == 200
    assert api_client.post(REFRESH_URL, **AJAX).status_code == 200


def test_the_google_login_is_recognised_even_if_the_address_differs_later(api_client, make_user):
    member = make_user(email=EMAIL, email_verified_at=timezone.now())
    sign_in(api_client)
    other = api_client.post(URL, {"id_token": token(email="renamed@example.com")})
    assert other.status_code == 200
    assert other.json()["user"]["id"] == str(member.pk)
    assert SocialIdentity.objects.count() == 1


def test_the_address_match_ignores_case(api_client, make_user):
    member = make_user(email=EMAIL, email_verified_at=timezone.now())
    response = api_client.post(URL, {"id_token": token(email="ADA@Example.com")})
    assert response.json()["user"]["id"] == str(member.pk)


def test_linking_to_an_unconfirmed_account_discards_the_squatters_password(api_client, make_user):
    """Someone registered this address without proving they own it."""
    squatter = make_user(email=EMAIL, email_verified_at=None, status="pending")
    stale = api_client.post(LOGIN_URL, {"email": EMAIL, "password": PASSWORD})
    assert stale.status_code == 403  # unconfirmed accounts cannot log in with a password
    session = sessions.start(squatter, user_agent="ua", ip="203.0.113.5")[1]
    response = sign_in(api_client)
    assert response.status_code == 200
    squatter.refresh_from_db()
    assert squatter.email_verified_at is not None
    assert not squatter.has_usable_password()
    assert api_client.post(LOGIN_URL, {"email": EMAIL, "password": PASSWORD}).status_code == 401
    session.refresh_from_db()
    assert session.revoked_at is not None  # whatever the squatter held is ended


@pytest.mark.parametrize("status", ["suspended", "removed", "rejected"])
def test_an_account_that_may_not_log_in_cannot_use_google_either(api_client, make_user, status):
    make_user(email=EMAIL, email_verified_at=timezone.now(), status=status)
    response = sign_in(api_client)
    assert response.status_code == 401
    assert response.json()["code"] == "invalid_credentials"
    assert SocialIdentity.objects.count() == 0
    assert settings.REFRESH_COOKIE_NAME not in response.cookies


def test_a_suspended_member_with_a_linked_google_login_is_still_refused(api_client, make_user):
    member = make_user(email=EMAIL, email_verified_at=timezone.now())
    sign_in(api_client)
    User.objects.filter(pk=member.pk).update(status="suspended")
    assert sign_in(api_client).status_code == 401


def test_accounts_with_a_second_factor_still_have_to_provide_it(api_client, make_user):
    member = make_user(email=EMAIL, email_verified_at=timezone.now())
    secret = pyotp.random_base32()
    MfaDevice.objects.create(
        user=member, secret_encrypted=crypto.encrypt(secret), confirmed_at=timezone.now()
    )
    response = sign_in(api_client)
    assert response.status_code == 202
    assert "access_token" not in response.json()
    assert settings.REFRESH_COOKIE_NAME not in response.cookies
    done = api_client.post(
        MFA_VERIFY_URL, {"mfa_token": response.json()["mfa_token"], "code": totp_code(secret)}
    )
    assert done.status_code == 200 and done.json()["access_token"]


# --- tokens that must be refused ---


def test_a_token_google_would_not_have_issued_is_refused(api_client):
    for bad in ("", "garbage", "fake|only|three|parts", "fake||x@example.com|1|"):
        response = api_client.post(URL, {"id_token": bad or "x"})
        assert response.status_code == 401, bad
        assert response.json()["code"] == "invalid_google_token"
    assert User.objects.count() == 0


def test_an_unconfirmed_google_address_is_refused_before_anything_is_touched(api_client, make_user):
    make_user(email=EMAIL, email_verified_at=timezone.now())
    response = api_client.post(URL, {"id_token": token(verified=False)})
    assert response.status_code == 403
    assert response.json()["code"] == "google_email_unverified"
    assert SocialIdentity.objects.count() == 0


def test_the_feature_is_off_until_a_client_id_is_configured(api_client, settings):
    settings.GOOGLE_CLIENT_ID = ""
    response = sign_in(api_client)
    assert response.status_code == 404
    assert response.json()["code"] == "google_sign_in_disabled"


def test_an_outage_at_google_is_reported_as_unavailable(api_client, monkeypatch):
    def down(self, id_token, *, nonce=""):
        raise IdentityProviderUnavailable()

    monkeypatch.setattr("apps.integrations.identity.fake.FakeGoogleVerifier.verify", down)
    response = sign_in(api_client)
    assert response.status_code == 503
    assert response.json()["code"] == "google_unavailable"


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"id_token": ""},
        {"id_token": "x" * 4097},
        {"id_token": "x", "extra": 1},
        {"id_token": "x", "registration": {"accepted_terms": True}},
    ],
)
def test_malformed_requests_are_refused(api_client, body):
    assert api_client.post(URL, body).status_code == 400


def test_only_post_is_allowed(api_client):
    assert api_client.get(URL).status_code == 405


def test_attempts_are_rate_limited(api_client, monkeypatch):
    from rest_framework.throttling import ScopedRateThrottle

    monkeypatch.setattr(
        ScopedRateThrottle,
        "THROTTLE_RATES",
        {**ScopedRateThrottle.THROTTLE_RATES, "auth_google": "2/min"},
    )
    statuses = [api_client.post(URL, {"id_token": "bad"}).status_code for _ in range(3)]
    assert statuses == [401, 401, 429]


# --- new people ---


def test_a_new_person_is_told_what_is_still_needed_and_nothing_is_created(api_client):
    response = sign_in(api_client)
    assert response.status_code == 409
    body = response.json()
    assert (body["code"], body["email"], body["name"]) == (
        "registration_required",
        EMAIL,
        "Ada Founder",
    )
    assert User.objects.count() == 0 and SocialIdentity.objects.count() == 0


def test_a_new_person_becomes_a_pending_member_who_is_signed_in(
    api_client, run_outbox, sent_emails
):
    response = sign_in(api_client, registration=registration())
    assert response.status_code == 201
    user = User.objects.get(email=EMAIL)
    assert response.json()["user"] == {"id": str(user.pk), "email": EMAIL, "status": "pending"}
    assert user.email_verified_at is not None
    assert not user.has_usable_password()
    assert SocialIdentity.objects.get().user_id == user.pk
    assert ConsentRecord.objects.filter(user=user, granted=True).count() == 3
    run_outbox()
    assert sent_emails == []  # nothing to confirm: Google already did
    assert AuditLog.objects.filter(action="auth.registered", after={"method": "google"}).exists()
    assert AnalyticsEvent.objects.filter(name="email_verified", actor_id=user.pk).exists()


def test_signing_in_again_afterwards_is_an_ordinary_login(api_client):
    sign_in(api_client, registration=registration())
    again = sign_in(api_client)
    assert again.status_code == 200
    assert User.objects.count() == 1


@pytest.mark.parametrize("field", ["accepted_terms", "accepted_privacy", "accepted_conduct"])
def test_a_new_person_must_accept_the_agreements(api_client, field):
    response = sign_in(api_client, registration=registration(**{field: False}))
    assert response.status_code == 400
    assert User.objects.count() == 0


def test_a_new_person_must_give_valid_sign_up_details(api_client):
    bad = registration_payload()["startup"] | {"sector": "not-a-sector"}
    assert sign_in(api_client, registration=registration(startup=bad)).status_code == 400


def test_a_visitor_id_joins_the_funnel(api_client):
    import uuid

    from apps.analytics.models import IdentityLink

    anon = uuid.uuid4()
    sign_in(api_client, registration=registration(anonymous_id=str(anon)))
    assert IdentityLink.objects.get().anonymous_id == anon


def test_a_valid_invitation_approves_the_account_at_once(api_client, make_user):
    import hashlib

    from apps.accounts import services

    admin = make_user(roles=("community_admin",), email="admin@example.com")
    services.create_invitation(actor=admin, email=EMAIL, role="mentor")
    from apps.accounts.models import Invitation

    Invitation.objects.update(token_hash=hashlib.sha256(b"known").hexdigest())
    response = sign_in(api_client, registration=registration(invitation_token="known"))
    assert response.status_code == 201
    user = User.objects.get(email=EMAIL)
    assert response.json()["user"]["status"] == "active"
    assert user.approval_source == "invitation"
    assert set(user.user_roles.values_list("role", flat=True)) == {"member", "mentor"}
    assert Invitation.objects.get().status == "registered"


def test_an_invitation_for_another_address_gives_no_shortcut(api_client, make_user):
    import hashlib

    from apps.accounts import services
    from apps.accounts.models import Invitation

    admin = make_user(roles=("community_admin",), email="admin@example.com")
    services.create_invitation(actor=admin, email="someone.else@example.com", role="member")
    Invitation.objects.update(token_hash=hashlib.sha256(b"known").hexdigest())
    response = sign_in(api_client, registration=registration(invitation_token="known"))
    assert response.status_code == 201
    assert response.json()["user"]["status"] == "pending"
    assert Invitation.objects.get().status != "registered"


def test_a_pending_google_member_has_no_admin_access(api_client):
    access = sign_in(api_client, registration=registration()).json()["access_token"]
    auth = {"HTTP_AUTHORIZATION": f"Bearer {access}"}
    assert api_client.get("/api/v1/me", **auth).status_code == 200
    assert api_client.get("/api/v1/admin/members", **auth).status_code == 403
