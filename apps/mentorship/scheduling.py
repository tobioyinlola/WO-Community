"""When a mentor can be booked: weekly and one off windows, minus what is already taken."""

from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone

from apps.mentorship.models import (
    ACTIVE_SESSION_STATUSES,
    AvailabilitySlot,
    MentorProfile,
    MentorSession,
)

Interval = tuple[datetime, datetime]
# Sessions that use up a place in the week: waiting, agreed, held, or missed by the founder.
COUNTED_STATUSES = (*ACTIVE_SESSION_STATUSES, "completed", "no_show")


def booked_intervals(mentor_id: UUID, start: datetime, end: datetime) -> list[Interval]:
    """Time already taken by requested and confirmed sessions."""
    rows = MentorSession.objects.filter(
        mentor_id=mentor_id,
        status__in=ACTIVE_SESSION_STATUSES,
        starts_at__lt=end,
        ends_at__gt=start,
    ).values_list("starts_at", "ends_at")
    return [(a, b) for a, b in rows]


def external_busy(mentor_id: UUID, start: datetime, end: datetime) -> list[Interval]:
    """Busy time from a mentor connected calendar.

    Reading a mentor own calendar needs a per mentor sign-in that is not built; the meeting
    providers only create meetings on the platform account. Returns nothing until it is.
    """
    return []


def week_bounds(zone_name: str, at: datetime) -> Interval:
    """The Monday 00:00 to next Monday 00:00 week, in the given time zone, as UTC instants."""
    zone = ZoneInfo(zone_name)
    local = at.astimezone(zone)
    monday = local.date() - timedelta(days=local.weekday())
    start = datetime.combine(monday, time(0, 0), tzinfo=zone)
    end = datetime.combine(monday + timedelta(days=7), time(0, 0), tzinfo=zone)
    return start.astimezone(UTC), end.astimezone(UTC)


def sessions_in_week(mentor_id: UUID, at: datetime, exclude: UUID | None = None) -> int:
    """Sessions using a place in the Monday to Sunday week (mentor local time) of ``at``.

    ``exclude`` leaves one session out, so a session being moved does not count against itself.
    """
    zone = (
        MentorProfile.objects.filter(user_id=mentor_id).values_list("timezone", flat=True).first()
    )
    begin, finish = week_bounds(zone or "UTC", at)
    rows = MentorSession.objects.filter(
        mentor_id=mentor_id,
        status__in=COUNTED_STATUSES,
        starts_at__gte=begin,
        starts_at__lt=finish,
    )
    if exclude is not None:
        rows = rows.exclude(pk=exclude)
    return rows.count()


def _merge(intervals: list[Interval]) -> list[Interval]:
    merged: list[Interval] = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _subtract(windows: list[Interval], busy: list[Interval]) -> list[Interval]:
    free: list[Interval] = []
    for start, end in windows:
        cursor = start
        for b_start, b_end in _merge(busy):
            if b_end <= cursor or b_start >= end:
                continue
            if b_start > cursor:
                free.append((cursor, b_start))
            cursor = max(cursor, b_end)
        if cursor < end:
            free.append((cursor, end))
    return free


def _local(day: date, minute: int, zone: ZoneInfo) -> datetime:
    midnight = datetime.combine(day, time(0, 0), tzinfo=zone)
    # Wall clock arithmetic: 09:00 stays 09:00 across a clock change.
    wall = datetime.combine(day, time(minute // 60, minute % 60), tzinfo=zone)
    return wall.astimezone(UTC) if minute < 1440 else (midnight + timedelta(days=1)).astimezone(UTC)


def windows(profile: MentorProfile, start: datetime, end: datetime) -> list[Interval]:
    """The mentor open windows between two instants, in UTC, merged and clipped."""
    zone = ZoneInfo(profile.timezone)
    slots = list(AvailabilitySlot.objects.filter(mentor_id=profile.user_id))
    found: list[Interval] = []
    day = (start.astimezone(zone) - timedelta(days=1)).date()
    last = (end.astimezone(zone) + timedelta(days=1)).date()
    while day <= last:
        for slot in slots:
            if slot.kind == AvailabilitySlot.Kind.WEEKLY and slot.weekday == day.weekday():
                assert slot.start_minute is not None and slot.end_minute is not None  # nosec B101
                found.append(
                    (_local(day, slot.start_minute, zone), _local(day, slot.end_minute, zone))
                )
        day += timedelta(days=1)
    for slot in slots:
        if slot.kind == AvailabilitySlot.Kind.ONE_OFF and slot.starts_at and slot.ends_at:
            found.append((slot.starts_at, slot.ends_at))
    clipped = [(max(a, start), min(b, end)) for a, b in found if b > start and a < end]
    return _merge([(a, b) for a, b in clipped if b > a])


def free_windows(profile: MentorProfile, start: datetime, end: datetime) -> list[Interval]:
    busy = booked_intervals(profile.user_id, start, end) + external_busy(
        profile.user_id, start, end
    )
    return _subtract(windows(profile, start, end), busy)


def _starts(
    profile: MentorProfile, begin: datetime, finish: datetime, earliest: datetime
) -> list[datetime]:
    """Start times from free windows between two instants, none before ``earliest``.

    Steps run from the start of each whole free window, not from where the search begins, so
    the same times are offered however far ahead the question is asked.
    """
    length = timedelta(minutes=profile.session_minutes)
    starts: list[datetime] = []
    for window_start, window_end in free_windows(profile, begin, finish):
        cursor = window_start
        while cursor + length <= window_end:
            if cursor >= earliest:
                starts.append(cursor)
            cursor += length
    return starts


def _within_capacity(
    profile: MentorProfile, starts: list[datetime], exclude: UUID | None
) -> list[datetime]:
    """Drop start times that fall in a week with no places left."""
    full: dict[datetime, bool] = {}
    kept: list[datetime] = []
    for start in starts:
        week = week_bounds(profile.timezone, start)[0]
        if week not in full:
            full[week] = (
                sessions_in_week(profile.user_id, start, exclude) >= profile.capacity_per_week
            )
        if not full[week]:
            kept.append(start)
    return kept


def bookable_starts(
    profile: MentorProfile, *, days: int, now: datetime | None = None
) -> list[datetime]:
    """Start times a session of the mentor length could begin, soonest first.

    Starts begin at each free window start and step by the session length, so a 09:00 to 12:00
    window with 45 minute sessions offers 09:00, 09:45, 10:30 and 11:15. Nothing earlier than the
    minimum notice is offered.
    """
    now = now or timezone.now()
    earliest = now + timedelta(hours=settings.MENTORSHIP_MIN_NOTICE_HOURS)
    latest = now + timedelta(days=min(days, settings.MENTORSHIP_HORIZON_DAYS))
    starts = _starts(profile, earliest - timedelta(days=1), latest, earliest)
    return _within_capacity(profile, starts, None)


def is_bookable(
    profile: MentorProfile,
    start: datetime,
    *,
    now: datetime | None = None,
    exclude: UUID | None = None,
) -> bool:
    """Whether ``start`` is one of the times that would be offered.

    ``exclude`` is a session being moved: its own place in the week is not held against it.
    """
    now = now or timezone.now()
    earliest = now + timedelta(hours=settings.MENTORSHIP_MIN_NOTICE_HOURS)
    if start < earliest or start > now + timedelta(days=settings.MENTORSHIP_HORIZON_DAYS):
        return False
    margin = timedelta(days=1)
    offered = _starts(profile, start - margin, start + margin, earliest)
    return start in offered and bool(_within_capacity(profile, [start], exclude))


def capacity_left(profile: MentorProfile, at: datetime | None = None) -> int:
    return max(
        0, profile.capacity_per_week - sessions_in_week(profile.user_id, at or timezone.now())
    )


def has_availability(mentor_ids: Any) -> Any:
    """Mentors with any weekly window, or a one off window still ahead."""
    from django.db.models import Q

    return (
        AvailabilitySlot.objects.filter(
            Q(kind="weekly") | Q(kind="one_off", ends_at__gt=timezone.now()),
            mentor_id__in=mentor_ids,
        )
        .values_list("mentor_id", flat=True)
        .distinct()
    )
