"""No member can crowd the others out, and the queue is observable."""

import pytest
from django.utils import timezone
from prometheus_client import REGISTRY
from rest_framework.exceptions import Throttled

from apps.core import metrics
from apps.toolkit.jobs import services as jobs
from apps.toolkit.jobs.models import AIJob

pytestmark = pytest.mark.django_db


def member(make_user, n):
    return make_user(
        email=f"m{n}@example.com", approved_at=timezone.now(), email_verified_at=timezone.now()
    )


def test_a_member_cannot_hold_more_than_a_few_jobs_at_once(make_user, settings):
    settings.TOOLKIT_MAX_ACTIVE_JOBS = 3
    busy, other = member(make_user, 1), member(make_user, 2)
    for _ in range(3):
        jobs.start(owner_id=busy.pk, kind="system.selfcheck")
    with pytest.raises(Throttled):
        jobs.start(owner_id=busy.pk, kind="system.selfcheck")
    # Somebody else is not affected by it.
    jobs.start(owner_id=other.pk, kind="system.selfcheck")
    # Asking again with a key that was already used returns that job rather than a refusal.
    first, created = jobs.start(owner_id=other.pk, kind="system.selfcheck", idempotency_key="a")
    again, created_again = jobs.start(
        owner_id=other.pk, kind="system.selfcheck", idempotency_key="a"
    )
    assert created and not created_again and first.pk == again.pk
    # A finished job frees a place.
    done = AIJob.objects.filter(owner_id=busy.pk).first()
    AIJob.objects.filter(pk=done.pk).update(status="succeeded")
    jobs.start(owner_id=busy.pk, kind="system.selfcheck")


def test_many_members_each_keeping_to_their_limit_all_get_their_jobs_done(make_user, settings):
    settings.TOOLKIT_MAX_ACTIVE_JOBS = 2
    members = [member(make_user, n) for n in range(20)]
    refused = 0
    for _round in range(3):  # every member keeps asking for more than their share
        for m in members:
            try:
                jobs.start(owner_id=m.pk, kind="system.selfcheck")
            except Throttled:
                refused += 1
    assert AIJob.objects.count() == 40 and refused == 20
    per_member = {m.pk: AIJob.objects.filter(owner=m).count() for m in members}
    assert set(per_member.values()) == {2}
    for job in AIJob.objects.order_by("created_at"):
        jobs.run(job.pk)
    assert AIJob.objects.filter(status="succeeded").count() == 40
    # Nobody is left waiting and everyone can start again.
    for m in members:
        jobs.start(owner_id=m.pk, kind="system.selfcheck")


def test_jobs_and_model_calls_are_counted_and_the_queue_is_scraped(make_user):
    def count(name, **labels):
        return REGISTRY.get_sample_value(name, labels) or 0

    before = count("wo_toolkit_jobs_total", kind="system.selfcheck", status="succeeded")
    runs_before = count("wo_toolkit_ai_runs_total", prompt="system.selfcheck", outcome="ok")
    m = member(make_user, 99)
    job, _ = jobs.start(owner_id=m.pk, kind="system.selfcheck")
    jobs.start(owner_id=m.pk, kind="system.selfcheck")
    jobs.run(job.pk)
    assert count("wo_toolkit_jobs_total", kind="system.selfcheck", status="succeeded") == before + 1
    assert (
        count("wo_toolkit_ai_runs_total", prompt="system.selfcheck", outcome="ok")
        == runs_before + 1
    )
    body = metrics.render().decode()
    assert "wo_toolkit_jobs_queued 1.0" in body
    assert "wo_toolkit_oldest_queued_seconds" in body
