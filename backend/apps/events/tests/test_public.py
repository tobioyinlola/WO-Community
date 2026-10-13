from datetime import timedelta

import pytest
from django.utils import timezone

from apps.events import services
from apps.events.models import Event
from apps.events.tests.conftest import make_event
from apps.integrations.cdn.fake import FakePurger

pytestmark = pytest.mark.django_db

PUBLIC = "/api/v1/public/events"


@pytest.fixture(autouse=True)
def _reset_purger():
    FakePurger.reset()


def public_event(admin, **overrides):
    event = make_event(admin, **overrides)
    Event.objects.filter(pk=event.pk).update(public=True)
    return event


def test_only_public_published_events_are_listed(api_client, admin):
    shown = public_event(admin, title="Shown")
    make_event(admin, title="Members only")
    draft = make_event(admin, publish=False, title="Draft")
    Event.objects.filter(pk=draft.pk).update(public=True)
    cancelled = public_event(admin, title="Cancelled")
    services.cancel(actor=admin, event_id=cancelled.pk)
    page = api_client.get(PUBLIC)
    assert [e["slug"] for e in page.json()["results"]] == [shown.slug]
    assert set(page.json()["results"][0]) == {
        "slug",
        "type",
        "title",
        "excerpt",
        "starts_at",
        "ends_at",
        "timezone",
        "location",
        "past",
    }
    assert "public" in page["Cache-Control"]
    assert api_client.get(PUBLIC, HTTP_IF_NONE_MATCH=page["ETag"]).status_code == 304


def test_upcoming_and_past_public_events(api_client, admin):
    upcoming = public_event(admin, title="Upcoming")
    old = public_event(admin, title="Old")
    Event.objects.filter(pk=old.pk).update(
        starts_at=timezone.now() - timedelta(days=3),
        ends_at=timezone.now() - timedelta(days=3) + timedelta(hours=1),
    )
    assert [e["title"] for e in api_client.get(PUBLIC).json()["results"]] == ["Upcoming"]
    assert [e["title"] for e in api_client.get(PUBLIC, {"when": "past"}).json()["results"]] == [
        "Old"
    ]
    assert upcoming.pk


@pytest.mark.parametrize(
    "params",
    [{"when": "now"}, {"type": "x"}, {"limit": 0}, {"cursor": "x"}, {"registered": "true"}],
)
def test_bad_public_queries_are_refused(api_client, params):
    assert api_client.get(PUBLIC, params).status_code == 400


def test_a_public_event_has_open_graph_data_but_no_join_link_or_attendance(
    api_client, admin, member_client
):
    event = public_event(admin)
    member_client.post(f"/api/v1/events/{event.pk}/register")
    body = api_client.get(f"{PUBLIC}/{event.slug}").json()
    assert body["title"] == "Pitch practice workshop" and body["share_url"].endswith(
        f"/events/{event.slug}"
    )
    assert (
        body["open_graph"]["url"] == body["share_url"] and body["open_graph"]["type"] == "website"
    )
    text = (
        api_client.get(PUBLIC).content.decode()
        + api_client.get(f"{PUBLIC}/{event.slug}").content.decode()
    )
    assert "meet.example.com" not in text  # the join link is for members
    assert (
        "member@example.com" not in text
        and "registered_count" not in text
        and "capacity" not in text
    )


def test_unlisted_events_are_404(api_client, admin):
    private = make_event(admin)
    gone = public_event(admin)
    services.remove(actor=admin, event_id=gone.pk)
    for event in (private, gone):
        assert api_client.get(f"{PUBLIC}/{event.slug}").status_code == 404
    assert api_client.get(f"{PUBLIC}/nope").status_code == 404


def test_publishing_and_cancelling_purge_the_public_pages(
    admin, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        event = public_event(admin)
    assert PUBLIC in FakePurger.purged and f"{PUBLIC}/{event.slug}" in FakePurger.purged
    FakePurger.reset()
    with django_capture_on_commit_callbacks(execute=True):
        services.cancel(actor=admin, event_id=event.pk)
    assert f"{PUBLIC}/{event.slug}" in FakePurger.purged
