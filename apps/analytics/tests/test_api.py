import uuid
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.throttling import ScopedRateThrottle

from apps.analytics import services
from apps.analytics.models import AnalyticsEvent, IdentityLink

pytestmark = pytest.mark.django_db

EVENTS = "/api/v1/events"
PREFERENCES = "/api/v1/me/analytics-preferences"


def view_event(slug="acme-pay-1a2b3c", **extra):
    return {"name": "startup_page_viewed", "properties": {"startup_slug": slug}, **extra}


# --- reporting events ---


def test_anyone_can_report_browser_events_without_logging_in(api_client):
    anon = str(uuid.uuid4())
    response = api_client.post(EVENTS, {"anonymous_id": anon, "events": [view_event()]})
    assert response.status_code == 202
    assert response.json() == {"accepted": 1, "rejected": []}
    event = AnalyticsEvent.objects.get()
    assert (event.source, event.actor_id, str(event.anonymous_id)) == ("client", None, anon)
    assert event.properties == {"startup_slug": "acme-pay-1a2b3c"}


def test_events_can_arrive_with_no_visitor_id_at_all(api_client):
    api_client.post(EVENTS, {"events": [{"name": "directory_viewed"}]})
    assert AnalyticsEvent.objects.get().anonymous_id is None


def test_a_signed_in_member_is_recorded_as_the_actor_and_linked_to_the_visitor_id(
    make_user, client_for
):
    member, anon = make_user(email="a@example.com"), uuid.uuid4()
    client_for(member).post(EVENTS, {"anonymous_id": str(anon), "events": [view_event()]})
    event = AnalyticsEvent.objects.get()
    assert (event.actor_id, event.anonymous_id) == (member.pk, anon)
    assert IdentityLink.objects.get().user_id == member.pk


def test_a_bad_or_expired_token_is_treated_as_an_anonymous_visitor_not_an_error(api_client):
    response = api_client.post(
        EVENTS, {"events": [view_event()]}, HTTP_AUTHORIZATION="Bearer not-a-token"
    )
    assert response.status_code == 202
    assert AnalyticsEvent.objects.get().actor_id is None


def test_every_valid_event_in_a_batch_is_kept_and_each_bad_one_is_explained(api_client):
    batch = [
        view_event(),
        {"name": "member_approved", "properties": {"approval_source": "admin"}},  # server only
        {"name": "invented_event"},
        {"name": "join_cta_clicked", "properties": {"location": "mars"}},
        {"name": "directory_viewed", "properties": {"email": "a@example.com"}},
        {"name": "startup_page_viewed", "properties": {"startup_slug": "not a slug!"}},
        {"name": "directory_viewed", "properties": {"nested": {"a": 1}}},
        {"name": "directory_viewed", "properties": {"page": 2}},
    ]
    body = api_client.post(EVENTS, {"events": batch}).json()
    assert body["accepted"] == 2
    assert [r["index"] for r in body["rejected"]] == [1, 2, 3, 4, 5, 6]
    reasons = {r["index"]: r["reason"] for r in body["rejected"]}
    assert "server" in reasons[1] and "unknown event" in reasons[2]
    assert AnalyticsEvent.objects.count() == 2


def test_a_browser_can_never_claim_that_a_member_was_approved(api_client):
    api_client.post(EVENTS, {"events": [{"name": "member_approved"}, {"name": "member_removed"}]})
    assert AnalyticsEvent.objects.count() == 0


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"events": []},
        {"events": "nope"},
        {"events": [view_event()] * 51},
        {"events": [view_event()], "actor_id": str(uuid.uuid4())},
        {"events": [view_event()], "anonymous_id": "not-a-uuid"},
        {"events": [{"properties": {}}]},
        {"events": [{"name": "x" * 61}]},
        {"events": [view_event(occurred_at="yesterday")]},
        {"events": [{"name": "directory_viewed", "source": "server"}]},
    ],
)
def test_malformed_batches_are_refused_whole(api_client, body):
    assert api_client.post(EVENTS, body).status_code == 400
    assert AnalyticsEvent.objects.count() == 0


def test_the_largest_allowed_batch_is_accepted(api_client):
    response = api_client.post(EVENTS, {"events": [view_event()] * 50})
    assert response.json()["accepted"] == 50


def test_timestamps_from_the_browser_are_checked(api_client):
    now = timezone.now()
    api_client.post(
        EVENTS,
        {
            "events": [
                view_event(occurred_at=(now + timedelta(days=2)).isoformat()),
                view_event(occurred_at=(now - timedelta(days=9)).isoformat()),
                view_event(occurred_at=(now - timedelta(minutes=5)).isoformat()),
            ]
        },
    )
    times = sorted(AnalyticsEvent.objects.values_list("occurred_at", flat=True))
    assert all(t <= timezone.now() for t in times)
    assert all(t > now - timedelta(hours=1) for t in times)


def test_nothing_is_recorded_for_a_member_who_opted_out_but_the_call_succeeds(
    make_user, client_for
):
    member = make_user(email="a@example.com")
    services.set_opt_out(member.pk, True)
    response = client_for(member).post(EVENTS, {"events": [view_event()]})
    assert response.status_code == 202
    assert AnalyticsEvent.objects.count() == 0


def test_the_endpoint_sets_no_cookies_and_is_not_cacheable(api_client):
    response = api_client.post(EVENTS, {"events": [view_event()]})
    assert not response.cookies


def test_reporting_is_rate_limited(api_client, monkeypatch):
    monkeypatch.setattr(
        ScopedRateThrottle,
        "THROTTLE_RATES",
        {**ScopedRateThrottle.THROTTLE_RATES, "analytics": "2/min"},
    )
    statuses = [api_client.post(EVENTS, {"events": [view_event()]}).status_code for _ in range(3)]
    assert statuses == [202, 202, 429]


# --- opting out ---


def test_preferences_default_to_taking_part(make_user, client_for):
    assert client_for(make_user(email="a@example.com")).get(PREFERENCES).json() == {
        "opt_out": False
    }


def test_a_member_can_opt_out_and_back_in(make_user, client_for):
    member = make_user(email="a@example.com")
    client = client_for(member)
    assert client.put(PREFERENCES, {"opt_out": True}).json() == {"opt_out": True}
    assert client.get(PREFERENCES).json() == {"opt_out": True}
    assert services.is_opted_out(member.pk)
    assert client.put(PREFERENCES, {"opt_out": False}).json() == {"opt_out": False}
    assert not services.is_opted_out(member.pk)


def test_preferences_need_a_login(api_client):
    assert api_client.get(PREFERENCES).status_code == 401
    assert api_client.put(PREFERENCES, {"opt_out": True}).status_code == 401


@pytest.mark.parametrize("body", [{}, {"opt_out": "maybe"}, {"opt_out": True, "extra": 1}])
def test_invalid_preference_changes_are_refused(make_user, client_for, body):
    assert client_for(make_user(email="a@example.com")).put(PREFERENCES, body).status_code == 400


def test_one_member_cannot_change_anothers_preference(make_user, client_for):
    mine, theirs = make_user(email="a@example.com"), make_user(email="b@example.com")
    client_for(mine).put(PREFERENCES, {"opt_out": True})
    assert not services.is_opted_out(theirs.pk)
