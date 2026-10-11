from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from apps.integrations.calendars.ics import FeedInvalid, busy_intervals, unfold

LAGOS = ZoneInfo("Africa/Lagos")  # UTC+1, no clock changes
WINDOW = (datetime(2026, 11, 1, tzinfo=UTC), datetime(2026, 12, 31, tzinfo=UTC))


def calendar(*events: str) -> str:
    return "BEGIN:VCALENDAR\r\nVERSION:2.0\r\n" + "\r\n".join(events) + "\r\nEND:VCALENDAR\r\n"


def event(*lines: str) -> str:
    return "BEGIN:VEVENT\r\nUID:e1\r\n" + "\r\n".join(lines) + "\r\nEND:VEVENT"


def busy(text: str, **kwargs):
    intervals, _ = busy_intervals(
        text, window_start=WINDOW[0], window_end=WINDOW[1], zone=LAGOS, **kwargs
    )
    return intervals


def utc(*parts: int) -> datetime:
    return datetime(*parts, tzinfo=UTC)


# --- single events ---


def test_a_utc_event_is_busy_for_its_length():
    text = calendar(event("DTSTART:20261110T090000Z", "DTEND:20261110T100000Z", "SUMMARY:Secret"))
    assert busy(text) == [(utc(2026, 11, 10, 9), utc(2026, 11, 10, 10))]


def test_floating_times_and_named_zones_are_read_in_the_right_zone():
    floating = calendar(event("DTSTART:20261110T090000", "DTEND:20261110T100000"))
    assert busy(floating) == [(utc(2026, 11, 10, 8), utc(2026, 11, 10, 9))]  # mentor zone, UTC+1
    named = calendar(
        event(
            "DTSTART;TZID=America/New_York:20261110T090000",
            "DTEND;TZID=America/New_York:20261110T100000",
        )
    )
    assert busy(named) == [(utc(2026, 11, 10, 14), utc(2026, 11, 10, 15))]  # UTC-5 in November
    unknown = calendar(
        event(
            "DTSTART;TZID=W. Central Africa Standard Time:20261110T090000",
            "DURATION:PT30M",
        )
    )
    assert busy(unknown) == [(utc(2026, 11, 10, 8), utc(2026, 11, 10, 8, 30))]


def test_duration_is_an_alternative_to_an_end():
    text = calendar(event("DTSTART:20261110T090000Z", "DURATION:PT1H30M"))
    assert busy(text) == [(utc(2026, 11, 10, 9), utc(2026, 11, 10, 10, 30))]


def test_cancelled_free_and_all_day_events_do_not_block_time():
    cancelled = event("DTSTART:20261110T090000Z", "DTEND:20261110T100000Z", "STATUS:CANCELLED")
    free = event("DTSTART:20261111T090000Z", "DTEND:20261111T100000Z", "TRANSP:TRANSPARENT")
    all_day = event("DTSTART;VALUE=DATE:20261112", "DTEND;VALUE=DATE:20261113")
    text = calendar(cancelled, free, all_day)
    assert busy(text) == []
    # An all-day event blocks the whole local day when the mentor asks for it.
    assert busy(text, include_all_day=True) == [(utc(2026, 11, 11, 23), utc(2026, 11, 12, 23))]


def test_nothing_outside_the_window_is_kept_and_overlaps_are_merged():
    text = calendar(
        event("DTSTART:20250101T090000Z", "DTEND:20250101T100000Z"),
        event("DTSTART:20261110T090000Z", "DTEND:20261110T100000Z"),
        event("DTSTART:20261110T093000Z", "DTEND:20261110T110000Z"),
    )
    assert busy(text) == [(utc(2026, 11, 10, 9), utc(2026, 11, 10, 11))]


def test_only_times_are_kept():
    # The parser returns ranges and a count; titles and guests never leave it.
    text = calendar(
        event(
            "DTSTART:20261110T090000Z",
            "DTEND:20261110T100000Z",
            "SUMMARY:Board meeting",
            "ATTENDEE:mailto:someone@example.com",
        )
    )
    intervals, count = busy_intervals(
        text, window_start=WINDOW[0], window_end=WINDOW[1], zone=LAGOS
    )
    assert count == 1 and all(isinstance(a, datetime) for pair in intervals for a in pair)


# --- recurrence ---


def test_a_weekly_series_is_expanded_with_exceptions_and_moved_occurrences():
    series = event(
        "DTSTART;TZID=Africa/Lagos:20261102T100000",
        "DTEND;TZID=Africa/Lagos:20261102T110000",
        "RRULE:FREQ=WEEKLY;COUNT=4",  # 2, 9, 16, 23 November
        "EXDATE;TZID=Africa/Lagos:20261109T100000",  # the 9th is cancelled
    )
    moved = (
        "BEGIN:VEVENT\r\nUID:e1\r\nRECURRENCE-ID;TZID=Africa/Lagos:20261116T100000\r\n"
        "DTSTART;TZID=Africa/Lagos:20261117T150000\r\nDTEND;TZID=Africa/Lagos:20261117T160000\r\n"
        "END:VEVENT"
    )
    starts = [a for a, _ in busy(calendar(series, moved))]
    assert starts == [
        utc(2026, 11, 2, 9),  # 10:00 Lagos
        utc(2026, 11, 17, 14),  # the 16th moved to the 17th at 15:00
        utc(2026, 11, 23, 9),
    ]


def test_until_in_any_form_and_open_ended_series_work():
    until_date = calendar(
        event(
            "DTSTART:20261102T090000Z", "DTEND:20261102T100000Z", "RRULE:FREQ=DAILY;UNTIL=20261104"
        )
    )
    assert len(busy(until_date)) == 3
    until_floating = calendar(
        event(
            "DTSTART;TZID=Africa/Lagos:20261102T090000",
            "DTEND;TZID=Africa/Lagos:20261102T100000",
            "RRULE:FREQ=DAILY;UNTIL=20261104T090000",
        )
    )
    assert len(busy(until_floating)) == 3
    forever = calendar(
        event("DTSTART:20200106T090000Z", "DTEND:20200106T100000Z", "RRULE:FREQ=WEEKLY")
    )
    got = busy(forever)
    assert got and got[0][0] >= WINDOW[0] and len(got) == 9  # Mondays from 2 Nov to 28 Dec


def test_a_rule_that_repeats_every_few_seconds_is_not_expanded():
    text = calendar(
        event("DTSTART:20261110T090000Z", "DTEND:20261110T090100Z", "RRULE:FREQ=SECONDLY")
    )
    assert busy(text) == [(utc(2026, 11, 10, 9), utc(2026, 11, 10, 9, 1))]


def test_a_broken_event_is_skipped_not_fatal():
    text = calendar(
        event("DTSTART:not-a-date", "DTEND:20261110T100000Z"),
        event("DTSTART:20261111T090000Z", "DTEND:20261111T100000Z", "RRULE:FREQ=NEVER"),
        event("DTSTART:20261112T090000Z", "DTEND:20261112T100000Z"),
    )
    assert busy(text)[-1] == (utc(2026, 11, 12, 9), utc(2026, 11, 12, 10))


def test_very_long_events_are_ignored():
    text = calendar(event("DTSTART:20261101T090000Z", "DTEND:20270101T090000Z"))
    assert busy(text) == []


# --- the text itself ---


def test_other_text_is_not_a_feed():
    with pytest.raises(FeedInvalid):
        busy("<html><body>Sign in</body></html>")


def test_folded_lines_are_joined():
    assert unfold("SUMMARY:A very\r\n  long title\r\nUID:1") == [
        "SUMMARY:A very long title",
        "UID:1",
    ]


def test_alarms_inside_an_event_are_ignored():
    text = calendar(
        event(
            "DTSTART:20261110T090000Z",
            "DTEND:20261110T100000Z",
            "BEGIN:VALARM",
            "TRIGGER:-PT15M",
            "DURATION:PT5H",
            "END:VALARM",
        )
    )
    assert busy(text) == [(utc(2026, 11, 10, 9), utc(2026, 11, 10, 10))]


def test_time_is_clipped_to_the_window():
    text = calendar(event("DTSTART:20261031T220000Z", "DTEND:20261101T020000Z"))
    assert busy(text) == [(WINDOW[0], utc(2026, 11, 1, 2))]
    assert WINDOW[0] + timedelta(hours=2) == utc(2026, 11, 1, 2)
