from datetime import timedelta

import pytest
from django.conf import settings
from django.utils import timezone

from apps.accounts.models import EmailToken, RefreshTokenFamily, User
from apps.accounts.tests.helpers import (
    AJAX,
    FORGOT_URL,
    LOGIN_URL,
    PASSWORD,
    REFRESH_URL,
    RESET_URL,
)

pytestmark = pytest.mark.django_db

COOKIE = settings.REFRESH_COOKIE_NAME
NEW_PASSWORD = "a-brand-new-passphrase"


@pytest.fixture
def member(make_user):
    return make_user(email="member@example.com", email_verified_at=timezone.now())


def request_reset(client, run_outbox, email="member@example.com"):
    response = client.post(FORGOT_URL, {"email": email})
    run_outbox()
    return response


def test_reset_flow_changes_the_password(api_client, member, run_outbox, last_token, sent_emails):
    assert request_reset(api_client, run_outbox).status_code == 202
    assert "reset-password?token=" in sent_emails[-1].text_body
    response = api_client.post(RESET_URL, {"token": last_token(), "password": NEW_PASSWORD})
    assert response.status_code == 200
    member.refresh_from_db()
    assert member.check_password(NEW_PASSWORD)
    assert not member.check_password(PASSWORD)
    old = api_client.post(LOGIN_URL, {"email": "member@example.com", "password": PASSWORD})
    new = api_client.post(LOGIN_URL, {"email": "member@example.com", "password": NEW_PASSWORD})
    assert (old.status_code, new.status_code) == (401, 200)


def test_unknown_and_known_addresses_get_the_same_response(
    api_client, member, run_outbox, sent_emails
):
    known = request_reset(api_client, run_outbox)
    sent_emails.clear()
    unknown = request_reset(api_client, run_outbox, email="nobody@example.com")
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    assert sent_emails == []


def test_reset_requests_are_limited_per_address(api_client, member, run_outbox, sent_emails):
    for _ in range(settings.PASSWORD_RESET_MAX_PER_EMAIL_PER_HOUR + 2):
        assert request_reset(api_client, run_outbox).status_code == 202
    assert len(sent_emails) == settings.PASSWORD_RESET_MAX_PER_EMAIL_PER_HOUR


def test_reset_token_is_single_use(api_client, member, run_outbox, last_token):
    request_reset(api_client, run_outbox)
    token = last_token()
    assert api_client.post(RESET_URL, {"token": token, "password": NEW_PASSWORD}).status_code == 200
    again = api_client.post(RESET_URL, {"token": token, "password": "yet-another-passphrase"})
    assert again.status_code == 400


def test_expired_reset_token_is_rejected(api_client, member, run_outbox, last_token):
    request_reset(api_client, run_outbox)
    EmailToken.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
    response = api_client.post(RESET_URL, {"token": last_token(), "password": NEW_PASSWORD})
    assert response.status_code == 400


def test_new_password_must_meet_the_rules(api_client, member, run_outbox, last_token):
    request_reset(api_client, run_outbox)
    response = api_client.post(RESET_URL, {"token": last_token(), "password": "short"})
    assert response.status_code == 400
    assert "password" in response.json()["errors"]


def test_reset_revokes_every_session_and_access_token(api_client, member, run_outbox, last_token):
    login = api_client.post(LOGIN_URL, {"email": "member@example.com", "password": PASSWORD})
    access = login.json()["access_token"]
    refresh = login.cookies[COOKIE].value
    request_reset(api_client, run_outbox)
    api_client.post(RESET_URL, {"token": last_token(), "password": NEW_PASSWORD})

    assert RefreshTokenFamily.objects.filter(revoked_at__isnull=True).count() == 0
    api_client.cookies[COOKIE] = refresh
    assert api_client.post(REFRESH_URL, **AJAX).status_code == 401
    assert api_client.get("/api/v1/me", HTTP_AUTHORIZATION=f"Bearer {access}").status_code == 401


def test_other_outstanding_reset_links_die_when_one_is_used(
    api_client, member, run_outbox, last_token
):
    request_reset(api_client, run_outbox)
    first = last_token()
    request_reset(api_client, run_outbox)
    second = last_token()
    api_client.post(RESET_URL, {"token": second, "password": NEW_PASSWORD})
    response = api_client.post(RESET_URL, {"token": first, "password": "yet-another-passphrase"})
    assert response.status_code == 400


def test_reset_marks_the_email_as_verified(api_client, make_user, run_outbox, last_token):
    user = make_user(email="unverified@example.com")
    request_reset(api_client, run_outbox, email="unverified@example.com")
    api_client.post(RESET_URL, {"token": last_token(), "password": NEW_PASSWORD})
    user.refresh_from_db()
    assert user.email_verified_at is not None


def test_suspended_account_gets_no_reset_email(api_client, make_user, run_outbox, sent_emails):
    make_user(email="s@example.com", status="suspended")
    request_reset(api_client, run_outbox, email="s@example.com")
    assert sent_emails == []


# --- sessions ---

SESSIONS = "/api/v1/me/sessions"


def test_user_can_list_only_their_own_active_sessions(api_client, member, make_user, client_for):
    other = make_user(email="other@example.com", email_verified_at=timezone.now())
    api_client.post(LOGIN_URL, {"email": "member@example.com", "password": PASSWORD})
    api_client.post(
        LOGIN_URL,
        {"email": "other@example.com", "password": PASSWORD},
        HTTP_USER_AGENT="OtherBrowser",
    )
    response = client_for(member).get(SESSIONS)
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert "OtherBrowser" not in response.content.decode()
    assert RefreshTokenFamily.objects.filter(user=other).count() == 1


def test_sessions_require_authentication(api_client):
    assert api_client.get(SESSIONS).status_code == 401


def test_user_can_revoke_a_session_and_it_stops_refreshing(api_client, member, client_for):
    cookie = (
        api_client.post(LOGIN_URL, {"email": "member@example.com", "password": PASSWORD})
        .cookies[COOKIE]
        .value
    )
    session_id = client_for(member).get(SESSIONS).json()[0]["id"]
    assert client_for(member).delete(f"{SESSIONS}/{session_id}").status_code == 204
    api_client.cookies[COOKIE] = cookie
    assert api_client.post(REFRESH_URL, **AJAX).status_code == 401
    assert client_for(member).get(SESSIONS).json() == []


def test_user_cannot_revoke_someone_elses_session(api_client, member, make_user, client_for):
    other = make_user(email="other@example.com", email_verified_at=timezone.now())
    api_client.post(LOGIN_URL, {"email": "other@example.com", "password": PASSWORD})
    session = RefreshTokenFamily.objects.get(user=other)
    response = client_for(member).delete(f"{SESSIONS}/{session.pk}")
    assert response.status_code == 404
    session.refresh_from_db()
    assert session.revoked_at is None


def test_revoking_requires_authentication(api_client, member):
    api_client.post(LOGIN_URL, {"email": "member@example.com", "password": PASSWORD})
    session = RefreshTokenFamily.objects.get()
    assert api_client.delete(f"{SESSIONS}/{session.pk}").status_code == 401


def test_user_count_is_unchanged_by_reset_requests(api_client, member, run_outbox):
    request_reset(api_client, run_outbox, email="nobody@example.com")
    assert User.objects.count() == 1


def test_breached_password_is_rejected_at_reset(api_client, member, run_outbox, last_token):
    request_reset(api_client, run_outbox)
    response = api_client.post(RESET_URL, {"token": last_token(), "password": "Password123!456"})
    assert response.status_code == 400
    member.refresh_from_db()
    assert member.check_password(PASSWORD)
