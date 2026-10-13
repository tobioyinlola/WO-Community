from datetime import timedelta

import pytest
from django.utils import timezone

from apps.mentorship.models import MentorProfile
from apps.toolkit.testing import BASE
from apps.toolkit.ventures.models import VentureGrant

pytestmark = pytest.mark.django_db


@pytest.fixture
def mentor(make_user):
    user = make_user(
        email="mentor@example.com", approved_at=timezone.now(), email_verified_at=timezone.now()
    )
    MentorProfile.objects.create(
        user=user,
        expertise=["pricing"],
        years_experience=9,
        current_role="CFO",
        company="Example",
        industries=[],
        stages=[],
        languages=["en"],
        timezone="Africa/Lagos",
        approved_at=timezone.now(),
    )
    return user


@pytest.fixture
def mentor_client(mentor, client_for):
    return client_for(mentor)


def grants(venture, tail=""):
    return f"{BASE}/ventures/{venture['id']}/grants{tail}"


def give(client, venture, mentor, **extra):
    return client.post(grants(venture), {"mentor_id": str(mentor.pk), **extra}, format="json")


def test_a_mentor_with_a_grant_can_read_but_not_change(client, mentor_client, mentor, full_venture):
    assert mentor_client.get(f"{BASE}/ventures/{full_venture['id']}/profile").status_code == 404
    made = give(client, full_venture, mentor, expires_in_days=30)
    assert made.status_code == 201, made.content
    assert made.json()["mentor_id"] == str(mentor.pk)

    shared = mentor_client.get(f"{BASE}/ventures-shared-with-me").json()
    assert [s["venture_id"] for s in shared] == [full_venture["id"]]
    read = mentor_client.get(f"{BASE}/ventures/{full_venture['id']}/profile")
    assert read.status_code == 200 and read.json()["fields"]["name"] == "Mamapesa"

    path = f"{BASE}/ventures/{full_venture['id']}"
    assert (
        mentor_client.patch(
            path + "/profile", {"fields": {"city": "Abuja"}}, format="json"
        ).status_code
        == 404
    )
    assert mentor_client.post(path + "/score").status_code == 404
    assert mentor_client.delete(path).status_code == 404
    assert mentor_client.get(path + "/export").status_code == 404


def test_other_ventures_stay_closed_to_the_mentor(client, mentor_client, mentor, full_venture):
    second = client.post(f"{BASE}/ventures", {"name": "Second"}, format="json").json()
    give(client, full_venture, mentor)
    assert mentor_client.get(f"{BASE}/ventures/{second['id']}/profile").status_code == 404


def test_revoking_or_expiry_ends_access_at_once(client, mentor_client, mentor, full_venture):
    made = give(client, full_venture, mentor).json()
    url = f"{BASE}/ventures/{full_venture['id']}/profile"
    assert mentor_client.get(url).status_code == 200
    assert client.delete(grants(full_venture, f"/{made['id']}")).status_code == 204
    assert mentor_client.get(url).status_code == 404
    assert client.delete(grants(full_venture, f"/{made['id']}")).status_code == 404

    again = give(client, full_venture, mentor).json()
    assert mentor_client.get(url).status_code == 200
    VentureGrant.objects.filter(pk=again["id"]).update(
        expires_at=timezone.now() - timedelta(minutes=1)
    )
    assert mentor_client.get(url).status_code == 404
    assert client.get(grants(full_venture)).json() == []


def test_only_listed_mentors_can_be_chosen_and_only_once(
    client, full_venture, member, other, mentor
):
    assert give(client, full_venture, other).status_code == 400  # an ordinary member
    assert give(client, full_venture, member).status_code == 400  # yourself
    assert give(client, full_venture, mentor).status_code == 201
    assert give(client, full_venture, mentor).status_code == 409
    assert give(client, full_venture, mentor, expires_in_days=0).status_code == 400


def test_only_the_owner_manages_access(client, other_client, mentor_client, mentor, full_venture):
    made = give(client, full_venture, mentor).json()
    assert other_client.get(grants(full_venture)).status_code == 404
    assert (
        other_client.post(
            grants(full_venture), {"mentor_id": str(mentor.pk)}, format="json"
        ).status_code
        == 404
    )
    assert other_client.delete(grants(full_venture, f"/{made['id']}")).status_code == 404
    # The mentor cannot see who else has access, nor add anyone.
    assert mentor_client.get(grants(full_venture)).status_code == 404
    assert (
        mentor_client.post(
            grants(full_venture), {"mentor_id": str(mentor.pk)}, format="json"
        ).status_code
        == 404
    )
