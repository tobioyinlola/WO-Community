"""A venture starts from what the member already told us, so nothing is typed twice."""

import pytest

from apps.core.etag import etag_for
from apps.profiles.models import FounderProfile
from apps.profiles.services import get_or_create_profile
from apps.startups import services as startups
from apps.toolkit.ventures import services

pytestmark = pytest.mark.django_db


def with_location(member, country="GH", city="Accra"):
    profile = get_or_create_profile(member.pk)
    FounderProfile.objects.filter(pk=profile.pk).update(country=country, city=city)


def test_a_new_venture_takes_the_members_country_and_city(member):
    with_location(member)
    venture = services.create_venture(owner_id=member.pk, name="Fresh idea")
    assert venture.profile.fields["country"] == "GH"
    assert venture.profile.fields["city"] == "Accra"


def test_a_member_with_no_location_still_gets_a_venture(member):
    venture = services.create_venture(owner_id=member.pk, name="Fresh idea")
    assert venture.profile.fields == {"name": "Fresh idea"}


def test_importing_a_startup_carries_over_its_users(member):
    startup = startups.create_startup(
        owner_id=member.pk,
        data={
            "name": "Kuda Foods",
            "pitch": "Produce to kitchens in a day",
            "country": "NG",
            "city": "Lagos",
            "sector": "agritech",
            "stage": "seed",
        },
    )
    startups.replace_traction(
        user_id=member.pk,
        startup_id=startup.pk,
        items=[{"kind": "users", "value": 1850, "visibility": "members"}],
        if_match=etag_for(startup),
    )
    venture = services.create_venture(
        owner_id=member.pk, name="Kuda Foods", from_startup_id=startup.pk
    )
    assert venture.profile.fields["traction"]["users"] == 1850
    assert venture.profile.fields["city"] == "Lagos"
