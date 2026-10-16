from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.db import connections
from django.utils import timezone

from apps.mentorship import scheduling, setup
from apps.mentorship.models import (
    AvailabilityException,
    AvailabilitySlot,
    MentorProfile,
    MentorSession,
    MentorSettings,
)
from apps.mentorship.tests.conftest import active, ask, times_of

pytestmark = pytest.mark.django_db

ME = "/api/v1/me/mentor"
NIL = "00000000-0000-0000-0000-000000000001"
WEEKDAYS = [{"weekday": d, "start": "09:00", "end": "12:00"} for d in range(5)]


@pytest.fixture
def mentor_client(booking_mentor, applicant_client):
    return applicant_client


@pytest.fixture
def profile(booking_mentor):
    return MentorProfile.objects.get(user=booking_mentor)


def settings_of(client):
    response = client.get(f"{ME}/settings")
    assert response.status_code == 200, response.content
    return response.json()


# --- who may call what ---

ENDPOINTS = [
    ("get", f"{ME}/settings", None),
    ("put", f"{ME}/settings", {"buffer_minutes": 10}),
    ("get", f"{ME}/availability", None),
    ("put", f"{ME}/availability", {"weekly": WEEKDAYS}),
    ("post", f"{ME}/exceptions", {"type": "blocked", "starts_on": "2030-01-01"}),
    ("delete", f"{ME}/exceptions/{NIL}", None),
    ("get", f"{ME}/preview", None),
]


def call(client, method, path, payload=None):
    send = getattr(client, method)
    return send(path, payload, format="json") if payload is not None else send(path)


@pytest.mark.parametrize("method,path,payload", ENDPOINTS)
def test_signing_in_is_required(api_client, method, path, payload):
    assert call(api_client, method, path, payload).status_code == 401


@pytest.mark.parametrize("method,path,payload", ENDPOINTS)
def test_only_an_approved_mentor_may_use_them(other_client, method, path, payload):
    assert call(other_client, method, path, payload).status_code == 403


def test_a_revoked_mentor_is_refused(mentor_client, profile):
    MentorProfile.objects.filter(pk=profile.pk).update(status="revoked")
    assert mentor_client.get(f"{ME}/settings").status_code == 403


def test_slots_need_sign_in_and_an_existing_mentor(api_client, mentee_client):
    assert api_client.get(f"/api/v1/mentors/{NIL}/slots").status_code == 401
    assert mentee_client.get(f"/api/v1/mentors/{NIL}/slots").status_code == 404


# --- the settings ---


def test_the_settings_start_from_what_the_mentor_already_had(mentor_client):
    body = settings_of(mentor_client)
    assert body["session_lengths"] == [45] and body["default_length"] == 45
    assert body["buffer_minutes"] == 0 and body["pricing_mode"] == "free"
    assert body["accepting_new"] is True and body["timezone"] == "Africa/Lagos"
    assert len(body["weekly"]) == 7 and body["payments_enabled"] is False
    assert body["options"]["currencies"] == ["NGN", "USD", "KES", "GHS", "ZAR", "EGP", "GBP", "EUR"]
    assert MentorSettings.objects.count() == 1


def test_settings_are_saved(mentor_client):
    response = mentor_client.put(
        f"{ME}/settings",
        {
            "session_lengths": [30, 60],
            "default_length": 30,
            "buffer_minutes": 15,
            "min_notice_hours": 24,
            "max_per_week": 5,
            "booking_window_days": 14,
            "about": "I help founders raise.",
            "topics": ["Pitch decks", "Term sheets"],
            "meeting_provider": "zoom",
        },
        format="json",
    )
    assert response.status_code == 200, response.content
    body = response.json()
    assert body["session_lengths"] == [30, 60] and body["default_length"] == 30
    assert body["buffer_minutes"] == 15 and body["min_notice_hours"] == 24
    assert body["max_per_week"] == 5 and body["booking_window_days"] == 14
    assert body["topics"] == ["Pitch decks", "Term sheets"] and body["meeting_provider"] == "zoom"


@pytest.mark.parametrize(
    "payload",
    [
        {"session_lengths": []},
        {"session_lengths": [20]},
        {"default_length": 90},
        {"buffer_minutes": 7},
        {"min_notice_hours": 5},
        {"booking_window_days": 3},
        {"max_per_week": 0},
        {"pricing_mode": "gift"},
        {"pricing_mode": "paid"},  # no price or currency yet
        {"pricing_mode": "paid", "currency": "XXX", "default_price_minor": 1000},
        {"pricing_mode": "paid", "currency": "NGN", "default_price_minor": 0},
        {"prices": [{"length_minutes": 45, "price_minor": 0}]},
        {
            "prices": [
                {"length_minutes": 45, "price_minor": 10},
                {"length_minutes": 45, "price_minor": 20},
            ]
        },
        {"meeting_provider": "teams"},
        {"meeting_provider": "personal"},  # needs a link
        {"personal_link": "javascript:alert(1)"},
        {"topics": ["x"]},
        {"timezone": "Mars/Base"},
        {"colour": "red"},
    ],
)
def test_bad_settings_are_refused_and_nothing_changes(mentor_client, payload):
    before = settings_of(mentor_client)
    assert mentor_client.put(f"{ME}/settings", payload, format="json").status_code == 400
    assert settings_of(mentor_client) == before


def test_pricing_per_length_and_a_personal_link(mentor_client):
    mentor_client.put(f"{ME}/settings", {"session_lengths": [30, 45, 60]}, format="json")
    response = mentor_client.put(
        f"{ME}/settings",
        {
            "pricing_mode": "paid",
            "currency": "NGN",
            "default_price_minor": 2_000_000,
            "prices": [{"length_minutes": 60, "price_minor": 3_000_000}],
            "meeting_provider": "personal",
            "personal_link": "https://meet.example.com/ada",
        },
        format="json",
    )
    assert response.status_code == 200, response.content
    body = response.json()
    assert body["pricing_mode"] == "paid" and body["prices"] == [
        {"length_minutes": 60, "price_minor": 3_000_000}
    ]
    assert body["personal_link"] == "https://meet.example.com/ada"


def test_accepting_mentees_needs_a_weekly_range(mentor_client):
    mentor_client.put(f"{ME}/settings", {"accepting_new": False}, format="json")
    mentor_client.put(f"{ME}/availability", {"weekly": []}, format="json")
    assert (
        mentor_client.put(f"{ME}/settings", {"accepting_new": True}, format="json").status_code
        == 400
    )
    assert (
        mentor_client.put(f"{ME}/availability", {"weekly": WEEKDAYS}, format="json").status_code
        == 200
    )
    assert (
        mentor_client.put(f"{ME}/settings", {"accepting_new": True}, format="json").status_code
        == 200
    )


# --- the weekly schedule ---


def test_the_weekly_schedule_is_replaced_and_extras_are_kept(mentor_client, booking_mentor):
    tomorrow = (timezone.now() + timedelta(days=3)).date().isoformat()
    added = mentor_client.post(
        f"{ME}/exceptions",
        {"type": "extra", "date": tomorrow, "start": "14:00", "end": "16:00"},
        format="json",
    )
    assert added.status_code == 201, added.content
    response = mentor_client.put(
        f"{ME}/availability",
        {"weekly": WEEKDAYS, "timezone": "Africa/Nairobi"},
        format="json",
    )
    assert response.status_code == 200, response.content
    body = response.json()
    assert len(body["weekly"]) == 5 and body["timezone"] == "Africa/Nairobi"
    assert [e["type"] for e in body["exceptions"]] == ["extra"]


@pytest.mark.parametrize(
    "weekly",
    [
        [{"weekday": 0, "start": "09:00", "end": "08:00"}],
        [{"weekday": 0, "start": "09:00", "end": "09:10"}],
        [
            {"weekday": 0, "start": "09:00", "end": "11:00"},
            {"weekday": 0, "start": "10:30", "end": "12:00"},
        ],
        [{"weekday": 7, "start": "09:00", "end": "12:00"}],
        [{"weekday": 0, "start": "9am", "end": "12:00"}],
    ],
)
def test_bad_weekly_ranges_are_refused(mentor_client, weekly):
    before = settings_of(mentor_client)["weekly"]
    assert (
        mentor_client.put(f"{ME}/availability", {"weekly": weekly}, format="json").status_code
        == 400
    )
    assert settings_of(mentor_client)["weekly"] == before


# --- days off and extra time ---


def test_days_off_remove_slots_and_can_be_removed(mentor_client, booking_mentor, mentee_client):
    slots = times_of(mentee_client, booking_mentor, days=7)
    target = slots[0][:10]
    response = mentor_client.post(
        f"{ME}/exceptions",
        {"type": "blocked", "starts_on": target, "ends_on": target, "note": "Holiday"},
        format="json",
    )
    assert response.status_code == 201, response.content
    item = response.json()["exceptions"][0]
    assert item["type"] == "blocked" and item["note"] == "Holiday"
    assert all(not s.startswith(target) for s in times_of(mentee_client, booking_mentor, days=7))
    gone = mentor_client.delete(f"{ME}/exceptions/{item['id']}")
    assert gone.status_code == 200 and gone.json()["exceptions"] == []
    assert any(s.startswith(target) for s in times_of(mentee_client, booking_mentor, days=7))


@pytest.mark.parametrize(
    "payload",
    [
        {"type": "blocked"},
        {"type": "blocked", "starts_on": "2030-02-02", "ends_on": "2030-02-01"},
        {"type": "blocked", "starts_on": "2020-01-01"},
        {"type": "blocked", "starts_on": "2030-01-01", "ends_on": "2031-06-01"},
        {"type": "extra", "date": "2030-02-01"},
        {"type": "extra", "date": "2030-02-01", "start": "16:00", "end": "15:00"},
        {"type": "extra", "date": "2020-02-01", "start": "10:00", "end": "12:00"},
        {"type": "weekend"},
    ],
)
def test_bad_exceptions_are_refused(mentor_client, payload):
    assert mentor_client.post(f"{ME}/exceptions", payload, format="json").status_code == 400


def test_extra_time_on_one_date_adds_slots_and_overlaps_are_refused(
    mentor_client, booking_mentor, mentee_client
):
    day = (timezone.now() + timedelta(days=5)).date().isoformat()
    body = {"type": "extra", "date": day, "start": "20:00", "end": "22:00"}
    assert mentor_client.post(f"{ME}/exceptions", body, format="json").status_code == 201
    assert (
        mentor_client.post(
            f"{ME}/exceptions", {**body, "start": "21:00", "end": "23:00"}, format="json"
        ).status_code
        == 400
    )
    assert any(s.startswith(day) for s in times_of(mentee_client, booking_mentor, days=10))


def test_another_mentors_exception_cannot_be_removed(mentor_client, make_user, client_for):
    mentor_client.post(
        f"{ME}/exceptions", {"type": "blocked", "starts_on": "2030-01-01"}, format="json"
    )
    row = AvailabilityException.objects.get()
    stranger = client_for(active(make_user, "stranger@example.com"))
    assert stranger.delete(f"{ME}/exceptions/{row.pk}").status_code == 403
    assert AvailabilityException.objects.count() == 1


# --- slots a mentee sees ---


def test_slots_follow_length_buffer_notice_and_the_viewers_time_zone(
    mentor_client, booking_mentor, mentee_client
):
    mentor_client.put(
        f"{ME}/settings",
        {
            "session_lengths": [30, 60],
            "default_length": 60,
            "buffer_minutes": 30,
            "min_notice_hours": 48,
        },
        format="json",
    )
    response = mentee_client.get(
        f"/api/v1/mentors/{booking_mentor.pk}/slots", {"length": 30, "tz": "America/New_York"}
    )
    assert response.status_code == 200, response.content
    body = response.json()
    assert body["timezone"] == "America/New_York" and body["mentor_timezone"] == "Africa/Lagos"
    assert body["length_minutes"] == 30 and body["lengths"] == [30, 60] and body["price"] is None
    slots = body["slots"]
    assert slots
    # The notice period can cut into the first day, so look at the first full day after it.
    first = next(s for s in slots if s["local_date"] != slots[0]["local_date"])
    # 09:00 Lagos is 04:00 in New York in the (UTC-4) autumn or 03:00 once clocks fall back.
    assert first["local_time"] in ("03:00", "04:00")
    earliest = timezone.now() + timedelta(hours=48)
    assert all(datetime.fromisoformat(s["starts_at"]) >= earliest for s in slots)
    # 30 minute sessions with a 30 minute buffer step by an hour inside a 09:00 to 12:00 window.
    in_lagos = mentee_client.get(
        f"/api/v1/mentors/{booking_mentor.pk}/slots", {"length": 30, "tz": "Africa/Lagos"}
    ).json()["slots"]
    middle = in_lagos[len(in_lagos) // 2]["local_date"]
    assert [s["local_time"] for s in in_lagos if s["local_date"] == middle] == [
        "09:00",
        "10:00",
        "11:00",
    ]


def test_a_length_the_mentor_does_not_offer_is_refused(mentee_client, booking_mentor):
    response = mentee_client.get(f"/api/v1/mentors/{booking_mentor.pk}/slots", {"length": 30})
    assert response.status_code == 400


@pytest.mark.parametrize(
    "query", [{"tz": "Mars/Base"}, {"to": "2030-01-01", "from": "2029-01-01"}, {"length": "abc"}]
)
def test_bad_slot_queries_are_refused(mentee_client, booking_mentor, query):
    assert mentee_client.get(f"/api/v1/mentors/{booking_mentor.pk}/slots", query).status_code == 400


def test_a_paused_mentor_shows_no_slots(mentor_client, booking_mentor, mentee_client):
    mentor_client.put(f"{ME}/settings", {"accepting_new": False}, format="json")
    body = mentee_client.get(f"/api/v1/mentors/{booking_mentor.pk}/slots")
    assert body.status_code == 404 or body.json()["slots"] == []


def test_the_preview_shows_slots_even_while_paused(mentor_client):
    mentor_client.put(f"{ME}/settings", {"accepting_new": False}, format="json")
    body = mentor_client.get(f"{ME}/preview", {"tz": "Africa/Lagos"}).json()
    assert body["accepting_new"] is False and body["slots"]


def test_the_preview_matches_what_a_mentee_gets(mentor_client, booking_mentor, mentee_client):
    mine = mentor_client.get(f"{ME}/preview", {"tz": "Africa/Lagos"}).json()["slots"]
    theirs = mentee_client.get(
        f"/api/v1/mentors/{booking_mentor.pk}/slots", {"tz": "Africa/Lagos"}
    ).json()["slots"]
    assert mine == theirs


# --- booking with a length and a price ---


def test_a_booking_records_length_and_a_price_that_is_settled_directly(
    mentor_client, booking_mentor, mentee_client
):
    mentor_client.put(
        f"{ME}/settings",
        {
            "session_lengths": [30, 60],
            "default_length": 60,
            "pricing_mode": "paid",
            "currency": "NGN",
            "default_price_minor": 2_000_000,
            "prices": [{"length_minutes": 30, "price_minor": 1_200_000}],
        },
        format="json",
    )
    slot = mentee_client.get(f"/api/v1/mentors/{booking_mentor.pk}/slots", {"length": 30}).json()
    assert slot["price"] == {"price_minor": 1_200_000, "currency": "NGN", "payment": "arranged"}
    response = ask(mentee_client, booking_mentor, slot["slots"][0]["starts_at"], length_minutes=30)
    assert response.status_code == 201, response.content
    body = response.json()
    assert body["length_minutes"] == 30
    assert body["price"] == {"price_minor": 1_200_000, "currency": "NGN", "payment": "arranged"}
    row = MentorSession.objects.get()
    assert (row.ends_at - row.starts_at) == timedelta(minutes=30) and row.status == "requested"


def test_a_free_booking_has_no_price(mentee_client, booking_mentor):
    start = times_of(mentee_client, booking_mentor)[0]
    body = ask(mentee_client, booking_mentor, start).json()
    assert body["price"] is None and body["length_minutes"] == 45


def test_an_unoffered_length_cannot_be_booked(mentee_client, booking_mentor):
    start = times_of(mentee_client, booking_mentor)[0]
    assert ask(mentee_client, booking_mentor, start, length_minutes=30).status_code == 400


def test_a_personal_link_becomes_the_meeting_when_the_mentor_accepts(
    mentor_client, booking_mentor, mentee_client
):
    mentor_client.put(
        f"{ME}/settings",
        {"meeting_provider": "personal", "personal_link": "https://meet.example.com/ada"},
        format="json",
    )
    start = times_of(mentee_client, booking_mentor)[0]
    created = ask(mentee_client, booking_mentor, start).json()
    accepted = mentor_client.post(f"/api/v1/sessions/{created['id']}/accept")
    assert accepted.status_code == 200, accepted.content
    row = MentorSession.objects.get()
    assert row.meeting_state == "ready" and row.meeting_url == "https://meet.example.com/ada"


# --- changes that would strand agreed sessions ---


def test_a_change_that_strands_a_session_is_refused_until_acknowledged(
    mentor_client, booking_mentor, mentee_client
):
    start = times_of(mentee_client, booking_mentor)[0]
    created = ask(mentee_client, booking_mentor, start).json()
    mentor_client.post(f"/api/v1/sessions/{created['id']}/accept")
    response = mentor_client.put(f"{ME}/availability", {"weekly": []}, format="json")
    assert response.status_code == 400  # accepting needs a range
    mentor_client.put(f"{ME}/settings", {"accepting_new": False}, format="json")
    refused = mentor_client.put(f"{ME}/availability", {"weekly": []}, format="json")
    assert refused.status_code == 409
    body = refused.json()
    assert body["code"] == "schedule_conflict" and [s["id"] for s in body["sessions"]] == [
        created["id"]
    ]
    assert AvailabilitySlot.objects.filter(mentor=booking_mentor).count() == 7  # nothing changed
    kept = mentor_client.put(
        f"{ME}/availability", {"weekly": [], "acknowledge": True}, format="json"
    )
    assert kept.status_code == 200
    assert MentorSession.objects.get().status == "confirmed"  # never removed by an edit


def test_blocking_the_day_of_a_session_names_it(mentor_client, booking_mentor, mentee_client):
    start = times_of(mentee_client, booking_mentor)[0]
    created = ask(mentee_client, booking_mentor, start).json()
    day = (
        MentorSession.objects.get()
        .starts_at.astimezone(__import__("zoneinfo").ZoneInfo("Africa/Lagos"))
        .date()
        .isoformat()
    )
    refused = mentor_client.post(
        f"{ME}/exceptions", {"type": "blocked", "starts_on": day}, format="json"
    )
    assert refused.status_code == 409 and refused.json()["sessions"][0]["id"] == created["id"]
    assert AvailabilityException.objects.count() == 0


# --- two people asking for the same time at once ---


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_two_mentees_asking_for_one_slot_at_once_get_one_booking(
    booking_mentor, make_user, client_for
):
    first = client_for(active(make_user, "m1@example.com"))
    second = client_for(active(make_user, "m2@example.com"))
    start = times_of(first, booking_mentor)[0]

    def go(client):
        try:
            return ask(client, booking_mentor, start).status_code
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        codes = sorted(pool.map(go, [first, second]))
    assert codes == [201, 409]
    assert MentorSession.objects.count() == 1


def test_the_buffer_is_kept_around_a_booked_session(
    mentor_client, booking_mentor, mentee_client, profile
):
    mentor_client.put(f"{ME}/settings", {"buffer_minutes": 30}, format="json")
    start = times_of(mentee_client, booking_mentor)[0]
    assert ask(mentee_client, booking_mentor, start).status_code == 201
    row = MentorSession.objects.get()
    lagos = ZoneInfo("Africa/Lagos")
    day = row.starts_at.astimezone(lagos).date()
    p = MentorProfile.objects.get(pk=profile.pk)
    same_day = [
        s.astimezone(lagos).strftime("%H:%M")
        for s in scheduling.bookable_starts(p, days=10)
        if s.astimezone(lagos).date() == day
    ]
    # 09:00 to 09:45 is taken; with 30 minutes kept clear the next 45 minute session fits at 10:15.
    assert row.starts_at.astimezone(lagos).strftime("%H:%M") == "09:00"
    assert same_day == ["10:15"]
    assert setup.agreed_outside(p) == []


def test_weekly_windows_follow_the_clock_change_in_the_mentors_zone(profile):
    from datetime import UTC

    MentorProfile.objects.filter(pk=profile.pk).update(timezone="Europe/London")
    AvailabilitySlot.objects.filter(mentor=profile.user).delete()
    mentor_client_rows = [
        AvailabilitySlot(
            mentor=profile.user,
            kind="weekly",
            weekday=0,
            start_minute=540,
            end_minute=720,
            week_span=(540, 720),
        )
    ]
    AvailabilitySlot.objects.bulk_create(mentor_client_rows)
    p = MentorProfile.objects.get(pk=profile.pk)
    found = scheduling.windows(
        p, datetime(2026, 10, 18, tzinfo=UTC), datetime(2026, 10, 28, tzinfo=UTC)
    )
    # Monday 19 October is still summer time (09:00 is 08:00 UTC); on Monday 26 it is 09:00 UTC.
    assert [(a.day, a.hour) for a, _ in found] == [(19, 8), (26, 9)]


def test_a_free_mentor_quotes_no_price(profile):
    setup_row = setup.prefs_row(profile)
    assert setup_row.pricing_mode == "free"
    assert setup.quote(profile, 45) == {
        "mode": "free",
        "price_minor": None,
        "currency": "",
        "payment": "",
    }


def test_notices_for_a_paid_session_say_payment_is_arranged_directly(
    mentor_client, booking_mentor, mentee_client, run_outbox
):
    mentor_client.put(
        f"{ME}/settings",
        {"pricing_mode": "paid", "currency": "KES", "default_price_minor": 500_000},
        format="json",
    )
    start = times_of(mentee_client, booking_mentor)[0]
    created = ask(mentee_client, booking_mentor, start).json()
    run_outbox()
    mentor_client.post(f"/api/v1/sessions/{created['id']}/accept")
    run_outbox()
    mentor_titles = [
        n["title"] for n in mentor_client.get("/api/v1/notifications").json()["results"]
    ]
    mentee_titles = [
        n["title"] for n in mentee_client.get("/api/v1/notifications").json()["results"]
    ]
    assert any(t.endswith("Payment arranged directly") and "asked you" in t for t in mentor_titles)
    assert any(t.endswith("Payment arranged directly") and "confirmed" in t for t in mentee_titles)
