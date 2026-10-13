import pytest
from django.utils import timezone

from apps.jobs.models import JobSettings

JOBS = "/api/v1/jobs"


def job_body(**overrides):
    body = {
        "title": "Backend Engineer",
        "type": "full_time",
        "organisation": "Acme Labs",
        "location": "Lagos",
        "remote": True,
        "description": "<p>Build <strong>great</strong> payment systems.</p>",
        "requirements": "<ul><li>Python</li></ul>",
        "compensation": "NGN 500k to 700k",
        "apply_method": "url",
        "apply_target": "https://acme.example.com/careers/1",
    }
    body.update(overrides)
    return body


def active(make_user, email, **fields):
    return make_user(
        email=email, approved_at=timezone.now(), email_verified_at=timezone.now(), **fields
    )


def set_board(*, require_approval, days=60):
    row = JobSettings.load()
    row.require_approval = require_approval
    row.default_duration_days = days
    row.save()


@pytest.fixture
def auto_publish(db):
    set_board(require_approval=False)


@pytest.fixture
def poster(make_user):
    return active(make_user, "poster@example.com")


@pytest.fixture
def reader(make_user):
    return active(make_user, "reader@example.com")


@pytest.fixture
def poster_client(poster, client_for):
    return client_for(poster)


@pytest.fixture
def reader_client(reader, client_for):
    return client_for(reader)


def post_job(client, **overrides):
    return client.post(JOBS, job_body(**overrides), format="json")


@pytest.fixture
def live_job(auto_publish, poster_client):
    response = post_job(poster_client)
    assert response.status_code == 201, response.content
    return response.json()["id"]
