import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.analytics.models import AnalyticsEvent
from apps.jobs.models import Job
from apps.jobs.tests.conftest import JOBS, job_body, post_job, set_board
from apps.startups.tests.conftest import STARTUPS, new_startup_body

pytestmark = pytest.mark.django_db


def job_url(job_id):
    return f"{JOBS}/{job_id}"


# --- posting ---


def test_by_default_a_members_job_waits_for_an_admin(poster_client, reader_client):
    response = post_job(poster_client)
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "pending" and body["published_at"] is None
    assert body["mine"] is True and body["origin"] == "member"
    assert reader_client.get(job_url(body["id"])).status_code == 404
    assert reader_client.get(JOBS).json()["results"] == []


def test_when_the_board_auto_publishes_the_job_is_live_at_once(
    auto_publish, poster_client, reader_client
):
    body = post_job(poster_client).json()
    assert body["status"] == "published"
    assert body["expires_at"] is not None
    assert [j["id"] for j in reader_client.get(JOBS).json()["results"]] == [body["id"]]
    seen = reader_client.get(job_url(body["id"])).json()
    assert seen["title"] == "Backend Engineer" and seen["mine"] is False
    assert seen["apply"] == {"method": "url", "target": "https://acme.example.com/careers/1"}


def test_the_default_term_is_configurable(auto_publish, poster_client):
    set_board(require_approval=False, days=10)
    expires = post_job(poster_client).json()["expires_at"]
    assert timezone.datetime.fromisoformat(
        expires.replace("Z", "+00:00")
    ) < timezone.now() + timedelta(days=11)


def test_a_deadline_sets_the_expiry_to_the_end_of_that_day(auto_publish, poster_client):
    deadline = (timezone.now() + timedelta(days=5)).date()
    body = post_job(poster_client, deadline=deadline.isoformat()).json()
    assert body["deadline"] == deadline.isoformat()
    assert body["expires_at"].startswith(f"{deadline.isoformat()}T23:59:59")


def test_creating_a_job_records_an_analytics_event(poster_client, poster):
    post_job(poster_client, type="contract")
    [event] = AnalyticsEvent.objects.filter(name="job_created")
    assert event.actor_id == poster.pk and event.properties == {"job_type": "contract"}


def test_a_job_can_apply_by_email(auto_publish, poster_client, reader_client):
    body = post_job(
        poster_client, apply_method="email", apply_target="Jobs@Acme.Example.com"
    ).json()
    assert body["apply"] == {"method": "email", "target": "jobs@acme.example.com"}


@pytest.mark.parametrize(
    "overrides",
    [
        {"title": ""},
        {"title": "x" * 141},
        {"type": "gig"},
        {"description": ""},
        {"description": "<p></p>"},
        {"description": "x" * 5001},
        {"requirements": "x" * 3001},
        {"apply_method": "phone"},
        {"apply_method": "url", "apply_target": "http://insecure.example.com"},
        {"apply_method": "url", "apply_target": "javascript:alert(1)"},
        {"apply_method": "url", "apply_target": "https://127.0.0.1/x"},
        {"apply_method": "url", "apply_target": "not a link"},
        {"apply_method": "email", "apply_target": "not-an-email"},
        {"deadline": "2000-01-01"},
        {"deadline": (timezone.now() + timedelta(days=400)).date().isoformat()},
        {"deadline": "soon"},
        {"organisation": ""},
        {"status": "published"},
        {"poster_id": str(uuid.uuid4())},
        {"remote": "maybe"},
    ],
)
def test_invalid_jobs_are_refused(poster_client, overrides):
    assert post_job(poster_client, **overrides).status_code == 400
    assert Job.objects.count() == 0


def test_a_job_needs_a_startup_or_an_organisation(poster_client):
    body = job_body()
    del body["organisation"]
    assert poster_client.post(JOBS, body, format="json").status_code == 400


def test_a_job_can_be_posted_for_ones_own_startup_but_not_someone_elses(
    auto_publish, poster_client, reader_client
):
    startup = poster_client.post(STARTUPS, new_startup_body(name="Kola Pay")).json()["id"]
    body = job_body(startup_id=startup)
    del body["organisation"]
    created = poster_client.post(JOBS, body, format="json")
    assert created.status_code == 201 and created.json()["startup"]["name"] == "Kola Pay"
    assert reader_client.post(JOBS, body, format="json").status_code == 400


def test_rich_text_is_cleaned(auto_publish, poster_client):
    body = post_job(
        poster_client,
        description=(
            '<h2>Role</h2><p onclick="x()">Hi</p><script>alert(1)</script>'
            '<a href="javascript:x">y</a>'
        ),
    ).json()
    assert "<script" not in body["description"] and "onclick" not in body["description"]
    assert "javascript:" not in body["description"] and "<h2>Role</h2>" in body["description"]


def test_a_member_has_a_daily_allowance(poster_client, monkeypatch):
    from apps.jobs import services

    monkeypatch.setattr(services, "JOBS_PER_DAY", 2)
    assert [post_job(poster_client).status_code for _ in range(3)] == [201, 201, 429]


def test_posting_needs_an_active_member(api_client, make_user, client_for):
    assert api_client.post(JOBS, job_body(), format="json").status_code == 401
    pending = client_for(make_user(email="p@example.com", status="pending"))
    assert post_job(pending).status_code == 403


# --- editing ---


def edit(client, job_id, body, etag=None):
    return client.patch(
        job_url(job_id),
        body,
        format="json",
        HTTP_IF_MATCH=etag or client.get(job_url(job_id))["ETag"],
    )


def test_the_poster_can_edit_a_live_job(poster_client, live_job):
    response = edit(poster_client, live_job, {"title": "Senior Backend Engineer", "remote": False})
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Senior Backend Engineer" and body["remote"] is False
    assert body["edited_at"] is not None


def test_editing_needs_the_current_etag(poster_client, live_job):
    assert poster_client.patch(job_url(live_job), {"title": "x"}, format="json").status_code == 428
    stale = poster_client.get(job_url(live_job))["ETag"]
    edit(poster_client, live_job, {"title": "First"})
    assert edit(poster_client, live_job, {"title": "Second"}, etag=stale).status_code == 412


def test_changing_the_deadline_moves_the_expiry(poster_client, live_job):
    deadline = (timezone.now() + timedelta(days=3)).date()
    body = edit(poster_client, live_job, {"deadline": deadline.isoformat()}).json()
    assert body["expires_at"].startswith(deadline.isoformat())


@pytest.mark.parametrize(
    "body",
    [
        {"type": "gig"},
        {"title": ""},
        {"description": "<p></p>"},
        {"status": "closed"},
        {"slug": "x"},
    ],
)
def test_invalid_edits_are_refused(poster_client, live_job, body):
    assert edit(poster_client, live_job, body).status_code == 400


def test_nobody_else_can_edit_a_job(reader_client, poster_client, live_job):
    etag = reader_client.get(job_url(live_job))["ETag"]
    response = reader_client.patch(
        job_url(live_job), {"title": "hijack"}, format="json", HTTP_IF_MATCH=etag
    )
    assert response.status_code == 404
    assert Job.objects.get(pk=live_job).title == "Backend Engineer"


def test_a_pending_job_can_be_edited_and_stays_pending(poster_client):
    created = post_job(poster_client).json()
    assert edit(poster_client, created["id"], {"title": "Changed"}).json()["status"] == "pending"


# --- reading ---


def test_a_job_is_visible_to_its_poster_in_any_state_but_removed(poster_client, live_job):
    poster_client.post(f"{JOBS}/{live_job}/close")
    assert poster_client.get(job_url(live_job)).json()["status"] == "closed"
    Job.objects.filter(pk=live_job).update(status="removed")
    assert poster_client.get(job_url(live_job)).status_code == 404


def test_jobs_of_suspended_posters_leave_the_board(live_job, reader_client, poster):
    from apps.accounts.models import User

    User.objects.filter(pk=poster.pk).update(status="suspended")
    assert reader_client.get(JOBS).json()["results"] == []
    assert reader_client.get(job_url(live_job)).status_code == 404


def test_a_lapsed_job_is_off_the_board_even_before_the_sweep_runs(live_job, reader_client):
    Job.objects.filter(pk=live_job).update(expires_at=timezone.now() - timedelta(minutes=1))
    assert reader_client.get(JOBS).json()["results"] == []
    assert reader_client.get(job_url(live_job)).status_code == 404


def test_my_jobs_lists_everything_i_posted(poster_client, reader_client, auto_publish):
    a = post_job(poster_client, title="A").json()["id"]
    poster_client.post(f"{JOBS}/{a}/close")
    set_board(require_approval=True)
    b = post_job(poster_client, title="B").json()["id"]
    post_job(reader_client, title="Not mine")
    mine = poster_client.get("/api/v1/me/jobs").json()["results"]
    assert [j["id"] for j in mine] == [b, a]


def test_the_board_requires_an_active_member(api_client, make_user, client_for):
    assert api_client.get(JOBS).status_code == 401
    assert (
        client_for(make_user(email="p@example.com", status="pending")).get(JOBS).status_code == 403
    )


def test_board_responses_are_not_cached(reader_client):
    assert reader_client.get(JOBS)["Cache-Control"] == "private, no-store"


# --- the board: filters, search, paging ---


@pytest.fixture
def several(auto_publish, poster_client):
    made = {}
    for key, overrides in {
        "dev": {
            "title": "Python Developer",
            "type": "full_time",
            "location": "Lagos",
            "remote": False,
        },
        "design": {
            "title": "Product Designer",
            "type": "contract",
            "location": "Nairobi",
            "remote": True,
        },
        "intern": {
            "title": "Marketing Intern",
            "type": "internship",
            "location": "Accra",
            "remote": True,
        },
        "help": {
            "title": "Volunteer Mentor",
            "type": "volunteer",
            "location": "Kigali",
            "remote": True,
        },
    }.items():
        made[key] = post_job(poster_client, **overrides).json()["id"]
    return made


def board_ids(client, **params):
    return [j["id"] for j in client.get(JOBS, params).json()["results"]]


def test_the_board_lists_newest_first_and_pages(several, reader_client):
    expected = [several[k] for k in ("help", "intern", "design", "dev")]
    assert board_ids(reader_client) == expected
    seen, cursor = [], ""
    while True:
        page = reader_client.get(JOBS, {"limit": 3, "cursor": cursor}).json()
        seen += [j["id"] for j in page["results"]]
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert seen == expected


def test_filters_narrow_the_board(several, reader_client):
    assert board_ids(reader_client, type="contract") == [several["design"]]
    assert set(board_ids(reader_client, remote="true")) == {
        several[k] for k in ("design", "intern", "help")
    }
    assert board_ids(reader_client, remote="false") == [several["dev"]]
    assert board_ids(reader_client, location="nair") == [several["design"]]
    assert board_ids(reader_client, posted_within_days=1) == board_ids(reader_client)


def test_posted_within_excludes_older_jobs(several, reader_client):
    Job.objects.filter(pk=several["dev"]).update(published_at=timezone.now() - timedelta(days=10))
    assert several["dev"] not in board_ids(reader_client, posted_within_days=7)
    assert several["dev"] in board_ids(reader_client, posted_within_days=30)


def test_filtering_by_startup(auto_publish, poster_client, reader_client):
    startup = poster_client.post(STARTUPS, new_startup_body(name="Kola Pay")).json()["id"]
    body = job_body(startup_id=startup)
    del body["organisation"]
    mine = poster_client.post(JOBS, body, format="json").json()["id"]
    post_job(poster_client, title="Elsewhere")
    assert board_ids(reader_client, startup_id=startup) == [mine]


def test_text_search_matches_titles_and_descriptions_and_forgives_typos(several, reader_client):
    assert board_ids(reader_client, q="designer") == [several["design"]]
    assert board_ids(reader_client, q="Desginer") == [several["design"]]  # typo
    assert board_ids(reader_client, q="payment") == board_ids(reader_client)  # in every description
    assert board_ids(reader_client, q="zzqq") == []


def test_quoted_and_excluded_terms_use_exact_rules(several, reader_client):
    assert board_ids(reader_client, q="payment -designer") != board_ids(reader_client)
    assert several["design"] not in board_ids(reader_client, q="payment -designer")


@pytest.mark.parametrize(
    "params",
    [
        {"type": "gig"},
        {"remote": "perhaps"},
        {"startup_id": "x"},
        {"posted_within_days": 0},
        {"posted_within_days": 91},
        {"limit": 0},
        {"limit": 51},
        {"cursor": "junk"},
        {"q": "x" * 101},
        {"extra": 1},
    ],
)
def test_bad_board_queries_are_refused(reader_client, params):
    assert reader_client.get(JOBS, params).status_code == 400


def test_search_terms_are_treated_as_text(several, reader_client):
    for hostile in ("%", "' OR 1=1 --", "\\", "a" * 100):
        assert reader_client.get(JOBS, {"q": hostile}).status_code == 200
