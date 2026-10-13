import pytest
from django.utils import timezone

from apps.audit import services as audit
from apps.audit.models import AuditLog
from apps.profiles.models import FounderProfile
from apps.profiles.services import get_or_create_profile

pytestmark = pytest.mark.django_db

BASE = "/api/v1/admin/members"


@pytest.fixture
def admin_client(make_user, client_for):
    return client_for(make_user(roles=("community_admin",)), mfa_age=5)


@pytest.fixture
def ada(make_user):
    user = make_user(
        email="ada@example.com", approved_at=timezone.now(), email_verified_at=timezone.now()
    )
    profile = get_or_create_profile(user.pk)
    FounderProfile.objects.filter(pk=profile.pk).update(full_name="Ada Okafor", city="Lagos")
    return user


def test_opening_a_member_returns_every_section(admin_client, ada):
    audit.record(actor=None, action="member.approve", target_type="user", target_id=ada.pk)
    body = admin_client.get(f"{BASE}/{ada.pk}").json()
    assert body["id"] == str(ada.pk) and body["name"] == "Ada Okafor"
    assert body["profile"]["city"] == "Lagos"
    assert body["account"] == {"invited_by": None, "referred_by": None, "approved_by": None}
    assert body["activity"] == {
        "posts": 0,
        "comments": 0,
        "events_attended": 0,
        "jobs_posted": 0,
    }
    assert body["learning"]["certificates"] == [] and body["mentorship"] is None
    assert body["open_tickets"] == []
    assert {a["action"] for a in body["audit"]} == {"member.approve", "members.viewed"}


def test_the_read_is_audited_and_the_audit_section_lists_entries_about_them(admin_client, ada):
    audit.record(actor=None, action="member.approve", target_type="user", target_id=ada.pk)
    admin_client.get(f"{BASE}/{ada.pk}")
    second = admin_client.get(f"{BASE}/{ada.pk}").json()
    actions = [a["action"] for a in second["audit"]]
    assert "member.approve" in actions and "members.viewed" in actions


def test_an_unknown_member_is_404(admin_client):
    assert admin_client.get(f"{BASE}/00000000-0000-0000-0000-000000000000").status_code == 404


def test_only_admins_with_the_permission_can_open_a_member(ada, make_user, client_for, api_client):
    assert api_client.get(f"{BASE}/{ada.pk}").status_code == 401
    assert client_for(make_user()).get(f"{BASE}/{ada.pk}").status_code == 403


def test_resending_verification_publishes_the_event_and_is_audited(
    admin_client, make_user, monkeypatch
):
    sent = []
    monkeypatch.setattr("apps.core.events.publish", lambda event: sent.append(event))
    unverified = make_user(email="new@example.com", email_verified_at=None)
    response = admin_client.post(f"{BASE}/{unverified.pk}/resend-verification")
    assert response.status_code == 204 and len(sent) == 1
    entry = AuditLog.objects.get(action="member.verification_resent")
    assert entry.target_id == str(unverified.pk) and entry.target_label == "new@example.com"


def test_resending_to_a_verified_member_is_refused(admin_client, ada):
    assert admin_client.post(f"{BASE}/{ada.pk}/resend-verification").status_code == 409


def test_resend_needs_the_permission(ada, make_user, client_for):
    assert client_for(make_user()).post(f"{BASE}/{ada.pk}/resend-verification").status_code == 403
