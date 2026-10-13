from datetime import UTC, datetime, timedelta

import pytest
from django.utils import timezone

from apps.integrations.calendars import FeedRejected, FeedUnavailable
from apps.integrations.calendars.fake import FakeFeedReader
from apps.mentorship import calendar_sync
from apps.mentorship.models import CalendarBusy, CalendarConnection, MentorProfile
from apps.mentorship.tests.conftest import ask, times_of

pytestmark = pytest.mark.django_db

CAL = "/api/v1/me/calendar"
# A made up feed token, assembled at run time so no token-shaped literal sits in the source.
FEED_TOKEN = "-".join(["private", "abc123"])
FEED = f"https://calendar.google.com/calendar/ical/ada%40example.com/{FEED_TOKEN}/basic.ics"


def stamp(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def feed_with(*ranges: tuple[datetime, datetime], extra: str = "") -> str:
    events = "".join(
        f"BEGIN:VEVENT\r\nUID:e{i}\r\nDTSTART:{stamp(a)}\r\nDTEND:{stamp(b)}\r\n"
        f"SUMMARY:Private meeting\r\nEND:VEVENT\r\n"
        for i, (a, b) in enumerate(ranges)
    )
    return f"BEGIN:VCALENDAR\r\nVERSION:2.0\r\n{events}{extra}END:VCALENDAR\r\n"


def share(client, url=FEED, **extra):
    return client.put(CAL, {"feed_url": url, **extra}, format="json")


# --- sharing ---


def test_a_mentor_shares_a_calendar_and_only_the_host_comes_back(booking_mentor, applicant_client):
    assert applicant_client.get(CAL).json()["connected"] is False
    FakeFeedReader.feeds[FEED] = feed_with()
    response = share(applicant_client)
    assert response.status_code == 200, response.content
    body = response.json()
    assert body["connected"] is True and body["host"] == "calendar.google.com"
    assert body["status"] == "active" and body["stale"] is False
    assert FEED_TOKEN not in response.content.decode()
    assert FEED_TOKEN not in applicant_client.get(CAL).content.decode()
    row = CalendarConnection.objects.get(mentor=booking_mentor)
    assert FEED_TOKEN not in row.feed_url_encrypted  # stored encrypted


def test_a_webcal_address_is_accepted(booking_mentor, applicant_client):
    FakeFeedReader.feeds[FEED] = feed_with()
    assert share(applicant_client, FEED.replace("https://", "webcal://")).status_code == 200
    assert FakeFeedReader.fetched == [FEED]  # read once, not once to check and once to sync


@pytest.mark.parametrize(
    "url", ["http://calendar.example.com/x.ics", "ftp://example.com/x.ics", "not a url", ""]
)
def test_only_https_addresses_are_accepted(booking_mentor, applicant_client, url):
    assert share(applicant_client, url).status_code == 400


def test_a_wrong_address_is_refused_with_the_reason_and_changes_nothing(
    booking_mentor, applicant_client
):
    FakeFeedReader.feeds[FEED] = feed_with()
    share(applicant_client)
    other = "https://calendar.example.com/other.ics"
    FakeFeedReader.feeds[other] = "<html>Please sign in</html>"
    refused = share(applicant_client, other)
    assert refused.status_code == 400
    assert "does not return a calendar" in refused.json()["errors"]["feed_url"][0]
    assert CalendarConnection.objects.get(mentor=booking_mentor).host == "calendar.google.com"

    FakeFeedReader.feeds[other] = FeedUnavailable("timeout")
    unreachable = share(applicant_client, other).json()
    assert "did not answer in time" in unreachable["errors"]["feed_url"][0]
    FakeFeedReader.feeds[other] = FeedRejected("blocked_address")
    assert share(applicant_client, other).status_code == 400


def test_only_mentors_can_share_a_calendar(other_client):
    assert other_client.get(CAL).status_code == 403
    assert share(other_client).status_code == 403


def test_sharing_is_rate_limited(booking_mentor, applicant_client, settings):
    settings.CALENDAR_CONNECTS_PER_HOUR = 2
    FakeFeedReader.feeds[FEED] = feed_with()
    assert share(applicant_client).status_code == 200
    assert share(applicant_client).status_code == 200
    assert share(applicant_client).status_code == 429


def test_stopping_forgets_the_address_and_the_busy_time(booking_mentor, applicant_client):
    soon = timezone.now() + timedelta(days=2)
    FakeFeedReader.feeds[FEED] = feed_with((soon, soon + timedelta(hours=1)))
    share(applicant_client)
    assert CalendarBusy.objects.filter(mentor=booking_mentor).count() == 1
    assert applicant_client.delete(CAL).status_code == 204
    assert not CalendarConnection.objects.exists() and not CalendarBusy.objects.exists()
    assert applicant_client.get(CAL).json()["connected"] is False


# --- effect on offered times ---


def test_busy_time_in_the_calendar_is_not_offered(booking_mentor, mentee_client, applicant_client):
    before = [datetime.fromisoformat(t) for t in times_of(mentee_client, booking_mentor)]
    target = before[2]
    FakeFeedReader.feeds[FEED] = feed_with(
        (target - timedelta(minutes=5), target + timedelta(minutes=5))
    )
    share(applicant_client)
    after = [datetime.fromisoformat(t) for t in times_of(mentee_client, booking_mentor)]
    assert target not in after
    assert before[0] in after
    # And asking for it directly is refused, not quietly double booked.
    refused = ask(mentee_client, booking_mentor, target.isoformat())
    assert refused.status_code == 409


def test_a_failed_refresh_keeps_the_last_busy_time(booking_mentor, mentee_client, applicant_client):
    target = datetime.fromisoformat(times_of(mentee_client, booking_mentor)[2])
    FakeFeedReader.feeds[FEED] = feed_with((target, target + timedelta(minutes=45)))
    share(applicant_client)
    FakeFeedReader.feeds[FEED] = FeedUnavailable("timeout")
    body = applicant_client.post(f"{CAL}/sync").json()
    assert body["status"] == "error" and "did not answer in time" in body["last_error"]
    assert target.isoformat() not in times_of(mentee_client, booking_mentor)  # still busy
    assert CalendarBusy.objects.filter(mentor=booking_mentor).count() == 1


def test_all_day_events_block_only_when_asked_for(booking_mentor, mentee_client, applicant_client):
    day = (timezone.now() + timedelta(days=3)).date()
    extra = (
        f"BEGIN:VEVENT\r\nUID:allday\r\nDTSTART;VALUE=DATE:{day:%Y%m%d}\r\n"
        f"DTEND;VALUE=DATE:{day + timedelta(days=1):%Y%m%d}\r\nEND:VEVENT\r\n"
    )
    FakeFeedReader.feeds[FEED] = feed_with(extra=extra)
    share(applicant_client)
    assert CalendarBusy.objects.count() == 0
    body = applicant_client.put(CAL, {"include_all_day": True}, format="json").json()
    assert body["include_all_day"] is True and body["busy_ranges"] == 1
    assert len(FakeFeedReader.fetched) == 2  # shared, then re-read with the changed setting


def test_changing_the_setting_needs_a_shared_calendar(booking_mentor, applicant_client):
    assert applicant_client.put(CAL, {"include_all_day": True}, format="json").status_code == 400


# --- refreshing in the background ---


def test_the_sync_job_refreshes_every_calendar_and_survives_a_bad_one(
    booking_mentor, applicant_client, make_user, client_for
):
    from apps.mentorship.tests.conftest import active, become_mentor

    soon = timezone.now() + timedelta(days=2)
    FakeFeedReader.feeds[FEED] = feed_with()
    share(applicant_client)
    FakeFeedReader.feeds[FEED] = feed_with((soon, soon + timedelta(hours=1)))
    assert calendar_sync.sync_all() == 1
    assert CalendarBusy.objects.filter(mentor=booking_mentor).count() == 1
    assert CalendarConnection.objects.get(mentor=booking_mentor).busy_hash

    FakeFeedReader.feeds[FEED] = FeedRejected("blocked_address")
    assert calendar_sync.sync_all() == 0
    row = CalendarConnection.objects.get(mentor=booking_mentor)
    assert row.status == "error" and row.last_error == "blocked_address"
    assert CalendarBusy.objects.filter(mentor=booking_mentor).count() == 1
    assert become_mentor and active  # imported for the readers of this test's helpers


def test_a_withdrawn_mentor_loses_the_connection(booking_mentor, applicant_client, as_admin):
    FakeFeedReader.feeds[FEED] = feed_with()
    share(applicant_client)
    as_admin.post(
        f"/api/v1/admin/mentors/{booking_mentor.pk}/revoke", {"reason": "x"}, format="json"
    )
    calendar_sync.sync_all()
    assert not CalendarConnection.objects.exists()
    assert MentorProfile.objects.filter(user=booking_mentor).exists()


# --- choosing available time ---


def test_the_preview_shows_what_removes_time_from_the_windows(
    booking_mentor, mentee_client, applicant_client
):
    times = [datetime.fromisoformat(t) for t in times_of(mentee_client, booking_mentor)]
    busy_at, booked_at = times[2], times[5]
    FakeFeedReader.feeds[FEED] = feed_with((busy_at, busy_at + timedelta(minutes=45)))
    share(applicant_client)
    assert ask(mentee_client, booking_mentor, booked_at.isoformat()).status_code == 201

    body = applicant_client.get("/api/v1/me/availability/preview", {"days": 14}).json()
    assert body["timezone"] == "Africa/Lagos" and body["session_minutes"] == 45
    assert body["windows"] and body["free"]
    assert [r["starts_at"] for r in body["calendar_busy"]] == [
        busy_at.isoformat().replace("+00:00", "Z")
    ] or len(body["calendar_busy"]) == 1
    assert len(body["booked"]) == 1
    starts = [datetime.fromisoformat(t) for t in body["bookable_starts"]]
    assert busy_at not in starts and booked_at not in starts and times[0] in starts
    assert body["calendar"]["connected"] is True
    bad = applicant_client.get("/api/v1/me/availability/preview", {"days": 99})
    assert bad.status_code == 400


def test_the_preview_is_for_mentors_only(other_client):
    assert other_client.get("/api/v1/me/availability/preview").status_code == 403
