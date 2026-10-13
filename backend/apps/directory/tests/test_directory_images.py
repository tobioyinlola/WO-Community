import json

import pytest

from apps.core import etag
from apps.directory.tests.conftest import FOUNDERS, STARTUPS
from apps.profiles import services as profile_services
from apps.profiles.models import FounderProfile
from apps.startups import services as startup_services
from apps.startups.models import Startup

pytestmark = pytest.mark.django_db


def set_logo(fixture, ready_upload):
    upload = ready_upload(fixture.user, purpose="startup_logo")
    startup_services.set_logo(
        user_id=fixture.user.pk,
        startup_id=fixture.id,
        upload_id=upload.pk,
        if_match=etag.etag_for(Startup.objects.get(pk=fixture.id)),
    )
    return upload


def set_photo(fixture, ready_upload):
    upload = ready_upload(fixture.user, purpose="profile_photo")
    profile_services.set_photo(
        user_id=fixture.user.pk,
        upload_id=upload.pk,
        if_match=etag.etag_for(FounderProfile.objects.get(user=fixture.user)),
    )
    return upload


def test_cards_and_pages_show_the_startup_logo(api_client, listed, ready_upload, run_outbox):
    fixture = listed("Acme Pay")
    assert api_client.get(STARTUPS).json()["results"][0]["logo"] is None
    upload = set_logo(fixture, ready_upload)
    run_outbox()
    expected = {
        "large": f"https://media.test/{upload.base_key}/large.webp",
        "thumb": f"https://media.test/{upload.base_key}/thumb.webp",
    }
    assert api_client.get(STARTUPS).json()["results"][0]["logo"] == expected
    assert api_client.get(f"{STARTUPS}/{fixture.slug}").json()["logo"] == expected


def test_removing_the_logo_removes_it_from_the_public_pages(
    api_client, listed, ready_upload, run_outbox
):
    fixture = listed()
    set_logo(fixture, ready_upload)
    run_outbox()
    startup_services.clear_logo(
        user_id=fixture.user.pk,
        startup_id=fixture.id,
        if_match=etag.etag_for(Startup.objects.get(pk=fixture.id)),
    )
    run_outbox()
    assert api_client.get(STARTUPS).json()["results"][0]["logo"] is None


def test_the_founder_photo_appears_on_the_founder_card_and_page(
    api_client, listed, ready_upload, run_outbox
):
    fixture = listed(founder="Ada Obi")
    upload = set_photo(fixture, ready_upload)
    run_outbox()
    card = api_client.get(FOUNDERS).json()["results"][0]
    assert card["photo"]["thumb"] == f"https://media.test/{upload.base_key}/thumb.webp"
    page = api_client.get(f"{FOUNDERS}/{card['slug']}").json()
    assert page["photo"]["large"].endswith("/large.webp")


def test_a_photo_stays_off_the_public_pages_when_the_basics_are_not_public(
    api_client, listed, ready_upload, run_outbox
):
    fixture = listed(founder_public=False)
    upload = set_photo(fixture, ready_upload)
    run_outbox()
    assert api_client.get(FOUNDERS).json()["results"] == []
    startups = api_client.get(STARTUPS).content.decode()
    assert upload.base_key not in startups


def test_only_processed_media_addresses_ever_reach_the_public_api(
    api_client, listed, ready_upload, run_outbox
):
    fixture = listed()
    set_logo(fixture, ready_upload)
    set_photo(fixture, ready_upload)
    run_outbox()
    text = " ".join(
        api_client.get(url).content.decode()
        for url in (STARTUPS, FOUNDERS, f"{STARTUPS}/{fixture.slug}")
    )
    assert "https://media.test/media/" in text
    # raw uploads live under "<purpose>/<random>" without the media prefix; none may appear
    assert '"profile_photo/' not in text and "/profile_photo/" not in text.replace(
        "media/profile_photo/", ""
    )
    assert "quarantine" not in text
    assert json.loads(api_client.get(STARTUPS).content)
