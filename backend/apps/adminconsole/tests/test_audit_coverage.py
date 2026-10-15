# ruff: noqa: F811
"""Each sensitive action leaves exactly one audit entry, with the right actor and target."""

import pytest
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.jobs.tests.conftest import post_job, poster, poster_client, set_board  # noqa: F401
from apps.profiles import services as profiles

pytestmark = pytest.mark.django_db

ADMIN = "/api/v1/admin"


@pytest.fixture
def boss(make_user):
    return make_user(
        roles=("super_admin",),
        email="boss@example.com",
        approved_at=timezone.now(),
        email_verified_at=timezone.now(),
    )


@pytest.fixture
def boss_client(boss, client_for):
    return client_for(boss, mfa_age=5)


def entries(action):
    return list(AuditLog.objects.filter(action=action))


def test_inviting_writes_one_entry_per_send_and_a_batch_entry(boss_client, boss):
    boss_client.post(
        f"{ADMIN}/invitations/batch",
        {"emails": ["a@example.com", "b@example.com"], "idempotency_key": "k"},
        format="json",
    )
    assert len(entries("invitation.created")) == 2
    [batch] = entries("invitation.batch_sent")
    assert batch.actor_id == boss.pk and batch.after["sent"] == 2


def test_approving_and_suspending_a_member(boss_client, boss, make_user):
    pending = make_user(email="p@example.com", status="pending", email_verified_at=timezone.now())
    profiles.set_linkedin(user_id=pending.pk, url="https://www.linkedin.com/in/someone")
    boss_client.post(f"{ADMIN}/members/{pending.pk}/approve")
    [approved] = entries("member.approve")
    assert approved.actor_id == boss.pk and approved.target_id == str(pending.pk)
    boss_client.post(f"{ADMIN}/members/{pending.pk}/suspend", {"reason": "spam"}, format="json")
    [suspended] = entries("member.suspend")
    assert suspended.reason == "spam"


def test_a_job_is_audited_when_posted_approved_and_rejected(
    poster, poster_client, boss_client, boss
):
    set_board(require_approval=True)
    job = post_job(poster_client).json()
    [created] = entries("jobs.created")
    assert created.actor_id == poster.pk and created.target_id == job["id"]
    assert created.target_label == "Backend Engineer"
    boss_client.post(f"{ADMIN}/jobs/{job['id']}/approve")
    [approved] = entries("jobs.approve")
    assert approved.actor_id == boss.pk
    assert len(entries("jobs.created")) == 1


def test_changing_the_board_settings_is_audited(boss_client, boss):
    boss_client.put(
        f"{ADMIN}/jobs/settings",
        {"require_approval": False, "default_duration_days": 45},
        format="json",
    )
    [entry] = entries("settings.jobs_changed")
    assert entry.actor_id == boss.pk
    assert (
        entry.before["default_duration_days"] == 30 and entry.after["default_duration_days"] == 45
    )
