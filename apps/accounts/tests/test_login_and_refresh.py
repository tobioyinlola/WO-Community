from datetime import timedelta

import pytest
from django.conf import settings
from django.utils import timezone

from apps.accounts.models import RefreshTokenFamily, UserStatus
from apps.accounts.tests.helpers import (
    AJAX,
    LOGIN_URL,
    LOGOUT_URL,
    PASSWORD,
    REFRESH_URL,
)
from apps.audit.models import AuditLog

pytestmark = pytest.mark.django_db

COOKIE = settings.REFRESH_COOKIE_NAME


@pytest.fixture
def member(make_user):
    return make_user(email="member@example.com", email_verified_at=timezone.now())


def login(client, email="member@example.com", password=PASSWORD):
    return client.post(LOGIN_URL, {"email": email, "password": password})


def test_login_returns_access_token_and_sets_refresh_cookie(api_client, member):
    response = login(api_client)
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "Bearer"
    assert body["expires_in"] == 600
    assert body["user"]["email"] == "member@example.com"
    assert "refresh" not in str(body).lower()
    cookie = response.cookies[COOKIE]
    assert cookie["httponly"]
    assert cookie["samesite"] == "Lax"
    assert cookie["path"] == "/api/v1/auth/"
    assert response["Cache-Control"] == "no-store"


def test_access_token_from_login_authenticates_requests(api_client, member):
    token = login(api_client).json()["access_token"]
    response = api_client.get("/api/v1/me", HTTP_AUTHORIZATION=f"Bearer {token}")
    assert response.status_code == 200
    assert response.json()["email"] == "member@example.com"


def test_login_ignores_email_case(api_client, member):
    assert login(api_client, email="MEMBER@example.com").status_code == 200


def test_wrong_password_and_unknown_email_give_the_same_answer(api_client, member):
    wrong = login(api_client, password="wrong-password-123")
    unknown = login(api_client, email="nobody@example.com")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()
    assert wrong.json()["code"] == "invalid_credentials"
    assert COOKIE not in wrong.cookies


@pytest.mark.parametrize("status", [UserStatus.SUSPENDED, UserStatus.REMOVED])
def test_suspended_and_removed_accounts_cannot_log_in(api_client, make_user, status):
    make_user(email="gone@example.com", status=status, email_verified_at=timezone.now())
    response = login(api_client, email="gone@example.com")
    assert response.status_code == 401
    assert response.json()["code"] == "invalid_credentials"


def test_pending_verified_account_can_log_in_but_stays_pending(api_client, make_user):
    make_user(email="p@example.com", status=UserStatus.PENDING, email_verified_at=timezone.now())
    body = login(api_client, email="p@example.com").json()
    assert body["user"]["status"] == "pending"


def test_unverified_account_is_refused_with_a_clear_code(api_client, make_user):
    make_user(email="u@example.com")
    response = login(api_client, email="u@example.com")
    assert response.status_code == 403
    assert response.json()["code"] == "email_not_verified"


def test_account_locks_after_repeated_failures(api_client, member):
    for _ in range(settings.LOGIN_MAX_FAILURES_PER_ACCOUNT):
        assert login(api_client, password="wrong-password-123").status_code == 401
    locked = login(api_client)  # even the right password is refused while locked
    assert locked.status_code == 429
    assert locked.json()["code"] == "rate_limited"


def test_successful_login_clears_the_failure_count(api_client, member):
    for _ in range(settings.LOGIN_MAX_FAILURES_PER_ACCOUNT - 1):
        login(api_client, password="wrong-password-123")
    assert login(api_client).status_code == 200
    for _ in range(settings.LOGIN_MAX_FAILURES_PER_ACCOUNT - 1):
        login(api_client, password="wrong-password-123")
    assert login(api_client).status_code == 200


def test_one_address_cannot_lock_everyone_out_but_is_limited_itself(
    api_client, make_user, settings
):
    settings.LOGIN_MAX_FAILURES_PER_IP = 3
    make_user(email="victim@example.com", email_verified_at=timezone.now())
    for n in range(3):
        login(api_client, email=f"ghost{n}@example.com", password="wrong-password-123")
    assert login(api_client, email="victim@example.com").status_code == 429


def test_login_attempts_are_audited_without_raw_addresses(api_client, member):
    login(api_client, password="wrong-password-123")
    login(api_client)
    actions = list(AuditLog.objects.values_list("action", flat=True))
    assert "auth.login_failed" in actions
    assert "auth.login" in actions
    stored = str(list(AuditLog.objects.values("target_id", "ip_hash", "user_agent_hash")))
    assert "member@example.com" not in stored


# --- refresh -----------------------------------------------------------------------


def test_refresh_rotates_the_token_and_returns_a_new_access_token(api_client, member):
    first = login(api_client)
    old_cookie = first.cookies[COOKIE].value
    api_client.cookies[COOKIE] = old_cookie
    response = api_client.post(REFRESH_URL, **AJAX)
    assert response.status_code == 200
    assert response.json()["access_token"]
    assert response.cookies[COOKIE].value != old_cookie


def test_refresh_requires_the_custom_header(api_client, member):
    api_client.cookies[COOKIE] = login(api_client).cookies[COOKIE].value
    response = api_client.post(REFRESH_URL)
    assert response.status_code == 403


def test_refresh_without_a_cookie_is_unauthorised(api_client):
    response = api_client.post(REFRESH_URL, **AJAX)
    assert response.status_code == 401
    assert response.json()["code"] == "invalid_refresh_token"


def test_refresh_with_garbage_is_unauthorised(api_client):
    api_client.cookies[COOKIE] = "garbage"
    assert api_client.post(REFRESH_URL, **AJAX).status_code == 401
    api_client.cookies[COOKIE] = "00000000-0000-0000-0000-000000000000.abc"
    assert api_client.post(REFRESH_URL, **AJAX).status_code == 401


def test_reusing_an_old_refresh_token_revokes_the_whole_session(api_client, member):
    original = login(api_client).cookies[COOKIE].value
    api_client.cookies[COOKIE] = original
    rotated = api_client.post(REFRESH_URL, **AJAX).cookies[COOKIE].value

    api_client.cookies[COOKIE] = original  # an attacker replays the stolen token
    assert api_client.post(REFRESH_URL, **AJAX).status_code == 401

    api_client.cookies[COOKIE] = rotated  # the legitimate client is logged out too
    assert api_client.post(REFRESH_URL, **AJAX).status_code == 401
    family = RefreshTokenFamily.objects.get()
    assert family.revoked_reason == "reuse_detected"
    assert AuditLog.objects.filter(action="auth.refresh_reuse_detected").exists()


def test_refresh_fails_after_the_sliding_window(api_client, member):
    api_client.cookies[COOKIE] = login(api_client).cookies[COOKIE].value
    RefreshTokenFamily.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
    assert api_client.post(REFRESH_URL, **AJAX).status_code == 401


def test_sliding_window_never_extends_past_the_absolute_limit(api_client, member):
    api_client.cookies[COOKIE] = login(api_client).cookies[COOKIE].value
    limit = timezone.now() + timedelta(days=1)
    RefreshTokenFamily.objects.update(absolute_expires_at=limit)
    api_client.post(REFRESH_URL, **AJAX)
    assert RefreshTokenFamily.objects.get().expires_at <= limit


def test_refresh_is_refused_once_the_account_is_suspended(api_client, member):
    api_client.cookies[COOKIE] = login(api_client).cookies[COOKIE].value
    member.status = UserStatus.SUSPENDED
    member.save()
    assert api_client.post(REFRESH_URL, **AJAX).status_code == 401
    assert RefreshTokenFamily.objects.get().revoked_reason == "account_unavailable"


def test_logout_revokes_the_session_and_clears_the_cookie(api_client, member):
    cookie = login(api_client).cookies[COOKIE].value
    api_client.cookies[COOKIE] = cookie
    response = api_client.post(LOGOUT_URL, **AJAX)
    assert response.status_code == 204
    assert response.cookies[COOKIE]["max-age"] == 0
    api_client.cookies[COOKIE] = cookie
    assert api_client.post(REFRESH_URL, **AJAX).status_code == 401


def test_logout_requires_the_custom_header(api_client, member):
    api_client.cookies[COOKIE] = login(api_client).cookies[COOKIE].value
    assert api_client.post(LOGOUT_URL).status_code == 403


def test_refresh_tokens_are_stored_hashed(api_client, member):
    cookie = login(api_client).cookies[COOKIE].value
    secret = cookie.partition(".")[2]
    assert secret not in RefreshTokenFamily.objects.get().current_hash
    assert len(RefreshTokenFamily.objects.get().current_hash) == 64
