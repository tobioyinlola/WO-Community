import pytest
from django.utils import timezone

from apps.profiles import services

PROFILE = "/api/v1/me/profile"
VISIBILITY = "/api/v1/me/visibility"


def member_url(user):
    return f"/api/v1/members/{user.pk}"


@pytest.fixture
def me(make_user):
    return make_user(
        email="me@example.com", approved_at=timezone.now(), email_verified_at=timezone.now()
    )


@pytest.fixture
def other(make_user):
    return make_user(
        email="other@example.com", approved_at=timezone.now(), email_verified_at=timezone.now()
    )


@pytest.fixture
def my_client(me, client_for):
    return client_for(me)


@pytest.fixture
def other_client(other, client_for):
    return client_for(other)


def etag_of(client):
    return client.get(PROFILE)["ETag"]


def patch(client, body, etag=None):
    return client.patch(PROFILE, body, HTTP_IF_MATCH=etag or etag_of(client))


FULL = {
    "full_name": "ZZNAME Okafor",
    "headline": "ZZHEADLINE founder",
    "bio": "ZZBIO builds things",
    "country": "NG",
    "city": "ZZCITY",
    "skills": ["payments"],
    "custom_skills": ["ZZCUSTOMSKILL"],
    "open_to": ["hiring"],
    "linkedin_url": "https://www.linkedin.com/in/zzlinked",
    "x_url": "https://x.com/zzhandle",
    "website_url": "https://zzsite.example.com",
}

# A string that appears in the response only if the matching group is visible.
MARKERS = {
    "basics": "ZZNAME",
    "bio": "ZZBIO",
    "location": "ZZCITY",
    "skills": "ZZCUSTOMSKILL",
    "links": "zzlinked",
    "open_to": "hiring",
}


@pytest.fixture
def full_profile(me, my_client):
    services.create_from_signup(me.pk, {"full_name": "x y", "country": "NG", "city": "Lagos"})
    response = patch(my_client, FULL)
    assert response.status_code == 200
    return me
