from datetime import timedelta

import pytest
from django.utils import timezone

from apps.toolkit.jobs import services
from apps.toolkit.jobs.models import AIJob
from apps.toolkit.testing import BASE

pytestmark = pytest.mark.django_db


@pytest.fixture
def kinds():
    """Registers throwaway kinds and removes them afterwards."""
    before = dict(services._handlers)
    yield services.register
    services._handlers.clear()
    services._handlers.update(before)


def start(member, kind, **kwargs):
    job, _ = services.start(owner_id=member.pk, kind=kind, **kwargs)
    return job


def test_a_job_runs_reports_progress_and_keeps_its_result(member, kinds):
    seen = []

    def handler(ctx):
        ctx.progress(30, "Reading")
        seen.append(AIJob.objects.get(pk=ctx.job.pk).step_label)
        return {"type": "thing", "id": "abc"}

    kinds("test.ok", handler)
    job = start(member, "test.ok")
    assert job.status == "queued"
    services.run(job.pk)
    job.refresh_from_db()
    assert seen == ["Reading"]
    assert (job.status, job.progress, job.result_ref) == (
        "succeeded",
        100,
        {"type": "thing", "id": "abc"},
    )
    assert job.started_at and job.finished_at and job.attempts == 1


def test_a_repeated_key_is_the_same_job(member, kinds):
    kinds("test.ok", lambda ctx: {})
    first, created = services.start(owner_id=member.pk, kind="test.ok", idempotency_key="k1")
    again, created_again = services.start(owner_id=member.pk, kind="test.ok", idempotency_key="k1")
    assert created and not created_again and first.pk == again.pk
    other, _ = services.start(owner_id=member.pk, kind="test.ok", idempotency_key="k2")
    assert other.pk != first.pk
    assert AIJob.objects.count() == 2


def test_the_same_key_from_two_members_is_two_jobs(member, other, kinds):
    kinds("test.ok", lambda ctx: {})
    a, _ = services.start(owner_id=member.pk, kind="test.ok", idempotency_key="k")
    b, _ = services.start(owner_id=other.pk, kind="test.ok", idempotency_key="k")
    assert a.pk != b.pk


def test_a_job_runs_only_once(member, kinds):
    calls = []
    kinds("test.once", lambda ctx: calls.append(1) or {})
    job = start(member, "test.once")
    services.run(job.pk)
    services.run(job.pk)
    assert len(calls) == 1


def test_a_known_failure_shows_its_safe_message(member, kinds):
    def handler(ctx):
        raise services.JobFailed("not_enough_data", "Add your problem statement first.")

    kinds("test.fails", handler)
    job = start(member, "test.fails")
    services.run(job.pk)
    job.refresh_from_db()
    assert (job.status, job.error_code) == ("failed", "not_enough_data")
    assert job.error_detail == "Add your problem statement first."


def test_a_crash_never_leaks_its_details(member, kinds):
    def handler(ctx):
        raise RuntimeError("secret internal detail with a key=abc123")

    kinds("test.crash", handler)
    job = start(member, "test.crash")
    services.run(job.pk)
    job.refresh_from_db()
    assert job.status == "failed" and job.error_code == "internal_error"
    assert "abc123" not in job.error_detail and "secret" not in job.error_detail


def test_a_temporary_problem_is_retried_and_then_given_up(member, kinds):
    def handler(ctx):
        raise services.TransientError("provider busy")

    kinds("test.busy", handler)
    job = start(member, "test.busy")
    with pytest.raises(services.TransientError):
        services.run(job.pk, final_attempt=False)
    job.refresh_from_db()
    assert job.status == "queued"  # back in line for the retry
    services.run(job.pk, final_attempt=True)
    job.refresh_from_db()
    assert (job.status, job.error_code) == ("failed", "temporarily_unavailable")


def test_cancelling_a_queued_job_is_immediate(member, kinds):
    kinds("test.ok", lambda ctx: {})
    job = start(member, "test.ok")
    assert services.cancel(job).status == "cancelled"
    services.run(job.pk)  # nothing happens
    job.refresh_from_db()
    assert job.status == "cancelled" and job.attempts == 0


def test_cancelling_a_running_job_stops_it_at_the_next_step(member, kinds):
    def handler(ctx):
        ctx.progress(10, "Step one")
        services.cancel(AIJob.objects.get(pk=ctx.job.pk))  # the member presses stop
        ctx.progress(50, "Step two")  # raises
        return {"type": "never"}

    kinds("test.stoppable", handler)
    job = start(member, "test.stoppable")
    services.run(job.pk)
    job.refresh_from_db()
    assert job.status == "cancelled" and job.result_ref == {}


def test_an_unknown_kind_is_refused(member):
    from rest_framework.exceptions import ValidationError

    with pytest.raises(ValidationError):
        services.start(owner_id=member.pk, kind="nope")


def test_abandoned_jobs_are_failed(member, kinds):
    kinds("test.ok", lambda ctx: {})
    job = start(member, "test.ok")
    AIJob.objects.filter(pk=job.pk).update(
        status="running", updated_at=timezone.now() - timedelta(hours=2)
    )
    assert services.reap_stuck() == 1
    job.refresh_from_db()
    assert (job.status, job.error_code) == ("failed", "timed_out")


def test_a_hook_hears_when_a_job_ends(member, kinds):
    ended = []
    services.on_finish(lambda job: ended.append((job.kind, job.status)))
    kinds("test.hooked", lambda ctx: {})
    job = start(member, "test.hooked")
    services.run(job.pk)
    assert ended[-1] == ("test.hooked", "succeeded")
    services._on_finish.clear()


# --- the API ---


def test_polling_costs_nothing_when_nothing_changed(client, member, kinds):
    kinds("test.ok", lambda ctx: {"type": "x"})
    job = start(member, "test.ok")
    first = client.get(f"{BASE}/jobs/{job.pk}")
    assert first.status_code == 200 and first.json()["status"] == "queued"
    tag = first["ETag"]
    assert client.get(f"{BASE}/jobs/{job.pk}", HTTP_IF_NONE_MATCH=tag).status_code == 304
    services.run(job.pk)
    after = client.get(f"{BASE}/jobs/{job.pk}", HTTP_IF_NONE_MATCH=tag)
    assert after.status_code == 200 and after.json()["status"] == "succeeded"
    assert after.json()["result"] == {"type": "x"}


def test_jobs_belong_to_their_owner(client, other_client, member, kinds):
    kinds("test.ok", lambda ctx: {})
    job = start(member, "test.ok")
    assert other_client.get(f"{BASE}/jobs/{job.pk}").status_code == 404
    assert other_client.post(f"{BASE}/jobs/{job.pk}/cancel").status_code == 404
    cancelled = client.post(f"{BASE}/jobs/{job.pk}/cancel")
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"


def test_jobs_need_a_login(api_client):
    assert api_client.get(f"{BASE}/jobs/00000000-0000-0000-0000-000000000000").status_code == 401
