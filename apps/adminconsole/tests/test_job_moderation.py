import uuid

import pytest
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.jobs.models import Job, JobSettings
from apps.notifications.models import Notification

pytestmark = pytest.mark.django_db

JOBS = "/api/v1/jobs"
ADMIN = "/api/v1/admin/jobs"


def body(**overrides):
    base = {
        "title": "Community Manager",
        "type": "part_time",
        "organisation": "Partner Org",
        "location": "Remote",
        "remote": True,
        "description": "<p>Look after our members.</p>",
        "apply_method": "url",
        "apply_target": "https://partner.example.com/apply",
    }
    base.update(overrides)
    return base


@pytest.fixture
def member(make_user):
    return make_user(
        email="member@example.com", approved_at=timezone.now(), email_verified_at=timezone.now()
    )


@pytest.fixture
def member_client(member, client_for):
    return client_for(member)


@pytest.fixture
def editor(make_user):
    return make_user(roles=("content_editor",), email="editor@example.com")


@pytest.fixture
def as_editor(editor, client_for):
    return client_for(editor, mfa_age=5)


@pytest.fixture
def super_admin(make_user):
    return make_user(roles=("super_admin",), email="root@example.com")


@pytest.fixture
def as_super(super_admin, client_for):
    return client_for(super_admin, mfa_age=5)


@pytest.fixture
def pending(member_client):
    JobSettings.objects.update_or_create(id=1, defaults={"require_approval": True})
    response = member_client.post(JOBS, body(), format="json")
    assert response.json()["status"] == "pending"
    return response.json()["id"]


def decide(client, job_id, decision, **data):
    return client.post(f"{ADMIN}/{job_id}/{decision}", data, format="json")


# --- the review queue ---


def test_pending_jobs_are_queued_oldest_first(as_editor, member_client, pending):
    second = member_client.post(JOBS, body(title="Second"), format="json").json()["id"]
    queue = as_editor.get(ADMIN, {"status": "pending"}).json()
    assert queue["count"] == 2
    assert [j["id"] for j in queue["results"]] == [pending, second]
    assert queue["results"][0]["poster_id"]


def test_the_queue_count_appears_with_the_other_queues(make_user, client_for, pending):
    admin = client_for(make_user(roles=("community_admin",), email="ca@example.com"), mfa_age=5)
    assert admin.get("/api/v1/admin/queues").json()["jobs_awaiting_review"] == 1


def test_jobs_can_be_filtered_by_origin_and_text(as_editor, pending):
    as_editor.post(ADMIN, body(title="Partner role"), format="json")
    assert as_editor.get(ADMIN, {"origin": "admin"}).json()["count"] == 1
    assert as_editor.get(ADMIN, {"origin": "member"}).json()["count"] == 1
    assert as_editor.get(ADMIN, {"q": "partner"}).json()["count"] == 2


@pytest.mark.parametrize("params", [{"status": "x"}, {"origin": "x"}, {"limit": 0}, {"z": 1}])
def test_bad_admin_queries_are_refused(as_editor, params):
    assert as_editor.get(ADMIN, params).status_code == 400


# --- approving and rejecting ---


def test_approving_puts_the_job_live_tells_the_poster_and_alerts_followers(
    as_editor, editor, member_client, make_user, client_for, pending, run_outbox
):
    reader = make_user(
        email="reader@example.com", approved_at=timezone.now(), email_verified_at=timezone.now()
    )
    reader_client = client_for(reader)
    reader_client.post(
        "/api/v1/job-alerts", {"filters": {"q": "community"}, "frequency": "instant"}, format="json"
    )
    response = decide(as_editor, pending, "approve")
    assert response.status_code == 200 and response.json()["status"] == "published"
    assert response.json()["reviewed_by"] == str(editor.pk)
    assert reader_client.get(f"{JOBS}/{pending}").status_code == 200
    run_outbox()
    [notice] = Notification.objects.filter(type="job_approved")
    assert notice.payload["job_id"] == pending
    assert Notification.objects.filter(user=reader, type="job_alert").count() == 1
    assert AuditLog.objects.filter(action="jobs.approve").count() == 1


def test_rejecting_needs_a_reason_and_the_poster_is_told_it(
    as_editor, member_client, pending, run_outbox
):
    assert decide(as_editor, pending, "reject").status_code == 400
    response = decide(as_editor, pending, "reject", reason="Looks like an advert")
    assert response.json()["status"] == "rejected"
    run_outbox()
    mine = member_client.get(f"{JOBS}/{pending}").json()
    assert mine["status"] == "rejected" and mine["review_note"] == "Looks like an advert"
    [item] = member_client.get("/api/v1/notifications").json()["results"]
    assert item["type"] == "job_rejected" and "Looks like an advert" in item["title"]
    assert AuditLog.objects.filter(action="jobs.reject", reason="Looks like an advert").exists()


def test_only_pending_jobs_can_be_approved_or_rejected(as_editor, pending):
    decide(as_editor, pending, "approve")
    assert decide(as_editor, pending, "approve").status_code == 409
    assert decide(as_editor, pending, "reject", reason="late").status_code == 409


def test_a_rejected_job_is_not_public_or_alerting(as_editor, pending, member_client, api_client):
    decide(as_editor, pending, "reject", reason="no")
    assert Job.objects.get(pk=pending).published_at is None
    assert api_client.get("/api/v1/public/jobs").json()["results"] == []


# --- unpublishing and removing ---


def test_unpublishing_takes_a_live_job_down_and_the_poster_can_renew_it(
    as_editor, member_client, pending
):
    decide(as_editor, pending, "approve")
    assert (
        decide(as_editor, pending, "unpublish", reason="needs rework").json()["status"] == "closed"
    )
    assert member_client.get(f"{JOBS}/{pending}").json()["status"] == "closed"
    assert decide(as_editor, pending, "unpublish").status_code == 409


def test_removing_takes_a_job_down_for_everyone_including_the_poster(
    as_editor, member_client, pending
):
    decide(as_editor, pending, "approve")
    assert decide(as_editor, pending, "remove", reason="scam").json()["status"] == "removed"
    assert member_client.get(f"{JOBS}/{pending}").status_code == 404
    assert member_client.post(f"{JOBS}/{pending}/renew").status_code in (404, 409)
    assert decide(as_editor, pending, "remove").status_code == 409
    assert AuditLog.objects.filter(action="jobs.remove", reason="scam").exists()


def test_decisions_on_unknown_jobs_are_404(as_editor):
    assert decide(as_editor, uuid.uuid4(), "approve").status_code == 404


# --- jobs added by admins ---


def test_an_admin_posts_a_job_that_goes_live_at_once(as_editor, member_client):
    created = as_editor.post(ADMIN, body(), format="json")
    assert created.status_code == 201
    job = created.json()
    assert job["status"] == "published" and job["origin"] == "admin"
    seen = member_client.get(f"{JOBS}/{job['id']}").json()
    assert seen["poster"] is None and seen["organisation"] == "Partner Org"


def test_admin_jobs_always_need_an_external_link(as_editor):
    assert (
        as_editor.post(
            ADMIN, body(apply_method="email", apply_target="hr@x.example.com"), format="json"
        ).status_code
        == 400
    )
    assert (
        as_editor.post(
            ADMIN, body(apply_target="http://insecure.example.com"), format="json"
        ).status_code
        == 400
    )
    assert as_editor.post(ADMIN, body(organisation=""), format="json").status_code == 400


def test_admin_jobs_ignore_the_daily_member_limit(as_editor, monkeypatch):
    from apps.jobs import services

    monkeypatch.setattr(services, "JOBS_PER_DAY", 1)
    assert [as_editor.post(ADMIN, body(), format="json").status_code for _ in range(3)] == [201] * 3


def test_an_admin_can_edit_any_job_with_the_etag(as_editor, pending):
    etag = as_editor.get(f"{ADMIN}/{pending}")["ETag"]
    response = as_editor.patch(
        f"{ADMIN}/{pending}", {"title": "Edited by admin"}, format="json", HTTP_IF_MATCH=etag
    )
    assert response.status_code == 200 and response.json()["title"] == "Edited by admin"
    assert as_editor.patch(f"{ADMIN}/{pending}", {"title": "x"}, format="json").status_code == 428
    assert (
        as_editor.patch(
            f"{ADMIN}/{pending}", {"title": "x"}, format="json", HTTP_IF_MATCH=etag
        ).status_code
        == 412
    )


def test_one_job_can_be_read(as_editor, pending):
    assert as_editor.get(f"{ADMIN}/{pending}").json()["id"] == pending
    assert as_editor.get(f"{ADMIN}/{uuid.uuid4()}").status_code == 404


# --- board settings ---


def test_a_super_admin_can_switch_the_board_to_auto_publish(as_super, member_client):
    assert as_super.get(f"{ADMIN}/settings").json() == {
        "require_approval": True,
        "default_duration_days": 60,
    }
    saved = as_super.put(
        f"{ADMIN}/settings", {"require_approval": False, "default_duration_days": 30}, format="json"
    )
    assert saved.status_code == 200 and saved.json()["require_approval"] is False
    assert member_client.post(JOBS, body(), format="json").json()["status"] == "published"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"require_approval": True},
        {"require_approval": True, "default_duration_days": 0},
        {"require_approval": True, "default_duration_days": 366},
        {"require_approval": "x", "default_duration_days": 5},
        {"require_approval": True, "default_duration_days": 5, "x": 1},
    ],
)
def test_invalid_settings_are_refused(as_super, payload):
    assert as_super.put(f"{ADMIN}/settings", payload, format="json").status_code == 400


# --- access control ---


READ_ENDPOINTS = [("get", ADMIN), ("get", f"{ADMIN}/{uuid.uuid4()}")]
WRITE_ENDPOINTS = [
    ("post", ADMIN),
    *[
        ("post", f"{ADMIN}/{uuid.uuid4()}/{d}")
        for d in ("approve", "reject", "unpublish", "remove")
    ],
    ("patch", f"{ADMIN}/{uuid.uuid4()}"),
]


@pytest.mark.parametrize("method, url", READ_ENDPOINTS + WRITE_ENDPOINTS)
def test_visitors_and_members_cannot_use_admin_job_endpoints(
    api_client, member_client, method, url
):
    assert getattr(api_client, method)(url).status_code == 401
    assert getattr(member_client, method)(url).status_code == 403


@pytest.mark.parametrize("method, url", READ_ENDPOINTS + WRITE_ENDPOINTS)
def test_admins_without_a_recent_mfa_check_are_refused(editor, client_for, method, url):
    assert getattr(client_for(editor), method)(url).status_code == 403


def test_settings_need_a_super_admin(as_editor, member_client, api_client):
    assert as_editor.get(f"{ADMIN}/settings").status_code == 403
    assert (
        as_editor.put(
            f"{ADMIN}/settings",
            {"require_approval": False, "default_duration_days": 5},
            format="json",
        ).status_code
        == 403
    )
    assert member_client.get(f"{ADMIN}/settings").status_code == 403
    assert api_client.get(f"{ADMIN}/settings").status_code == 401
