import itertools
from types import SimpleNamespace

import pytest
from django.utils import timezone

from apps.core import etag
from apps.integrations.cdn.fake import FakePurger
from apps.profiles import services as profile_services
from apps.profiles.models import FounderProfile
from apps.startups import services as startup_services
from apps.startups.models import Startup

STARTUPS = "/api/v1/public/startups"
FOUNDERS = "/api/v1/public/founders"
SITEMAP = "/api/v1/public/sitemap"


@pytest.fixture(autouse=True)
def _reset_purger():
    FakePurger.reset()


def make_member(make_user, email, **fields):
    return make_user(
        email=email, approved_at=timezone.now(), email_verified_at=timezone.now(), **fields
    )


def edit_startup(startup_id, **data):
    startup = Startup.objects.get(pk=startup_id)
    startup_services.update_startup(
        user_id=startup.owner_id,
        startup_id=startup.pk,
        data=data,
        if_match=etag.etag_for(startup),
    )


def edit_profile(user_id, **data):
    profile = FounderProfile.objects.get(user_id=user_id)
    profile_services.update_profile(user_id=user_id, data=data, if_match=etag.etag_for(profile))


def set_startup_levels(startup_id, **levels):
    startup = Startup.objects.get(pk=startup_id)
    startup_services.set_visibility(
        user_id=startup.owner_id,
        startup_id=startup.pk,
        levels=levels,
        if_match=etag.etag_for(startup),
    )


@pytest.fixture
def listed(make_user, run_outbox):
    """Build a listed startup with a public founder; returns a namespace of handles."""
    counter = itertools.count()

    def build(
        name="Acme Pay",
        *,
        founder="Ada Obi",
        sector="fintech",
        stage="seed",
        country="NG",
        skills=("payments",),
        pitch="Payments for small traders",
        description="ZZDESCRIPTION we move money",
        team_public=True,
        founder_public=True,
        founder_location_public=False,
        description_public=True,
        featured=False,
        listed=True,
        process=True,
    ):
        n = next(counter)
        user = make_member(make_user, f"founder{n}@example.com")
        profile_services.create_from_signup(
            user.pk, {"full_name": founder, "country": country, "city": "Lagos"}
        )
        edit_profile(user.pk, skills=list(skills), bio="ZZBIO builds things")
        levels = {"basics": "public" if founder_public else "members"}
        levels["skills"] = "public"
        if founder_location_public:
            levels["location"] = "public"
        profile_services.update_visibility(user_id=user.pk, levels=levels)
        startup = startup_services.create_startup(
            owner_id=user.pk,
            data={
                "name": name,
                "pitch": pitch,
                "country": country,
                "city": "Lagos",
                "sector": sector,
                "stage": stage,
                "year_founded": 2022,
                "description": description,
                "website_url": "https://acme.example.com",
            },
        )
        if listed:
            edit_startup(startup.pk, directory_opt_in=True)
        set_startup_levels(
            startup.pk,
            team="public" if team_public else "members",
            description="public" if description_public else "members",
            website="public",
        )
        if featured:
            startup_services.set_featured(actor=user, startup_id=startup.pk, featured=True)
        if process:
            run_outbox()
        return SimpleNamespace(user=user, startup=startup, slug=startup.slug, id=startup.pk)

    return build


def slugs(response):
    return [item["slug"] for item in response.json()["results"]]
