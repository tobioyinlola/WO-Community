from datetime import timedelta

import pytest
from django.utils import timezone

from apps.core.public import SearchThrottle
from apps.integrations.cdn.fake import FakePurger
from apps.jobs import services
from apps.jobs.models import Job
from apps.jobs.tests.conftest import JOBS, post_job
from apps.startups.tests.conftest import STARTUPS, new_startup_body

pytestmark = pytest.mark.django_db

PUBLIC = "/api/v1/public/jobs"


@pytest.fixture(autouse=True)
def _reset_purger():
    FakePurger.reset()


def slug_of(job_id):
    return Job.objects.get(pk=job_id).slug


# --- the list ---


def test_anyone_can_see_live_jobs_without_logging_in(api_client, live_job):
    response = api_client.get(PUBLIC)
    assert response.status_code == 200
    [job] = response.json()["results"]
    assert job["slug"] == slug_of(live_job) and job["title"] == "Backend Engineer"
    assert set(job) == {
        "slug",
        "title",
        "type",
        "organisation",
        "startup",
        "location",
        "remote",
        "published_at",
        "expires_at",
    }
    assert "public" in response["Cache-Control"] and response["ETag"]


def test_unchanged_pages_answer_304(api_client, live_job):
    tag = api_client.get(PUBLIC)["ETag"]
    assert api_client.get(PUBLIC, HTTP_IF_NONE_MATCH=tag).status_code == 304


def test_pending_closed_expired_and_removed_jobs_are_not_public(
    api_client, auto_publish, poster_client
):
    ids = [post_job(poster_client, title=f"J{i}").json()["id"] for i in range(4)]
    Job.objects.filter(pk=ids[0]).update(status="pending")
    Job.objects.filter(pk=ids[1]).update(status="closed")
    Job.objects.filter(pk=ids[2]).update(expires_at=timezone.now() - timedelta(minutes=1))
    assert [j["slug"] for j in api_client.get(PUBLIC).json()["results"]] == [slug_of(ids[3])]
    for index in range(3):
        assert api_client.get(f"{PUBLIC}/{slug_of(ids[index])}").status_code == 404


def test_the_public_list_filters_and_searches(api_client, auto_publish, poster_client):
    post_job(
        poster_client, title="Python Developer", type="full_time", remote=False, location="Lagos"
    )
    post_job(poster_client, title="Designer", type="contract", remote=True, location="Accra")
    assert [j["title"] for j in api_client.get(PUBLIC, {"type": "contract"}).json()["results"]] == [
        "Designer"
    ]
    assert [j["title"] for j in api_client.get(PUBLIC, {"remote": "false"}).json()["results"]] == [
        "Python Developer"
    ]
    assert [j["title"] for j in api_client.get(PUBLIC, {"q": "python"}).json()["results"]] == [
        "Python Developer"
    ]
    assert [j["title"] for j in api_client.get(PUBLIC, {"location": "accr"}).json()["results"]] == [
        "Designer"
    ]


def test_the_public_list_pages(api_client, auto_publish, poster_client):
    for i in range(5):
        post_job(poster_client, title=f"Job {i}")
    seen, cursor = [], ""
    while True:
        page = api_client.get(PUBLIC, {"limit": 2, "cursor": cursor}).json()
        seen += [j["title"] for j in page["results"]]
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert seen == [f"Job {i}" for i in range(4, -1, -1)]


@pytest.mark.parametrize(
    "params",
    [{"type": "gig"}, {"limit": 0}, {"limit": 51}, {"cursor": "x"}, {"startup_id": "x"}, {"x": 1}],
)
def test_bad_public_queries_are_refused(api_client, params):
    assert api_client.get(PUBLIC, params).status_code == 400


def test_public_search_is_rate_limited_more_tightly(api_client, live_job, monkeypatch):
    monkeypatch.setattr(SearchThrottle, "THROTTLE_RATES", {"public_search": "2/min"})
    codes = [api_client.get(PUBLIC, {"q": "engineer"}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
    assert api_client.get(PUBLIC).status_code == 200  # browsing without searching is unaffected


# --- one job, for sharing ---


def test_a_public_job_has_open_graph_data_for_previews(api_client, live_job, settings):
    job = api_client.get(f"{PUBLIC}/{slug_of(live_job)}").json()
    assert job["title"] == "Backend Engineer" and "great" in job["description"]
    assert job["share_url"] == f"{settings.FRONTEND_BASE_URL}/jobs/{slug_of(live_job)}"
    assert job["open_graph"] == {
        "title": "Backend Engineer",
        "description": "Build great payment systems.",
        "url": job["share_url"],
        "type": "article",
        "image": None,
    }
    assert job["apply"] == {"method": "url", "target": "https://acme.example.com/careers/1"}


def test_the_open_graph_description_is_cut_short(api_client, auto_publish, poster_client):
    post = post_job(poster_client, description="<p>" + "word " * 100 + "</p>").json()["id"]
    description = api_client.get(f"{PUBLIC}/{slug_of(post)}").json()["open_graph"]["description"]
    assert len(description) <= 200 and description.endswith("…")


def test_an_apply_email_is_never_shown_publicly(
    api_client, auto_publish, poster_client, reader_client
):
    job = post_job(poster_client, apply_method="email", apply_target="hr@acme.example.com").json()
    public = api_client.get(f"{PUBLIC}/{slug_of(job['id'])}").json()
    assert public["apply"] == {"method": "email"}
    assert "hr@acme.example.com" not in api_client.get(PUBLIC).content.decode()
    assert (
        "hr@acme.example.com"
        not in api_client.get(f"{PUBLIC}/{slug_of(job['id'])}").content.decode()
    )
    assert (
        reader_client.get(f"{JOBS}/{job['id']}").json()["apply"]["target"] == "hr@acme.example.com"
    )


def test_no_personal_details_of_the_poster_are_public(api_client, live_job, poster):
    body = (
        api_client.get(PUBLIC).content.decode()
        + api_client.get(f"{PUBLIC}/{slug_of(live_job)}").content.decode()
    )
    assert str(poster.pk) not in body and "poster@example.com" not in body


def test_a_startups_public_logo_becomes_the_share_image(api_client, auto_publish, poster_client):
    from apps.startups.tests.conftest import detail, etag_of

    startup = poster_client.post(STARTUPS, new_startup_body(name="Kola Pay")).json()["id"]
    poster_client.patch(
        f"{detail(startup)}/visibility",
        {"basics": "public"},
        HTTP_IF_MATCH=etag_of(poster_client, startup),
    )
    body = {
        "title": "Dev",
        "type": "full_time",
        "startup_id": startup,
        "description": "<p>x</p>",
        "apply_method": "url",
        "apply_target": "https://kola.example.com/jobs",
    }
    job = poster_client.post(JOBS, body, format="json").json()
    public = api_client.get(f"{PUBLIC}/{slug_of(job['id'])}").json()
    assert public["startup"]["name"] == "Kola Pay"


def test_a_startup_hiding_its_basics_is_not_named_publicly(api_client, auto_publish, poster_client):
    startup = poster_client.post(STARTUPS, new_startup_body(name="Secret Co")).json()["id"]
    body = {
        "title": "Dev",
        "type": "full_time",
        "startup_id": startup,
        "description": "<p>x</p>",
        "apply_method": "url",
        "apply_target": "https://secret.example.com/jobs",
    }
    job = poster_client.post(JOBS, body, format="json").json()
    assert api_client.get(f"{PUBLIC}/{slug_of(job['id'])}").json()["startup"] is None


def test_unknown_slugs_are_404(api_client):
    assert api_client.get(f"{PUBLIC}/no-such-job-abc123").status_code == 404


def test_public_endpoints_ignore_credentials(api_client, live_job):
    assert api_client.get(PUBLIC, HTTP_AUTHORIZATION="Bearer garbage").status_code == 200


# --- the sitemap ---


def test_the_sitemap_lists_live_jobs_for_search_engines(api_client, live_job):
    body = api_client.get(f"{PUBLIC}/sitemap").json()
    assert [e["slug"] for e in body["results"]] == [slug_of(live_job)]
    assert "updated_at" in body["results"][0]
    Job.objects.filter(pk=live_job).update(status="closed")
    assert api_client.get(f"{PUBLIC}/sitemap").json()["results"] == []


def test_the_sitemap_takes_no_parameters(api_client):
    assert api_client.get(f"{PUBLIC}/sitemap", {"x": 1}).status_code == 400


# --- cache purging ---


def test_going_live_and_closing_purge_the_public_pages(
    auto_publish, poster_client, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        job_id = post_job(poster_client).json()["id"]
    page = f"/api/v1/public/jobs/{slug_of(job_id)}"
    assert page in FakePurger.purged and PUBLIC in FakePurger.purged
    FakePurger.reset()
    with django_capture_on_commit_callbacks(execute=True):
        poster_client.post(f"{JOBS}/{job_id}/close")
    assert page in FakePurger.purged


def test_a_failing_cdn_never_breaks_a_job_change(auto_publish, poster_client, monkeypatch):
    def broken():
        raise RuntimeError("cdn down")

    monkeypatch.setattr(services, "get_cache_purger", broken)
    assert post_job(poster_client).status_code == 201
