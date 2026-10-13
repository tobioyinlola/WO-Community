import pytest
from django.utils import timezone

STARTUPS = "/api/v1/startups"
MINE = "/api/v1/me/startups"


def detail(startup_id):
    return f"{STARTUPS}/{startup_id}"


def new_startup_body(**overrides):
    body = {
        "name": "ZZSTARTUP Pay",
        "pitch": "ZZPITCH payments for traders",
        "country": "NG",
        "city": "ZZCITY",
        "sector": "fintech",
        "stage": "seed",
        "year_founded": 2023,
        "description": "ZZDESCRIPTION long text",
        "website_url": "https://zzsite.example.com",
    }
    body.update(overrides)
    return body


# Strings that appear in a response only if the matching group is visible.
MARKERS = {
    "basics": "ZZSTARTUP",
    "description": "ZZDESCRIPTION",
    "website": "zzsite.example.com",
}


def active_member(make_user, email):
    return make_user(email=email, approved_at=timezone.now(), email_verified_at=timezone.now())


@pytest.fixture
def owner(make_user):
    return active_member(make_user, "owner@example.com")


@pytest.fixture
def stranger(make_user):
    return active_member(make_user, "stranger@example.com")


@pytest.fixture
def owner_client(owner, client_for):
    return client_for(owner)


@pytest.fixture
def stranger_client(stranger, client_for):
    return client_for(stranger)


@pytest.fixture
def startup_id(owner_client):
    response = owner_client.post(STARTUPS, new_startup_body())
    assert response.status_code == 201
    return response.json()["id"]


def etag_of(client, startup_id):
    return client.get(detail(startup_id))["ETag"]


def patch(client, startup_id, body, etag=None):
    return client.patch(detail(startup_id), body, HTTP_IF_MATCH=etag or etag_of(client, startup_id))


def set_levels(client, startup_id, levels, etag=None):
    return client.patch(
        f"{detail(startup_id)}/visibility",
        levels,
        HTTP_IF_MATCH=etag or etag_of(client, startup_id),
    )
