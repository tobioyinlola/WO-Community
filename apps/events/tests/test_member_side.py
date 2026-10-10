import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.core.etag import etag_for
from apps.events import services
from apps.events.models import Event, EventRegistration
from apps.events.tests.conftest import EVENTS, active, make_event
from apps.notifications.models import Notification

pytestmark = pytest.mark.django_db


def url(event, tail=""):
    return f"{EVENTS}/{event.pk}{tail}"


def register(client, event):
    return client.post(url(event, "/register"))


# --- browsing ---


def test_upcoming_events_are_listed_soonest_first_and_past_ones_archived(admin, member_client):
    soon = make_event(
        admin,
        title="Soon",
        starts_at=timezone.now() + timedelta(days=1),
        ends_at=timezone.now() + timedelta(days=1, hours=1),
    )
    later = make_event(
        admin,
        title="Later",
        starts_at=timezone.now() + timedelta(days=9),
        ends_at=timezone.now() + timedelta(days=9, hours=1),
    )
    done = make_event(admin, title="Done")
    Event.objects.filter(pk=done.pk).update(
        starts_at=timezone.now() - timedelta(days=2),
        ends_at=timezone.now() - timedelta(days=2) + timedelta(hours=1),
    )
    assert [e["title"] for e in member_client.get(EVENTS).json()["results"]] == ["Soon", "Later"]
    assert [e["title"] for e in member_client.get(EVENTS, {"when": "past"}).json()["results"]] == [
        "Done"
    ]
    assert soon.pk and later.pk


def test_the_list_can_be_filtered_by_type_and_registration_and_paged(admin, member_client):
    for i in range(3):
        make_event(
            admin,
            title=f"W{i}",
            starts_at=timezone.now() + timedelta(days=i + 1),
            ends_at=timezone.now() + timedelta(days=i + 1, hours=1),
        )
    meetup = make_event(admin, title="Meetup", type="meetup")
    assert [
        e["title"] for e in member_client.get(EVENTS, {"type": "meetup"}).json()["results"]
    ] == ["Meetup"]
    register(member_client, meetup)
    assert [
        e["title"] for e in member_client.get(EVENTS, {"registered": "true"}).json()["results"]
    ] == ["Meetup"]
    seen, cursor = [], ""
    while True:
        page = member_client.get(EVENTS, {"limit": 2, "cursor": cursor}).json()
        seen += [e["title"] for e in page["results"]]
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert len(seen) == 4 and seen[0] == "W0"


@pytest.mark.parametrize(
    "params", [{"when": "now"}, {"type": "party"}, {"limit": 0}, {"cursor": "x"}, {"x": 1}]
)
def test_bad_queries_are_refused(member_client, params):
    assert member_client.get(EVENTS, params).status_code == 400


def test_drafts_and_removed_events_are_invisible_but_cancelled_ones_explain_themselves(
    admin, member_client
):
    draft = make_event(admin, publish=False)
    gone = make_event(admin)
    services.remove(actor=admin, event_id=gone.pk)
    cancelled = make_event(admin)
    services.cancel(actor=admin, event_id=cancelled.pk)
    assert member_client.get(url(draft)).status_code == 404
    assert member_client.get(url(gone)).status_code == 404
    assert member_client.get(url(cancelled)).json()["status"] == "cancelled"


def test_an_event_shows_what_a_member_needs(event, member_client, other_client):
    body = member_client.get(url(event)).json()
    assert body["title"] == "Pitch practice workshop" and body["timezone"] == "Africa/Lagos"
    assert body["link"] == "https://meet.example.com/pitch" and "pitch" in body["description"]
    assert body["capacity"] is None and body["spots_left"] is None
    assert body["registered_count"] == 0 and body["registered"] is False
    assert body["registration_open"] is True and body["past"] is False
    assert body["recording_url"] == "" and body["slots"] == []


def test_the_events_area_is_for_active_members(api_client, make_user, client_for, event):
    assert api_client.get(EVENTS).status_code == 401
    pending = client_for(make_user(email="p@example.com", status="pending"))
    assert pending.get(EVENTS).status_code == 403
    assert pending.post(url(event, "/register")).status_code == 403


# --- registering ---


def test_registering_confirms_counts_and_is_idempotent(
    event, member_client, other_client, member, run_outbox, sent_emails
):
    first = register(member_client, event)
    assert first.status_code == 201
    assert first.json() == {
        "event_id": str(event.pk),
        "registered": True,
        "registered_count": 1,
        "spots_left": None,
    }
    assert register(member_client, event).status_code == 200
    register(other_client, event)
    assert other_client.get(url(event)).json()["registered_count"] == 2
    assert member_client.get(url(event)).json()["registered"] is True
    run_outbox()
    run_outbox()
    assert Notification.objects.filter(user=member, type="event_registered").count() == 1
    assert any("registered for Pitch practice workshop" in m.subject for m in sent_emails)


def test_a_member_can_cancel_their_registration(event, member_client):
    register(member_client, event)
    gone = member_client.delete(url(event, "/register"))
    assert (
        gone.status_code == 200
        and gone.json()["registered"] is False
        and gone.json()["registered_count"] == 0
    )
    assert member_client.delete(url(event, "/register")).status_code == 200  # idempotent
    assert EventRegistration.objects.count() == 0


def test_capacity_is_enforced_and_freed_by_cancelling(admin, member_client, other_client):
    event = make_event(admin, capacity=1)
    assert register(member_client, event).status_code == 201
    assert member_client.get(url(event)).json()["spots_left"] == 0
    full = register(other_client, event)
    assert full.status_code == 409
    member_client.delete(url(event, "/register"))
    assert register(other_client, event).status_code == 201


def test_registration_can_be_closed(admin, member_client):
    event = make_event(admin, registration_open=False)
    assert register(member_client, event).status_code == 409
    assert member_client.get(url(event)).json()["registration_open"] is False


def test_you_cannot_register_for_unpublished_cancelled_or_started_events(admin, member_client):
    draft = make_event(admin, publish=False)
    cancelled = make_event(admin)
    services.cancel(actor=admin, event_id=cancelled.pk)
    started = make_event(admin)
    Event.objects.filter(pk=started.pk).update(starts_at=timezone.now() - timedelta(minutes=5))
    assert register(member_client, draft).status_code == 404
    assert register(member_client, cancelled).status_code == 404
    assert register(member_client, started).status_code == 409
    assert register(member_client, type("E", (), {"pk": uuid.uuid4()})).status_code == 404


def test_registration_cannot_be_cancelled_after_the_start(event, member_client):
    register(member_client, event)
    Event.objects.filter(pk=event.pk).update(starts_at=timezone.now() - timedelta(minutes=1))
    assert member_client.delete(url(event, "/register")).status_code == 409


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
@pytest.mark.usefixtures("truncate_audit")
def test_many_people_registering_at_once_never_exceed_capacity(admin, make_user):
    from concurrent.futures import ThreadPoolExecutor

    from django.db import connections

    event = make_event(admin, capacity=3)
    users = [active(make_user, f"u{i}@example.com") for i in range(8)]

    def go(user):
        try:
            return services.register(user_id=user.pk, event_id=event.pk)
        except Exception:  # the ones refused because it is full
            return None
        finally:
            connections.close_all()

    with ThreadPoolExecutor(8) as pool:
        list(pool.map(go, users))
    assert EventRegistration.objects.filter(event=event).count() == 3


# --- the calendar file ---


def test_the_calendar_file_has_the_event_in_utc(event, member_client):
    response = member_client.get(url(event, "/calendar.ics"))
    assert response.status_code == 200 and response["Content-Type"].startswith("text/calendar")
    text = response.content.decode()
    assert "BEGIN:VEVENT" in text and "SUMMARY:Pitch practice workshop" in text
    assert f"UID:{event.pk}@wocommunity" in text and "LOCATION:Yaba\\, Lagos" in text
    assert "DTSTART:" in text and text.count("Z\r\n") >= 3
    assert text.endswith("END:VCALENDAR\r\n") and "\r\n" in text
    assert response["Content-Disposition"].endswith('.ics"')


def test_calendar_text_is_escaped(admin, member_client):
    event = make_event(admin, title="A; B, C\nD", location="Room 1\\2")
    text = member_client.get(url(event, "/calendar.ics")).content.decode()
    assert "SUMMARY:A\\; B\\, C D" in text or "SUMMARY:A\\; B\\, C" in text
    assert "\nD" not in text.split("SUMMARY:")[1].split("\r\n")[0]


def test_the_calendar_file_needs_a_visible_event_and_an_active_member(
    admin, api_client, member_client
):
    draft = make_event(admin, publish=False)
    assert member_client.get(url(draft, "/calendar.ics")).status_code == 404
    assert api_client.get(url(draft, "/calendar.ics")).status_code == 401


# --- demo days and the archive ---


def test_a_demo_day_lists_its_presenters_in_pitch_order(admin, member_client, other_client):
    from apps.startups.tests.conftest import STARTUPS, new_startup_body

    a = other_client.post(STARTUPS, new_startup_body(name="Alpha")).json()["id"]
    b = other_client.post(STARTUPS, new_startup_body(name="Beta")).json()["id"]
    event = make_event(admin, type="demo_day")
    services.set_slots(
        actor=admin,
        event_id=event.pk,
        slots=[
            {"startup_id": uuid.UUID(b), "pitch_link": "https://pitch.example.com/b"},
            {"startup_id": uuid.UUID(a)},
        ],
    )
    slots = member_client.get(url(event)).json()["slots"]
    assert [(s["position"], s["startup"]["name"]) for s in slots] == [(1, "Beta"), (2, "Alpha")]
    assert slots[0]["pitch_link"] == "https://pitch.example.com/b"


def test_past_events_carry_their_recording_and_summary(admin, member_client):
    event = make_event(
        admin, recording_url="https://video.example.com/r", summary="<p>What we learned</p>"
    )
    assert member_client.get(url(event)).json()["recording_url"] == ""  # not until it is over
    Event.objects.filter(pk=event.pk).update(
        starts_at=timezone.now() - timedelta(days=1), ends_at=timezone.now() - timedelta(hours=20)
    )
    past = member_client.get(url(event)).json()
    assert past["past"] is True and past["recording_url"] == "https://video.example.com/r"
    assert past["summary"] == "<p>What we learned</p>" and past["registration_open"] is False


# --- reminders ---


def reminders(user):
    return list(Notification.objects.filter(user=user, type="event_reminder"))


def start_in(event, **delta):
    now = timezone.now()
    Event.objects.filter(pk=event.pk).update(
        starts_at=now + timedelta(**delta), ends_at=now + timedelta(**delta) + timedelta(hours=1)
    )
    EventRegistration.objects.filter(event=event).update(created_at=now - timedelta(days=10))


def test_registrants_are_reminded_a_day_and_an_hour_before_once_each(
    event, member_client, member, run_outbox
):
    register(member_client, event)
    start_in(event, hours=23)
    assert services.send_reminders() == 1
    assert services.send_reminders() == 0
    start_in(event, minutes=50)
    assert services.send_reminders() == 1
    run_outbox()
    titles = [n["title"] for n in member_client.get("/api/v1/notifications").json()["results"]]
    assert any("starts in 24 hours" in t for t in titles) and any(
        "starts in 1 hour" in t for t in titles
    )
    assert len(reminders(member)) == 2


def test_nothing_is_sent_early_or_for_unregistered_members(event, member_client, other, member):
    register(member_client, event)
    start_in(event, days=2)
    assert services.send_reminders() == 0
    start_in(event, hours=20)
    services.send_reminders()
    assert reminders(other) == []


def test_late_registrants_skip_the_reminder_their_confirmation_covered(
    event, member_client, member
):
    start_in(event, hours=10)
    register(member_client, event)  # registered inside the 24 hour window
    assert services.send_reminders() == 0
    assert reminders(member) == []


def test_cancelled_events_and_unregistered_members_get_no_reminders(admin, member_client, member):
    event = make_event(admin)
    register(member_client, event)
    start_in(event, hours=5)
    services.cancel(actor=admin, event_id=event.pk)
    assert services.send_reminders() == 0


def test_reminders_respect_notification_preferences(event, member_client, member):
    register(member_client, event)
    member_client.put(
        "/api/v1/me/notification-preferences",
        {"preferences": {"event_reminders": {"in_app": False, "email": False}}},
        format="json",
    )
    start_in(event, hours=5)
    services.send_reminders()
    assert reminders(member) == []


# --- cancellation and rescheduling notices ---


def test_cancelling_tells_everyone_registered(
    admin, event, member_client, other_client, member, other, run_outbox
):
    register(member_client, event)
    register(other_client, event)
    services.cancel(actor=admin, event_id=event.pk, reason="Venue flooded")
    run_outbox()
    for user in (member, other):
        [notice] = Notification.objects.filter(user=user, type="event_cancelled")
        assert notice.payload["title"] == "Pitch practice workshop"


def test_changing_the_times_tells_registrants_and_resets_reminders(
    admin, event, member_client, member, run_outbox
):
    register(member_client, event)
    EventRegistration.objects.update(reminded_24h_at=timezone.now())
    new_start = timezone.now() + timedelta(days=5)
    services.update_event(
        actor=admin,
        event_id=event.pk,
        data={"starts_at": new_start, "ends_at": new_start + timedelta(hours=1)},
        if_match=etag_for(Event.objects.get(pk=event.pk)),
    )
    run_outbox()
    assert Notification.objects.filter(user=member, type="event_rescheduled").count() == 1
    assert EventRegistration.objects.get().reminded_24h_at is None
