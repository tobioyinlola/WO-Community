import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.jobs import services
from apps.jobs.models import Job, JobAlert, SavedJob
from apps.jobs.tests.conftest import JOBS, active, post_job
from apps.notifications.models import Notification

pytestmark = pytest.mark.django_db

SAVED = "/api/v1/me/saved-jobs"
ALERTS = "/api/v1/job-alerts"


def save(client, job_id):
    return client.post(f"{JOBS}/{job_id}/save")


# --- saving ---


def test_a_member_can_save_and_unsave_a_job(reader_client, live_job):
    assert save(reader_client, live_job).status_code == 201
    assert save(reader_client, live_job).status_code == 200  # idempotent
    assert SavedJob.objects.count() == 1
    assert reader_client.get(f"{JOBS}/{live_job}").json()["saved"] is True
    assert reader_client.delete(f"{JOBS}/{live_job}/save").status_code == 204
    assert reader_client.delete(f"{JOBS}/{live_job}/save").status_code == 204
    assert reader_client.get(f"{JOBS}/{live_job}").json()["saved"] is False


def test_the_saved_list_is_newest_save_first_and_paged(auto_publish, poster_client, reader_client):
    ids = [post_job(poster_client, title=f"Job {i}").json()["id"] for i in range(4)]
    for job_id in ids:
        save(reader_client, job_id)
    page = reader_client.get(SAVED, {"limit": 3}).json()
    assert [j["id"] for j in page["results"]] == ids[::-1][:3] and page["next_cursor"]
    rest = reader_client.get(SAVED, {"limit": 3, "cursor": page["next_cursor"]}).json()
    assert [j["id"] for j in rest["results"]] == ids[:1]


def test_ended_jobs_stay_in_the_saved_list_with_their_status(
    poster_client, reader_client, live_job
):
    save(reader_client, live_job)
    poster_client.post(f"{JOBS}/{live_job}/close")
    [job] = reader_client.get(SAVED).json()["results"]
    assert job["status"] == "closed"


def test_removed_jobs_and_those_of_inactive_posters_vanish_from_the_saved_list(
    reader_client, live_job, poster
):
    from apps.accounts.models import User

    save(reader_client, live_job)
    Job.objects.filter(pk=live_job).update(status="removed")
    assert reader_client.get(SAVED).json()["results"] == []
    Job.objects.filter(pk=live_job).update(status="published")
    User.objects.filter(pk=poster.pk).update(status="suspended")
    assert reader_client.get(SAVED).json()["results"] == []


def test_you_cannot_save_what_you_cannot_see(reader_client, poster_client):
    pending = post_job(poster_client).json()["id"]
    assert save(reader_client, pending).status_code == 404
    assert save(reader_client, uuid.uuid4()).status_code == 404


def test_saved_jobs_are_private_to_each_member(reader_client, live_job, make_user, client_for):
    save(reader_client, live_job)
    other = client_for(active(make_user, "other@example.com"))
    assert other.get(SAVED).json()["results"] == []


def test_there_is_a_cap_on_saved_jobs(reader_client, live_job, monkeypatch):
    monkeypatch.setattr(services, "MAX_SAVED", 0)
    assert save(reader_client, live_job).status_code == 400


def test_saving_needs_an_active_member(api_client, live_job):
    assert save(api_client, live_job).status_code == 401
    assert api_client.get(SAVED).status_code == 401


# --- managing alerts ---


def make_alert(client, filters=None, frequency="instant"):
    return client.post(ALERTS, {"filters": filters or {}, "frequency": frequency}, format="json")


def test_a_member_can_create_list_and_delete_alerts(reader_client):
    created = make_alert(
        reader_client, {"q": "python", "type": "full_time", "remote": True}, "daily"
    )
    assert created.status_code == 201
    body = created.json()
    assert body["filters"] == {"q": "python", "type": "full_time", "remote": True}
    assert body["frequency"] == "daily"
    assert reader_client.get(ALERTS).json()[0]["id"] == body["id"]
    assert reader_client.delete(f"{ALERTS}/{body['id']}").status_code == 204
    assert reader_client.get(ALERTS).json() == []


def test_blank_filters_are_dropped(reader_client):
    body = make_alert(reader_client, {"q": "", "location": "", "type": "contract"}).json()
    assert body["filters"] == {"type": "contract"}


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"filters": {}},
        {"filters": {}, "frequency": "hourly"},
        {"filters": {"type": "gig"}, "frequency": "instant"},
        {"filters": {"nonsense": 1}, "frequency": "instant"},
        {"filters": {"startup_id": "x"}, "frequency": "instant"},
        {"filters": {}, "frequency": "instant", "extra": 1},
    ],
)
def test_invalid_alerts_are_refused(reader_client, body):
    assert reader_client.post(ALERTS, body, format="json").status_code == 400


def test_a_member_may_have_five_alerts(reader_client):
    assert [make_alert(reader_client).status_code for _ in range(6)] == [201] * 5 + [400]


def test_alerts_are_private_to_each_member(reader_client, make_user, client_for):
    mine = make_alert(reader_client).json()["id"]
    other = client_for(active(make_user, "other@example.com"))
    assert other.get(ALERTS).json() == []
    assert other.delete(f"{ALERTS}/{mine}").status_code == 404
    assert JobAlert.objects.count() == 1


def test_alerts_need_an_active_member(api_client):
    assert api_client.get(ALERTS).status_code == 401
    assert (
        api_client.post(ALERTS, {"filters": {}, "frequency": "instant"}, format="json").status_code
        == 401
    )


# --- instant alerts ---


def alerts_for(user):
    return list(Notification.objects.filter(user=user, type="job_alert"))


def test_a_matching_new_job_alerts_the_member_once(
    auto_publish, poster_client, reader_client, reader, run_outbox, sent_emails
):
    make_alert(reader_client, {"q": "python", "type": "contract"})
    make_alert(reader_client, {"remote": True})  # also matches: still one notice
    post_job(poster_client, title="Python Wizard", type="contract", remote=True)
    run_outbox()
    [notice] = alerts_for(reader)
    assert notice.payload["title"] == "Python Wizard"
    listed = reader_client.get("/api/v1/notifications").json()["results"][0]
    assert listed["title"] == "New job matching your alert: Python Wizard"
    assert listed["link"].startswith("/jobs/")
    assert any("Python Wizard" in m.subject for m in sent_emails)


def test_a_job_that_does_not_match_alerts_nobody(
    auto_publish, poster_client, reader_client, reader, run_outbox
):
    make_alert(reader_client, {"type": "internship"})
    make_alert(reader_client, {"q": "rust"})
    make_alert(reader_client, {"location": "Nairobi"})
    post_job(poster_client, type="full_time", title="Python Dev", location="Lagos")
    run_outbox()
    assert alerts_for(reader) == []


def test_posters_are_not_alerted_to_their_own_jobs(auto_publish, poster_client, poster, run_outbox):
    make_alert(poster_client)
    post_job(poster_client)
    run_outbox()
    assert alerts_for(poster) == []


def test_jobs_alert_when_an_admin_approves_them_not_when_they_wait(
    poster_client, reader_client, reader, run_outbox
):
    make_alert(reader_client)
    created = post_job(poster_client).json()["id"]  # held for review
    run_outbox()
    assert alerts_for(reader) == []
    Job.objects.filter(pk=created).update(
        status="published"
    )  # (approval itself is tested with admins)
    assert services.alert_instantly(uuid.UUID(created)) == 1


def test_daily_alerts_do_not_fire_instantly(
    auto_publish, poster_client, reader_client, reader, run_outbox
):
    make_alert(reader_client, {}, "daily")
    post_job(poster_client)
    run_outbox()
    assert alerts_for(reader) == []


def test_an_alert_can_be_switched_off_in_preferences(
    auto_publish, poster_client, reader_client, reader, run_outbox
):
    reader_client.put(
        "/api/v1/me/notification-preferences",
        {"preferences": {"jobs": {"in_app": False, "email": False}}},
        format="json",
    )
    make_alert(reader_client)
    post_job(poster_client)
    run_outbox()
    assert alerts_for(reader) == []


# --- daily digests ---


def test_a_daily_alert_sends_one_digest_for_new_matching_jobs(
    auto_publish, poster_client, reader_client, reader, run_outbox
):
    alert = make_alert(reader_client, {"type": "contract"}, "daily").json()["id"]
    JobAlert.objects.filter(pk=alert).update(created_at=timezone.now() - timedelta(days=2))
    post_job(poster_client, type="contract", title="One")
    post_job(poster_client, type="contract", title="Two")
    post_job(poster_client, type="internship", title="Not this")
    assert services.send_digests() == 1
    [notice] = Notification.objects.filter(user=reader, type="job_digest")
    assert notice.payload["count"] == 2
    assert (
        reader_client.get("/api/v1/notifications").json()["results"][0]["title"]
        == "2 new jobs match your alert"
    )
    assert services.send_digests() == 0  # not again within a day
    assert JobAlert.objects.get(pk=alert).last_sent_at is not None


def test_no_digest_when_nothing_new_matches(auto_publish, poster_client, reader_client, reader):
    alert = make_alert(reader_client, {"type": "internship"}, "daily").json()["id"]
    JobAlert.objects.filter(pk=alert).update(created_at=timezone.now() - timedelta(days=2))
    post_job(poster_client, type="contract")
    assert services.send_digests() == 0
    assert Notification.objects.filter(type="job_digest").count() == 0


def test_a_new_daily_alert_waits_a_day_before_its_first_digest(
    auto_publish, poster_client, reader_client
):
    make_alert(reader_client, {}, "daily")
    post_job(poster_client)
    assert services.send_digests() == 0


def test_digests_only_count_jobs_since_the_last_one(
    auto_publish, poster_client, reader_client, reader
):
    alert = make_alert(reader_client, {}, "daily").json()["id"]
    JobAlert.objects.filter(pk=alert).update(created_at=timezone.now() - timedelta(days=3))
    post_job(poster_client, title="Old news")
    Job.objects.update(published_at=timezone.now() - timedelta(days=2))
    JobAlert.objects.filter(pk=alert).update(
        last_sent_at=timezone.now() - timedelta(days=1, hours=1)
    )
    post_job(poster_client, title="Fresh")
    services.send_digests()
    assert Notification.objects.get(type="job_digest").payload["count"] == 1


# --- matching rules ---


def test_in_memory_matching_agrees_with_the_board_filters():
    job = Job(
        title="Python Developer",
        organisation="Acme",
        location="Lagos Nigeria",
        type="contract",
        remote=True,
        description_text="build things",
        startup_id=None,
    )
    assert services.matches(job, {})
    assert services.matches(job, {"q": "python developer", "type": "contract", "remote": True})
    assert services.matches(job, {"location": "lagos"})
    assert not services.matches(job, {"q": "python rust"})
    assert not services.matches(job, {"type": "internship"})
    assert not services.matches(job, {"remote": False})
    assert not services.matches(job, {"startup_id": str(uuid.uuid4())})
