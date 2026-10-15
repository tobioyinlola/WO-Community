"""After an admin enters their authenticator code, that browser skips the code for a day."""

import pytest
from django.conf import settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import MfaDevice
from apps.accounts.tests.test_mfa_login import (
    claims_of,
    enrolled,  # noqa: F401 - a fixture
    full_login,
    password_step,
)
from apps.audit.models import AuditLog

pytestmark = pytest.mark.django_db

TRUST = settings.MFA_TRUST_COOKIE_NAME
MEMBERS = "/api/v1/admin/members"


def test_entering_the_code_remembers_the_browser_for_a_day(api_client, enrolled):  # noqa: F811
    _, secret, _ = enrolled
    response = full_login(api_client, secret)
    cookie = response.cookies[TRUST]
    assert cookie["httponly"] and cookie["max-age"] == settings.MFA_REMEMBER_SECONDS
    assert cookie["path"] == settings.REFRESH_COOKIE_PATH


def test_the_next_sign_in_from_that_browser_needs_only_the_password(
    api_client, enrolled  # noqa: F811
):
    user, secret, _ = enrolled
    first = full_login(api_client, secret)
    first_at = claims_of(first.json()["access_token"])["mfa_at"]
    again = password_step(api_client, remembered=True)
    assert again.status_code == 200
    token = again.json()["access_token"]
    # The session keeps the time the code was entered, so the day is not stretched.
    assert claims_of(token)["mfa_at"] == pytest.approx(first_at, abs=1)
    admin = api_client.get(MEMBERS, HTTP_AUTHORIZATION=f"Bearer {token}")
    assert admin.status_code == 200
    assert AuditLog.objects.filter(
        actor_id=user.pk, action="auth.login", after__mfa="remembered_browser"
    ).exists()


def test_another_browser_still_gets_the_code(api_client, enrolled):  # noqa: F811
    _, secret, _ = enrolled
    full_login(api_client, secret)
    assert password_step(APIClient()).status_code == 202


def test_after_a_day_the_code_is_asked_again(api_client, enrolled, settings):  # noqa: F811
    _, secret, _ = enrolled
    full_login(api_client, secret)
    settings.MFA_REMEMBER_SECONDS = 0  # the day is up
    assert password_step(api_client, remembered=True).status_code == 202


def test_a_new_authenticator_or_password_ends_the_remembered_browser(
    api_client, enrolled  # noqa: F811
):
    user, secret, _ = enrolled
    full_login(api_client, secret)
    user.bump_token_version()  # what a password reset or "sign out everywhere" does
    assert password_step(api_client, remembered=True).status_code == 202

    full_login(api_client, secret)
    device = MfaDevice.objects.get(user=user)
    MfaDevice.objects.filter(pk=device.pk).delete()
    MfaDevice.objects.create(
        user=user, secret_encrypted=device.secret_encrypted, confirmed_at=timezone.now()
    )
    assert password_step(api_client, remembered=True).status_code == 202


def test_a_forged_cookie_is_ignored(api_client, enrolled):  # noqa: F811
    api_client.cookies[TRUST] = "not-a-real-note"
    assert password_step(api_client, remembered=True).status_code == 202


def test_another_accounts_cookie_does_not_carry_over(api_client, enrolled, make_user):  # noqa: F811
    from apps.accounts.tests.helpers import PASSWORD

    _, secret, _ = enrolled
    full_login(api_client, secret)
    other = make_user(
        roles=("community_admin",), email="other@example.com", email_verified_at=timezone.now()
    )
    MfaDevice.objects.create(
        user=other,
        secret_encrypted=MfaDevice.objects.first().secret_encrypted,
        confirmed_at=timezone.now(),
    )
    response = api_client.post(
        "/api/v1/auth/login", {"email": "other@example.com", "password": PASSWORD}
    )
    assert response.status_code == 202
