"""Reading busy time out of an iCalendar feed. Pure functions: text in, time ranges out.

Only *when* a mentor is busy is kept. Titles, attendees, places and notes are never read into
anything that is stored. What counts as busy: events that are not cancelled and not marked
"free" (``TRANSP:TRANSPARENT``); all-day events only when asked for (they are often reminders).

Recurring events are expanded inside the window that matters, with exceptions (``EXDATE``) and
moved or edited single occurrences (``RECURRENCE-ID``) honoured. A feed is untrusted input, so
every step is bounded: events, occurrences per event and total ranges are capped, rules that would
repeat every few seconds are not expanded, and a broken event is skipped rather than failing the
feed.
"""

import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dateutil import rrule  # type: ignore[import-untyped]

Interval = tuple[datetime, datetime]

MAX_EVENTS = 20_000
MAX_OCCURRENCES = 1_000  # per recurring event, inside the window
MAX_INTERVALS = 5_000
MAX_EVENT_LENGTH = timedelta(days=31)
_FAST_RULES = ("SECONDLY", "MINUTELY", "HOURLY")

_DURATION = re.compile(r"^([+-])?P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$")
_UNTIL = re.compile(r"UNTIL=([0-9TZ]+)", re.IGNORECASE)


class FeedInvalid(Exception):
    """The text is not an iCalendar feed."""


@dataclass
class _Event:
    uid: str = ""
    start: datetime | date | None = None
    end: datetime | date | None = None
    duration: timedelta | None = None
    rrule: str = ""
    exdates: list[datetime | date] = field(default_factory=list)
    status: str = ""
    transparent: bool = False
    recurrence_id: datetime | date | None = None


def unfold(text: str) -> list[str]:
    """Lines with continuation lines joined back on."""
    lines: list[str] = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        elif raw:
            lines.append(raw)
    return lines


def _split(line: str) -> tuple[str, dict[str, str], str] | None:
    """``NAME;PARAM=V:value`` as (name, params, value); colons inside quotes are not splits."""
    in_quotes = False
    for index, char in enumerate(line):
        if char == '"':
            in_quotes = not in_quotes
        elif char == ":" and not in_quotes:
            head, value = line[:index], line[index + 1 :]
            break
    else:
        return None
    pieces = head.split(";")
    params: dict[str, str] = {}
    for piece in pieces[1:]:
        key, _, val = piece.partition("=")
        params[key.upper()] = val.strip('"')
    return pieces[0].upper(), params, value


def _to_time(value: str, params: dict[str, str], zone: ZoneInfo) -> datetime | date:
    value = value.strip()
    if params.get("VALUE") == "DATE" or len(value) == 8:
        return date(int(value[:4]), int(value[4:6]), int(value[6:8]))
    utc = value.endswith("Z")
    parsed = datetime.strptime(value.rstrip("Zz"), "%Y%m%dT%H%M%S")
    if utc:
        return parsed.replace(tzinfo=UTC)
    tz = zone
    tzid = params.get("TZID")
    if tzid:
        try:
            tz = ZoneInfo(tzid)
        except (ZoneInfoNotFoundError, ValueError, OSError):
            tz = zone  # a vendor time zone name we do not know: use the mentor's own
    return parsed.replace(tzinfo=tz)


def _to_duration(value: str) -> timedelta | None:
    match = _DURATION.match(value.strip().upper())
    if not match:
        return None
    sign, weeks, days, hours, minutes, seconds = match.groups()
    total = timedelta(
        weeks=int(weeks or 0),
        days=int(days or 0),
        hours=int(hours or 0),
        minutes=int(minutes or 0),
        seconds=int(seconds or 0),
    )
    return -total if sign == "-" else total


def _events(text: str, zone: ZoneInfo) -> list[_Event]:
    found: list[_Event] = []
    current: _Event | None = None
    alarm_depth = 0
    for line in unfold(text):
        upper = line.upper()
        if upper == "BEGIN:VEVENT":
            current = _Event()
            continue
        if upper == "END:VEVENT":
            if current is not None and current.start is not None:
                found.append(current)
                if len(found) > MAX_EVENTS:
                    break
            current = None
            continue
        if current is None:
            continue
        if upper == "BEGIN:VALARM":
            alarm_depth += 1
            continue
        if upper == "END:VALARM":
            alarm_depth = max(0, alarm_depth - 1)
            continue
        if alarm_depth:
            continue
        parts = _split(line)
        if parts is None:
            continue
        name, params, value = parts
        try:
            if name == "UID":
                current.uid = value.strip()
            elif name == "DTSTART":
                current.start = _to_time(value, params, zone)
            elif name == "DTEND":
                current.end = _to_time(value, params, zone)
            elif name == "DURATION":
                current.duration = _to_duration(value)
            elif name == "RRULE":
                current.rrule = value.strip()
            elif name == "EXDATE":
                current.exdates += [
                    _to_time(part, params, zone) for part in value.split(",") if part.strip()
                ]
            elif name == "STATUS":
                current.status = value.strip().upper()
            elif name == "TRANSP":
                current.transparent = value.strip().upper() == "TRANSPARENT"
            elif name == "RECURRENCE-ID":
                current.recurrence_id = _to_time(value, params, zone)
        except (ValueError, OverflowError):
            current.start = None if name == "DTSTART" else current.start  # a bad start drops it
    return found


def _as_instant(value: datetime | date, zone: ZoneInfo) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.combine(value, time(0, 0), tzinfo=zone)


def _length(event: _Event, zone: ZoneInfo) -> timedelta:
    assert event.start is not None  # nosec B101
    start = _as_instant(event.start, zone)
    if event.end is not None:
        return _as_instant(event.end, zone) - start
    if event.duration is not None:
        return event.duration
    return timedelta(days=1) if not isinstance(event.start, datetime) else timedelta(0)


def _rule_text(text: str, start: datetime) -> str:
    """The rule with UNTIL as a UTC instant, which is what a time zone aware start requires."""

    def fix(match: re.Match[str]) -> str:
        value = match.group(1).upper()
        if value.endswith("Z"):
            return match.group(0)
        if len(value) == 8:
            return f"UNTIL={value}T235959Z"
        naive = datetime.strptime(value, "%Y%m%dT%H%M%S").replace(tzinfo=start.tzinfo)
        return "UNTIL=" + naive.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")

    return _UNTIL.sub(fix, text)


def _occurrences(
    event: _Event, zone: ZoneInfo, window: Interval, skip: set[datetime]
) -> list[Interval]:
    assert event.start is not None  # nosec B101
    start = _as_instant(event.start, zone)
    length = _length(event, zone)
    if length <= timedelta(0) or length > MAX_EVENT_LENGTH:
        return []
    begin, finish = window
    if not event.rrule:
        return [(start, start + length)] if start < finish and start + length > begin else []

    skipped = {s.astimezone(UTC) for s in skip}
    skipped |= {_as_instant(d, zone).astimezone(UTC) for d in event.exdates}
    try:
        rule = rrule.rrulestr(_rule_text(event.rrule, start), dtstart=start)
        if getattr(rule, "_freq", None) in (rrule.SECONDLY, rrule.MINUTELY, rrule.HOURLY):
            return [(start, start + length)] if start < finish and start + length > begin else []
        found: list[Interval] = []
        for occurrence in rule.xafter(begin - length, count=MAX_OCCURRENCES, inc=True):
            if occurrence >= finish:
                break
            if occurrence.astimezone(UTC) in skipped:
                continue
            found.append((occurrence, occurrence + length))
        return found
    except (ValueError, TypeError, OverflowError, KeyError):
        return []  # a rule we cannot read: better to miss one series than to fail the feed


def _merge(intervals: list[Interval]) -> list[Interval]:
    merged: list[Interval] = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def busy_intervals(
    text: str,
    *,
    window_start: datetime,
    window_end: datetime,
    zone: ZoneInfo,
    include_all_day: bool = False,
) -> tuple[list[Interval], int]:
    """Merged busy ranges (UTC) inside the window, and how many events were read."""
    if "BEGIN:VCALENDAR" not in text[:4096].upper():
        raise FeedInvalid("not_a_calendar")
    events = _events(text, zone)
    moved: dict[str, set[datetime]] = {}
    for event in events:
        if event.recurrence_id is not None and event.uid:
            moved.setdefault(event.uid, set()).add(_as_instant(event.recurrence_id, zone))
    window = (window_start, window_end)
    busy: list[Interval] = []
    for event in events:
        if event.status == "CANCELLED" or event.transparent or event.start is None:
            continue
        if not isinstance(event.start, datetime) and not include_all_day:
            continue
        skip = moved.get(event.uid, set()) if event.recurrence_id is None else set()
        for start, end in _occurrences(event, zone, window, skip):
            clipped = (max(start, window_start), min(end, window_end))
            if clipped[1] > clipped[0]:
                busy.append((clipped[0].astimezone(UTC), clipped[1].astimezone(UTC)))
        if len(busy) > MAX_INTERVALS * 4:
            break
    return _merge(busy)[:MAX_INTERVALS], len(events)
