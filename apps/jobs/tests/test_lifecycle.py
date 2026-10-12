from datetime import timedelta

import pytest
from django.utils import timezone

from apps.jobs import services
from apps.jobs.models import Job
from apps.jobs.tests.conftest import JOBS, post_job, set_board
from apps.notifications.models import Notification

pytestmark = pytest.mark.django_db


def act(client, job_id, action, body=None):
    return client.post(f"{JOBS}/{job_id}/{action}", body or {}, format="json")


def status_of(job_id):
    return Job.objects.get(pk=job_id).status


# --- closing and renewing ---


def test_the_poster_can_close_a_live_job(poster_client, reader_client, live_job):
    response = act(poster_client, live_job, "close")
    assert response.status_code == 200 and response.json()["status"] == "closed"
    assert reader_client.get(f"{JOBS}/{live_job}").status_code == 404
    assert Job.objects.get(pk=live_job).closed_at is not None


def test_a_pending_job_can_be_withdrawn(poster_client):
    created = post_job(poster_client).json()["id"]
    assert act(poster_client, created, "close").json()["status"] == "closed"


def test_a_job_that_is_already_closed_cannot_be_closed_again(poster_client, live_job):
    act(poster_client, live_job, "close")
    assert act(poster_client, live_job, "close").status_code == 409


def test_only_the_poster_can_close_or_renew(reader_client, live_job):
    assert act(reader_client, live_job, "close").status_code == 404
    assert act(reader_client, live_job, "renew").status_code == 404
    assert status_of(live_job) == "published"


def test_a_closed_job_can_be_renewed_and_is_announced_again(poster_client, reader_client, live_job):
    act(poster_client, live_job, "close")
    response = act(poster_client, live_job, "renew")
    assert response.status_code == 200 and response.json()["status"] == "published"
    assert reader_client.get(f"{JOBS}/{live_job}").status_code == 200
    assert Job.objects.get(pk=live_job).closed_at is None


def test_renewing_a_live_job_extends_its_term(poster_client, live_job):
    Job.objects.filter(pk=live_job).update(expires_at=timezone.now() + timedelta(days=1))
    renewed = act(poster_client, live_job, "renew").json()
    assert timezone.datetime.fromisoformat(renewed["expires_at"].replace("Z", "+00:00")) > (
        timezone.now() + timedelta(days=50)
    )


def test_renewing_with_a_new_deadline(poster_client, live_job):
    deadline = (timezone.now() + timedelta(days=20)).date()
    renewed = act(poster_client, live_job, "renew", {"deadline": deadline.isoformat()}).json()
    assert renewed["deadline"] == deadline.isoformat()
    assert renewed["expires_at"].startswith(deadline.isoformat())


def test_renewing_rejects_a_past_deadline(poster_client, live_job):
    assert act(poster_client, live_job, "renew", {"deadline": "2000-01-01"}).status_code == 400


@pytest.mark.parametrize("state", ["pending", "rejected", "removed"])
def test_jobs_that_never_went_live_or_were_removed_cannot_be_renewed(
    poster_client, live_job, state
):
    Job.objects.filter(pk=live_job).update(status=state)
    assert act(poster_client, live_job, "renew").status_code in (404, 409)
    assert status_of(live_job) == state


@pytest.mark.parametrize("state", ["closed", "expired", "rejected"])
def test_ended_jobs_cannot_be_edited_until_renewed(poster_client, live_job, state):
    etag = poster_client.get(f"{JOBS}/{live_job}")["ETag"]
    Job.objects.filter(pk=live_job).update(status=state)
    response = poster_client.patch(
        f"{JOBS}/{live_job}", {"title": "x"}, format="json", HTTP_IF_MATCH=etag
    )
    assert response.status_code == 409


# --- the expiry sweep ---


def test_jobs_past_their_expiry_are_expired_and_others_are_left_alone(
    auto_publish, poster_client, reader_client
):
    due = post_job(poster_client, title="Due").json()["id"]
    later = post_job(poster_client, title="Later").json()["id"]
    Job.objects.filter(pk=due).update(expires_at=timezone.now() - timedelta(minutes=1))
    assert services.expire_due() == 1
    assert status_of(due) == "expired" and status_of(later) == "published"
    assert Job.objects.get(pk=due).closed_at is not None
    assert services.expire_due() == 0


def test_an_expired_job_can_be_renewed_by_its_poster(poster_client, live_job):
    Job.objects.filter(pk=live_job).update(expires_at=timezone.now() - timedelta(minutes=1))
    services.expire_due()
    assert act(poster_client, live_job, "renew").json()["status"] == "published"


def test_the_expiry_task_is_scheduled():
    from django.conf import settings

    assert settings.CELERY_BEAT_SCHEDULE["jobs-expire"]["task"] == "jobs.expire_due"


# --- the three day warning ---


def notices(user):
    return list(Notification.objects.filter(user=user, type="job_expiring"))


def test_posters_are_warned_once_three_days_before(
    poster, poster_client, live_job, run_outbox, sent_emails
):
    Job.objects.filter(pk=live_job).update(expires_at=timezone.now() + timedelta(days=2, hours=12))
    assert services.warn_expiring() == 1
    run_outbox()
    [notice] = notices(poster)
    assert notice.payload["job_id"] == live_job
    assert (
        "expires in 3 days"
        in poster_client.get("/api/v1/notifications").json()["results"][0]["title"]
    )
    assert any("Renew or close" in m.subject or "renew or close" in m.subject for m in sent_emails)
    assert services.warn_expiring() == 0  # only once per term
    run_outbox()
    assert len(notices(poster)) == 1


def test_jobs_with_more_time_are_not_warned(poster, live_job, run_outbox):
    assert services.warn_expiring() == 0
    run_outbox()
    assert notices(poster) == []


def test_a_renewed_job_can_be_warned_again(poster, poster_client, live_job, run_outbox):
    Job.objects.filter(pk=live_job).update(expires_at=timezone.now() + timedelta(days=2))
    services.warn_expiring()
    act(poster_client, live_job, "renew")
    assert Job.objects.get(pk=live_job).expiry_warned_at is None
    Job.objects.filter(pk=live_job).update(expires_at=timezone.now() + timedelta(days=2))
    assert services.warn_expiring() == 1


def test_a_job_closed_before_the_notice_is_sent_is_not_announced(
    poster, poster_client, live_job, run_outbox
):
    Job.objects.filter(pk=live_job).update(expires_at=timezone.now() + timedelta(days=2))
    services.warn_expiring()
    act(poster_client, live_job, "close")
    run_outbox()
    assert notices(poster) == []


def test_a_warning_can_be_switched_off_in_preferences(poster, poster_client, live_job, run_outbox):
    poster_client.put(
        "/api/v1/me/notification-preferences",
        {"preferences": {"jobs": {"in_app": False, "email": False}}},
        format="json",
    )
    Job.objects.filter(pk=live_job).update(expires_at=timezone.now() + timedelta(days=2))
    services.warn_expiring()
    run_outbox()
    assert notices(poster) == []


def test_default_board_settings_hold_for_review_and_sixty_days(db):
    set_board(require_approval=True, days=60)
    from apps.jobs.models import JobSettings

    row = JobSettings.load()
    assert row.require_approval is True and row.default_duration_days == 60
