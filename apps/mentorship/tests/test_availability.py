from datetime import UTC, datetime, timedelta

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.mentorship import scheduling
from apps.mentorship.models import AvailabilitySlot, MentorProfile
from apps.mentorship.tests.conftest import active, application_body

pytestmark = pytest.mark.django_db

MINE = "/api/v1/me/availability"
LIST = "/api/v1/mentors"

EVERY_DAY = [{"weekday": d, "start": "09:00", "end": "12:00"} for d in range(7)]


def put(client, **body):
    return client.put(MINE, body, format="json")


def profile_of(user):
    return MentorProfile.objects.get(user=user)


@pytest.fixture
def scheduled(mentor, applicant_client):
    """A mentor free 09:00 to 12:00 every day, Lagos time (UTC+1, no clock changes)."""
    assert put(applicant_client, weekly=EVERY_DAY).status_code == 200
    return mentor


@pytest.fixture
def seeker_client(make_user, client_for):
    return client_for(active(make_user, "seeker@example.com"))


# --- editing ---


def test_a_mentor_sets_and_reads_their_schedule(mentor, applicant_client):
    later = (timezone.now() + timedelta(days=5)).replace(microsecond=0)
    response = put(
        applicant_client,
        weekly=[
            {"weekday": 2, "start": "14:00", "end": "17:00"},
            {"weekday": 0, "start": "09:00", "end": "11:00"},
        ],
        one_off=[
            {"starts_at": later.isoformat(), "ends_at": (later + timedelta(hours=2)).isoformat()}
        ],
    )
    assert response.status_code == 200
    body = applicant_client.get(MINE).json()
    assert body["timezone"] == "Africa/Lagos" and body["session_minutes"] == 45
    assert body["weekly"] == [
        {"weekday": 0, "start": "09:00", "end": "11:00"},
        {"weekday": 2, "start": "14:00", "end": "17:00"},
    ]
    assert len(body["one_off"]) == 1


def test_each_save_replaces_the_whole_schedule(scheduled, applicant_client):
    put(applicant_client, weekly=[{"weekday": 1, "start": "10:00", "end": "12:00"}])
    assert applicant_client.get(MINE).json()["weekly"] == [
        {"weekday": 1, "start": "10:00", "end": "12:00"}
    ]
    put(applicant_client)
    assert applicant_client.get(MINE).json()["weekly"] == []
    assert not AvailabilitySlot.objects.exists()


def test_the_time_zone_can_change_with_the_schedule(scheduled, applicant_client):
    response = put(applicant_client, timezone="Europe/London", weekly=EVERY_DAY)
    assert response.json()["timezone"] == "Europe/London"


@pytest.mark.parametrize(
    "body",
    [
        {"weekly": [{"weekday": 7, "start": "09:00", "end": "10:00"}]},
        {"weekly": [{"weekday": 0, "start": "9am", "end": "10:00"}]},
        {"weekly": [{"weekday": 0, "start": "25:00", "end": "26:00"}]},
        {"weekly": [{"weekday": 0, "start": "10:00", "end": "09:00"}]},
        {"weekly": [{"weekday": 0, "start": "10:00", "end": "10:30"}]},  # shorter than a session
        {"weekly": [{"weekday": 0, "start": "00:00", "end": "13:00"}]},  # longer than 12 hours
        {
            "weekly": [
                {"weekday": 0, "start": "09:00", "end": "11:00"},
                {"weekday": 0, "start": "10:00", "end": "12:00"},
            ]
        },
        {"weekly": [{"weekday": 0, "start": "09:00", "end": "10:00", "x": 1}]},
        {
            "weekly": [
                {"weekday": d % 7, "start": f"{h:02d}:00", "end": f"{h + 1:02d}:00"}
                for d in range(40)
                for h in [9 + d // 7]
            ]
        },
        {"timezone": "Mars/Base"},
        {"unknown": 1},
    ],
)
def test_invalid_schedules_are_refused_and_change_nothing(scheduled, applicant_client, body):
    before = applicant_client.get(MINE).json()
    assert put(applicant_client, **body).status_code == 400
    assert applicant_client.get(MINE).json() == before


@pytest.mark.parametrize(
    "offset_start,hours",
    [(-1, 2), (5000, 2), (24, 0.25), (24, 13)],
)
def test_one_off_windows_are_checked(mentor, applicant_client, offset_start, hours):
    start = timezone.now() + timedelta(hours=offset_start)
    response = put(
        applicant_client,
        one_off=[
            {
                "starts_at": start.isoformat(),
                "ends_at": (start + timedelta(hours=hours)).isoformat(),
            }
        ],
    )
    assert response.status_code == 400


def test_overlapping_one_off_windows_are_refused(mentor, applicant_client):
    start = timezone.now() + timedelta(days=2)
    windows = [
        {"starts_at": start.isoformat(), "ends_at": (start + timedelta(hours=2)).isoformat()},
        {
            "starts_at": (start + timedelta(hours=1)).isoformat(),
            "ends_at": (start + timedelta(hours=3)).isoformat(),
        },
    ]
    assert put(applicant_client, one_off=windows).status_code == 400


def test_the_database_itself_refuses_overlapping_windows(scheduled):
    from django.db.backends.postgresql.psycopg_any import NumericRange

    with pytest.raises(IntegrityError), transaction.atomic():
        AvailabilitySlot.objects.create(
            mentor=scheduled,
            kind="weekly",
            weekday=0,
            start_minute=600,
            end_minute=660,
            week_span=NumericRange(600, 660, "[)"),
        )


def test_only_mentors_can_edit_and_everyone_needs_login(
    api_client, other_client, applicant_client, applicant
):
    assert put(other_client, weekly=EVERY_DAY).status_code == 403
    assert other_client.get(MINE).status_code == 404
    assert api_client.get(MINE).status_code == 401
    assert api_client.put(MINE, {}, format="json").status_code == 401
    assert applicant_client.get(MINE).status_code == 404  # not yet a mentor


def test_a_revoked_mentor_cannot_edit(scheduled, applicant_client, as_admin):
    as_admin.post(f"/api/v1/admin/mentors/{scheduled.pk}/revoke", {"reason": "x"}, format="json")
    assert put(applicant_client, weekly=EVERY_DAY).status_code in (403, 404)


def test_one_mentor_cannot_change_anothers_schedule(scheduled, other_client, as_admin, other):
    created = other_client.post(
        "/api/v1/mentor-applications",
        application_body(),
        format="json",
    ).json()
    as_admin.post(
        f"/api/v1/admin/mentor-applications/{created['id']}/decision",
        {"decision": "approve"},
        format="json",
    )
    assert (
        put(other_client, weekly=[{"weekday": 1, "start": "10:00", "end": "12:00"}]).status_code
        == 200
    )
    assert AvailabilitySlot.objects.filter(mentor=scheduled).count() == 7  # untouched


def test_changing_the_session_length_is_validated_against_windows(scheduled, applicant_client):
    ok = applicant_client.put("/api/v1/me/mentor-profile", {"session_minutes": 60}, format="json")
    assert ok.status_code == 200 and ok.json()["session_minutes"] == 60
    bad = applicant_client.put("/api/v1/me/mentor-profile", {"session_minutes": 50}, format="json")
    assert bad.status_code == 400


# --- working out bookable times ---

MONDAY = datetime(2026, 10, 12, 0, 0, tzinfo=UTC)


def test_starts_step_by_the_session_length_inside_each_window(scheduled):
    starts = scheduling.bookable_starts(profile_of(scheduled), days=3, now=MONDAY)
    # Monday's window (08:00-11:00 UTC) is inside the 12 hour notice period, Tuesday's is not.
    assert starts[:5] == [
        datetime(2026, 10, 13, 8, 0, tzinfo=UTC),
        datetime(2026, 10, 13, 8, 45, tzinfo=UTC),
        datetime(2026, 10, 13, 9, 30, tzinfo=UTC),
        datetime(2026, 10, 13, 10, 15, tzinfo=UTC),
        datetime(2026, 10, 14, 8, 0, tzinfo=UTC),
    ]


def test_nothing_is_offered_inside_the_minimum_notice(scheduled):
    soon = datetime(2026, 10, 12, 7, 0, tzinfo=UTC)  # a window opens at 08:00; 12h notice applies
    starts = scheduling.bookable_starts(profile_of(scheduled), days=1, now=soon)
    assert all(s >= soon + timedelta(hours=12) for s in starts)


def test_clock_changes_keep_the_local_time(mentor, applicant_client):
    put(
        applicant_client,
        timezone="America/New_York",
        weekly=[{"weekday": d, "start": "09:00", "end": "09:45"} for d in range(7)],
    )
    profile = profile_of(mentor)
    starts = scheduling.bookable_starts(
        profile, days=14, now=datetime(2026, 10, 25, 0, 0, tzinfo=UTC)
    )
    before = [s for s in starts if s.date() <= datetime(2026, 10, 31).date()]
    after = [s for s in starts if s.date() >= datetime(2026, 11, 2).date()]
    assert {s.hour for s in before} == {13}  # 09:00 EDT is 13:00 UTC
    assert {s.hour for s in after} == {14}  # 09:00 EST is 14:00 UTC after the change on 1 Nov


def test_one_off_windows_add_time_and_overlaps_are_merged(scheduled, applicant_client):
    day = datetime(2026, 10, 14, 10, 0, tzinfo=UTC)
    put(
        applicant_client,
        weekly=EVERY_DAY,
        one_off=[
            {
                "starts_at": (timezone.now() + timedelta(days=3)).isoformat(),
                "ends_at": (timezone.now() + timedelta(days=3, hours=2)).isoformat(),
            }
        ],
    )
    profile = profile_of(scheduled)
    windows = scheduling.windows(profile, day, day + timedelta(days=10))
    assert windows == sorted(windows)
    assert all(a < b for a, b in windows)
    assert all(windows[i][1] < windows[i + 1][0] for i in range(len(windows) - 1))


def test_booked_and_busy_time_is_removed(scheduled, monkeypatch):
    profile = profile_of(scheduled)
    taken = (datetime(2026, 10, 13, 8, 30, tzinfo=UTC), datetime(2026, 10, 13, 9, 0, tzinfo=UTC))
    monkeypatch.setattr(scheduling, "booked_intervals", lambda *a: [taken])
    starts = scheduling.bookable_starts(profile, days=2, now=MONDAY)
    assert datetime(2026, 10, 13, 8, 0, tzinfo=UTC) not in starts  # would run into 08:30
    assert datetime(2026, 10, 13, 9, 0, tzinfo=UTC) in starts  # free time restarts afterwards
    monkeypatch.setattr(
        scheduling, "external_busy", lambda *a: [(taken[0], taken[0] + timedelta(hours=2))]
    )
    again = scheduling.bookable_starts(profile, days=2, now=MONDAY)
    assert all(not (taken[0] <= s < taken[0] + timedelta(hours=2)) for s in again)


def test_is_bookable_matches_the_offered_times(scheduled):
    profile = profile_of(scheduled)
    offered = scheduling.bookable_starts(profile, days=2, now=MONDAY)[0]
    assert scheduling.is_bookable(profile, offered, now=MONDAY)
    assert not scheduling.is_bookable(profile, offered + timedelta(minutes=10), now=MONDAY)
    assert not scheduling.is_bookable(profile, MONDAY, now=MONDAY)  # inside the notice period
    far = MONDAY + timedelta(days=90)
    assert not scheduling.is_bookable(profile, far.replace(hour=8), now=MONDAY)


def test_the_horizon_caps_how_far_ahead_times_are_offered(scheduled):
    starts = scheduling.bookable_starts(profile_of(scheduled), days=365, now=MONDAY)
    assert max(starts) <= MONDAY + timedelta(days=60)


# --- seeing a mentor's times ---


def test_members_see_a_listed_mentors_times(scheduled, seeker_client):
    body = seeker_client.get(f"{LIST}/{scheduled.pk}/availability").json()
    assert body["session_minutes"] == 45 and body["sessions_left_this_week"] == 3
    assert body["times"] and body["times"] == sorted(body["times"])
    assert seeker_client.get(f"{LIST}/{scheduled.pk}/availability", {"days": 31}).status_code == 400
    assert seeker_client.get(f"{LIST}/{scheduled.pk}/availability", {"days": 0}).status_code == 400


def test_no_times_when_paused_or_full(scheduled, applicant_client, seeker_client, monkeypatch):
    monkeypatch.setattr(scheduling, "sessions_in_week", lambda *a: 3)
    body = applicant_client.get(f"{LIST}/{scheduled.pk}/availability").json()
    assert body["times"] == [] and body["sessions_left_this_week"] == 0


def test_a_paused_mentor_is_hidden_from_others_but_not_from_themselves(
    scheduled, applicant_client, seeker_client
):
    applicant_client.put("/api/v1/me/mentor-profile", {"paused": True}, format="json")
    assert seeker_client.get(f"{LIST}/{scheduled.pk}/availability").status_code == 404
    assert applicant_client.get(f"{LIST}/{scheduled.pk}/availability").json()["times"] == []


def test_availability_needs_login_and_a_real_mentor(api_client, seeker_client, other):
    import uuid

    assert api_client.get(f"{LIST}/{uuid.uuid4()}/availability").status_code == 401
    assert seeker_client.get(f"{LIST}/{other.pk}/availability").status_code == 404


def test_the_directory_can_show_only_mentors_with_availability(
    mentor, applicant_client, seeker_client
):
    assert len(seeker_client.get(LIST).json()["results"]) == 1
    assert seeker_client.get(LIST, {"available": "true"}).json()["results"] == []
    put(applicant_client, weekly=EVERY_DAY)
    assert len(seeker_client.get(LIST, {"available": "true"}).json()["results"]) == 1
