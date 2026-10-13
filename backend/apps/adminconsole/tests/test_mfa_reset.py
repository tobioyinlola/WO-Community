import pyotp
import pytest
from django.utils import timezone

from apps.accounts import mfa
from apps.accounts.models import MfaDevice, RecoveryCode, RefreshTokenFamily
from apps.accounts.tests.helpers import AJAX, LOGIN_URL, PASSWORD, REFRESH_URL
from apps.audit.models import AuditLog
from apps.core import crypto

pytestmark = pytest.mark.django_db

MEMBERS = "/api/v1/admin/members"


@pytest.fixture
def boss(make_user):
    return make_user(roles=("super_admin",), email="boss@example.com")


@pytest.fixture
def locked_out(make_user):
    """A community admin who lost their authenticator."""
    user = make_user(
        roles=("community_admin",), email="lost@example.com", email_verified_at=timezone.now()
    )
    MfaDevice.objects.create(
        user=user,
        secret_encrypted=crypto.encrypt(pyotp.random_base32()),
        confirmed_at=timezone.now(),
    )
    mfa._issue_recovery_codes(user)
    return user


def reset_url(user):
    return f"{MEMBERS}/{user.pk}/reset-mfa"


def test_super_admin_can_reset_an_admins_mfa(boss, locked_out, client_for, api_client):
    login_before = api_client.post(LOGIN_URL, {"email": "lost@example.com", "password": PASSWORD})
    assert login_before.status_code == 202

    response = client_for(boss, mfa_age=5).post(reset_url(locked_out))
    assert response.status_code == 200
    assert not MfaDevice.objects.filter(user=locked_out).exists()
    assert not RecoveryCode.objects.filter(user=locked_out).exists()
    entry = AuditLog.objects.get(action="mfa.reset")
    assert entry.actor_id == boss.pk
    assert entry.target_id == str(locked_out.pk)

    login_after = api_client.post(LOGIN_URL, {"email": "lost@example.com", "password": PASSWORD})
    assert login_after.status_code == 200
    assert login_after.json()["mfa_enrolment_required"] is True


def test_reset_ends_the_admins_existing_sessions(boss, locked_out, client_for, api_client):
    from apps.accounts import sessions

    raw, _ = sessions.start(locked_out, user_agent="t", ip="1.2.3.4")
    client_for(boss, mfa_age=5).post(reset_url(locked_out))
    api_client.cookies["wo_refresh"] = raw
    assert api_client.post(REFRESH_URL, **AJAX).status_code == 401
    assert RefreshTokenFamily.objects.filter(revoked_at__isnull=True).count() == 0


def test_community_admins_cannot_reset_mfa(make_user, locked_out, client_for):
    other = make_user(roles=("community_admin",), email="other@example.com")
    response = client_for(other, mfa_age=5).post(reset_url(locked_out))
    assert response.status_code == 403
    assert MfaDevice.objects.filter(user=locked_out).exists()


def test_reset_needs_a_recent_mfa_check(boss, locked_out, client_for):
    response = client_for(boss, mfa_age=3600).post(reset_url(locked_out))
    assert response.status_code == 403
    assert response.json()["code"] == "step_up_required"
    assert MfaDevice.objects.filter(user=locked_out).exists()


def test_reset_needs_an_mfa_session(boss, locked_out, client_for):
    response = client_for(boss).post(reset_url(locked_out))
    assert response.json()["code"] == "mfa_required"


def test_reset_is_refused_for_anonymous_callers_and_members(
    locked_out, api_client, client_for, make_user
):
    assert api_client.post(reset_url(locked_out)).status_code == 401
    member = make_user(email="m@example.com")
    assert client_for(member, mfa_age=5).post(reset_url(locked_out)).status_code == 403


def test_nobody_can_reset_their_own_mfa(boss, client_for):
    MfaDevice.objects.create(
        user=boss, secret_encrypted=crypto.encrypt("JBSWY3DPEHPK3PXP"), confirmed_at=timezone.now()
    )
    assert client_for(boss, mfa_age=5).post(reset_url(boss)).status_code == 403
    assert MfaDevice.objects.filter(user=boss).exists()


def test_reset_of_someone_without_mfa_is_a_conflict(boss, make_user, client_for):
    plain = make_user(roles=("community_admin",), email="plain@example.com")
    response = client_for(boss, mfa_age=5).post(reset_url(plain))
    assert response.status_code == 409
    assert response.json()["code"] == "mfa_not_enrolled"


def test_reset_of_an_unknown_member_is_404(boss, client_for):
    missing = f"{MEMBERS}/00000000-0000-0000-0000-000000000000/reset-mfa"
    assert client_for(boss, mfa_age=5).post(missing).status_code == 404
