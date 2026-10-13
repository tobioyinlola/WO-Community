import pytest

from apps.jobs.models import Job, JobSettings
from apps.jobs.tests.conftest import JOBS, job_body, post_job, set_board

pytestmark = pytest.mark.django_db

ADMIN = "/api/v1/admin/jobs"


@pytest.fixture
def admin_client(make_user, client_for):
    return client_for(make_user(roles=("community_admin",)), mfa_age=5)


def etag_of(client, job_id):
    return client.get(f"{JOBS}/{job_id}")["ETag"]


def edit(client, job_id, **fields):
    return client.patch(
        f"{JOBS}/{job_id}", fields, format="json", HTTP_IF_MATCH=etag_of(client, job_id)
    )


def routes(**fields):
    """A job body with the older single route removed, so the new fields decide."""
    body = job_body(**fields)
    body.pop("apply_method")
    body.pop("apply_target")
    return body


# --- how to apply: always off the platform ---


def test_a_job_can_give_a_link_an_email_or_both(auto_publish, poster_client):
    both = poster_client.post(
        JOBS,
        routes(apply_url="https://acme.example.com/jobs/2", apply_email="Jobs@Acme.Example.com"),
        format="json",
    )
    assert both.status_code == 201
    apply = both.json()["apply"]
    assert apply["url"] == "https://acme.example.com/jobs/2"
    assert apply["email"] == "jobs@acme.example.com" and apply["host"] == "acme.example.com"
    only_link = poster_client.post(
        JOBS, routes(apply_url="https://acme.example.com/jobs/3"), format="json"
    )
    only_email = poster_client.post(JOBS, routes(apply_email="hr@acme.example.com"), format="json")
    assert only_link.status_code == 201 and only_email.status_code == 201


@pytest.mark.parametrize(
    "fields",
    [
        {},  # neither route
        {"apply_url": "javascript:alert(1)"},
        {"apply_url": "http://insecure.example.com"},
        {"apply_url": "https://user:pw@example.com"},
        {"apply_email": "not-an-email"},
    ],
)
def test_a_job_needs_a_valid_route_and_never_a_script_or_plain_http_link(
    auto_publish, poster_client, fields
):
    assert poster_client.post(JOBS, routes(**fields), format="json").status_code == 400


def test_there_is_no_way_to_apply_on_the_platform(poster_client, reader_client):
    job = post_job(poster_client).json()
    for url in (f"{JOBS}/{job['id']}/apply", f"{JOBS}/{job['id']}/applications"):
        assert reader_client.post(url, {"note": "hi"}, format="json").status_code == 404
        assert reader_client.get(url).status_code == 404


def test_the_public_page_hides_the_email_but_members_see_it(
    auto_publish, poster_client, reader_client, api_client
):
    job = poster_client.post(
        JOBS, routes(apply_email="jobs@acme.example.com"), format="json"
    ).json()
    seen = reader_client.get(f"{JOBS}/{job['id']}").json()
    assert seen["apply"]["email"] == "jobs@acme.example.com"
    public = api_client.get(f"/api/v1/public/jobs/{job['slug']}").json()
    assert public["apply"]["email"] == ""


# --- who posts, who approves ---


def test_an_admins_job_is_live_at_once_and_a_members_waits(admin_client, poster_client):
    set_board(require_approval=True)
    mine = post_job(poster_client).json()
    theirs = admin_client.post(ADMIN, job_body(), format="json")
    assert mine["status"] == "pending"
    assert theirs.status_code == 201 and theirs.json()["status"] == "published"
    assert theirs.json()["origin"] == "admin"


def test_an_admin_job_may_use_an_email_route(admin_client):
    body = routes(apply_email="jobs@acme.example.com")
    assert admin_client.post(ADMIN, body, format="json").status_code == 201


def test_the_default_term_is_30_days(db):
    assert JobSettings.load().default_duration_days == 30


# --- editing ---


def test_a_rejected_job_can_be_fixed_and_goes_back_to_review(poster_client, admin_client):
    job = post_job(poster_client).json()
    admin_client.post(f"{ADMIN}/{job['id']}/reject", {"reason": "Add a salary"}, format="json")
    assert Job.objects.get(pk=job["id"]).status == "rejected"
    fixed = edit(poster_client, job["id"], compensation="NGN 600k")
    assert fixed.status_code == 200 and fixed.json()["status"] == "pending"
    assert fixed.json()["review_note"] == ""


def test_a_live_member_job_returns_to_review_only_for_sensitive_changes(
    poster_client, admin_client
):
    job = post_job(poster_client).json()
    admin_client.post(f"{ADMIN}/{job['id']}/approve")
    assert edit(poster_client, job["id"], location="Abuja").json()["status"] == "published"
    assert edit(poster_client, job["id"], compensation="NGN 1m").json()["status"] == "published"
    assert edit(poster_client, job["id"], title="Staff Engineer").json()["status"] == "pending"


def test_changing_how_to_apply_on_a_live_job_returns_it_to_review(poster_client, admin_client):
    job = post_job(poster_client).json()
    admin_client.post(f"{ADMIN}/{job['id']}/approve")
    changed = edit(poster_client, job["id"], apply_email="new@acme.example.com")
    assert changed.status_code == 200 and changed.json()["status"] == "pending"


def test_an_admin_edit_to_a_live_member_job_keeps_it_live(poster_client, admin_client):
    job = post_job(poster_client).json()
    admin_client.post(f"{ADMIN}/{job['id']}/approve")
    etag = admin_client.get(f"{ADMIN}/{job['id']}")["ETag"]
    done = admin_client.patch(
        f"{ADMIN}/{job['id']}", {"title": "Better title"}, format="json", HTTP_IF_MATCH=etag
    )
    assert done.status_code == 200 and done.json()["status"] == "published"


# --- the admin lists ---


def test_tabs_count_and_filter(poster_client, admin_client):
    a = post_job(poster_client).json()
    b = post_job(poster_client, title="Designer", type="contract").json()
    admin_client.post(f"{ADMIN}/{a['id']}/approve")
    admin_client.post(f"{ADMIN}/{b['id']}/reject", {"reason": "No"}, format="json")
    admin_client.post(ADMIN, job_body(title="Admin role"), format="json")
    counts = admin_client.get(f"{ADMIN}/stats").json()
    assert counts == {"active": 2, "pending": 0, "rejected": 1, "closed": 0}
    assert admin_client.get(ADMIN, {"tab": "rejected"}).json()["count"] == 1
    assert admin_client.get(ADMIN, {"tab": "active", "type": "full_time"}).json()["count"] == 2
    assert admin_client.get(ADMIN, {"company": "acme"}).json()["count"] == 3
    assert admin_client.get(f"{ADMIN}/stats", {"type": "contract"}).json()["rejected"] == 1


def test_bulk_approve_approves_pending_and_skips_the_rest(poster_client, admin_client):
    jobs = [post_job(poster_client, title=f"Role {n}").json()["id"] for n in range(3)]
    admin_client.post(f"{ADMIN}/{jobs[2]}/reject", {"reason": "No"}, format="json")
    done = admin_client.post(f"{ADMIN}/bulk-approve", {"ids": jobs}, format="json").json()
    assert done == {"approved": 2, "skipped": 1}
    assert Job.objects.filter(status="published").count() == 2


def test_close_reopen_and_remove_tell_the_poster(poster, poster_client, admin_client, run_outbox):
    from apps.notifications.models import Notification

    job = post_job(poster_client).json()
    admin_client.post(f"{ADMIN}/{job['id']}/approve")
    admin_client.post(f"{ADMIN}/{job['id']}/unpublish", {"reason": "Filled"}, format="json")
    assert Job.objects.get(pk=job["id"]).status == "closed"
    reopened = admin_client.post(f"{ADMIN}/{job['id']}/reopen")
    assert reopened.status_code == 200 and reopened.json()["status"] == "published"
    admin_client.post(f"{ADMIN}/{job['id']}/remove", {"reason": "Spam"}, format="json")
    run_outbox()
    kinds = list(Notification.objects.filter(user=poster).values_list("type", flat=True))
    assert kinds.count("job_changed") == 3


def test_a_member_cannot_use_the_admin_job_tools(poster_client, reader_client):
    job = post_job(poster_client).json()
    for method, url in (
        ("get", f"{ADMIN}/stats"),
        ("post", f"{ADMIN}/bulk-approve"),
        ("post", f"{ADMIN}/{job['id']}/reopen"),
    ):
        assert getattr(reader_client, method)(url).status_code == 403
