"""A mentor edits their weekly and one off availability."""

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from django.db import IntegrityError, transaction
from django.db.backends.postgresql.psycopg_any import (  # type: ignore[import-untyped]
    DateTimeTZRange,
    NumericRange,
)
from django.utils import timezone
from rest_framework import exceptions

from apps.mentorship import cache, domain
from apps.mentorship.applications import Conflict, Forbidden
from apps.mentorship.models import AvailabilitySlot, MentorProfile

MAX_WEEKLY = 35
MAX_ONE_OFF = 60
MAX_WINDOW_HOURS = 12
MAX_AHEAD_DAYS = 180


def _minutes(value: str, field: str) -> int:
    try:
        hours, minutes = value.split(":")
        total = int(hours) * 60 + int(minutes)
    except ValueError as exc:
        raise domain.invalid(field, "Use HH:MM.") from exc
    if not 0 <= total <= 1440 or (total == 1440 and value != "24:00"):
        raise domain.invalid(field, "Use a time between 00:00 and 24:00.")
    return total


def _clock(total: int) -> str:
    return f"{total // 60:02d}:{total % 60:02d}"


def schedule(profile: MentorProfile) -> dict[str, Any]:
    now = timezone.now()
    slots = list(AvailabilitySlot.objects.filter(mentor_id=profile.user_id))
    weekly = sorted(
        (s.weekday or 0, s.start_minute or 0, s.end_minute or 0)
        for s in slots
        if s.kind == AvailabilitySlot.Kind.WEEKLY
    )
    one_off = sorted(
        (s.starts_at, s.ends_at)
        for s in slots
        if s.kind == AvailabilitySlot.Kind.ONE_OFF and s.starts_at and s.ends_at and s.ends_at > now
    )
    return {
        "timezone": profile.timezone,
        "session_minutes": profile.session_minutes,
        "weekly": [
            {"weekday": day, "start": _clock(start), "end": _clock(end)}
            for day, start, end in weekly
        ],
        "one_off": [{"starts_at": start, "ends_at": end} for start, end in one_off],
    }


def _weekly_rows(
    mentor_id: UUID, items: list[dict[str, Any]], minimum: int
) -> list[AvailabilitySlot]:
    rows: list[AvailabilitySlot] = []
    spans: list[tuple[int, int]] = []
    for item in items:
        start = _minutes(item["start"], "weekly")
        end = _minutes(item["end"], "weekly")
        if end - start < minimum:
            raise domain.invalid("weekly", f"Each window must be at least {minimum} minutes.")
        if end - start > MAX_WINDOW_HOURS * 60:
            raise domain.invalid("weekly", f"A window can be at most {MAX_WINDOW_HOURS} hours.")
        base = item["weekday"] * 1440
        span = (base + start, base + end)
        if any(span[0] < other[1] and other[0] < span[1] for other in spans):
            raise domain.invalid("weekly", "Weekly windows must not overlap.")
        spans.append(span)
        rows.append(
            AvailabilitySlot(
                mentor_id=mentor_id,
                kind=AvailabilitySlot.Kind.WEEKLY,
                weekday=item["weekday"],
                start_minute=start,
                end_minute=end,
                week_span=NumericRange(span[0], span[1], "[)"),
            )
        )
    return rows


def _one_off_rows(
    mentor_id: UUID, items: list[dict[str, Any]], minimum: int
) -> list[AvailabilitySlot]:
    now = timezone.now()
    rows: list[AvailabilitySlot] = []
    spans: list[tuple[datetime, datetime]] = []
    for item in items:
        start, end = item["starts_at"], item["ends_at"]
        if end - start < timedelta(minutes=minimum):
            raise domain.invalid("one_off", f"Each window must be at least {minimum} minutes.")
        if end - start > timedelta(hours=MAX_WINDOW_HOURS):
            raise domain.invalid("one_off", f"A window can be at most {MAX_WINDOW_HOURS} hours.")
        if start <= now:
            raise domain.invalid("one_off", "One off windows must start in the future.")
        if end > now + timedelta(days=MAX_AHEAD_DAYS):
            raise domain.invalid("one_off", f"At most {MAX_AHEAD_DAYS} days ahead.")
        if any(start < other[1] and other[0] < end for other in spans):
            raise domain.invalid("one_off", "One off windows must not overlap.")
        spans.append((start, end))
        rows.append(
            AvailabilitySlot(
                mentor_id=mentor_id,
                kind=AvailabilitySlot.Kind.ONE_OFF,
                starts_at=start,
                ends_at=end,
                time_span=DateTimeTZRange(start, end, "[)"),
            )
        )
    return rows


def replace(*, user_id: UUID, data: dict[str, Any]) -> MentorProfile:
    """Replace the whole schedule at once, so two edits cannot interleave."""
    weekly_items = data.get("weekly", [])
    one_off_items = data.get("one_off", [])
    if len(weekly_items) > MAX_WEEKLY or len(one_off_items) > MAX_ONE_OFF:
        raise exceptions.ValidationError({"weekly": ["Too many windows."]})
    zone = domain.timezone_name(data["timezone"]) if "timezone" in data else None
    try:
        with transaction.atomic():
            profile = MentorProfile.objects.select_for_update().filter(user_id=user_id).first()
            if profile is None or profile.status != MentorProfile.Status.ACTIVE:
                raise Forbidden("You are not a mentor.")
            if zone:
                profile.timezone = zone
                profile.save(update_fields=["timezone", "updated_at"])
            minimum = profile.session_minutes
            rows = _weekly_rows(user_id, weekly_items, minimum) + _one_off_rows(
                user_id, one_off_items, minimum
            )
            AvailabilitySlot.objects.filter(mentor_id=user_id).delete()
            AvailabilitySlot.objects.bulk_create(rows)
    except IntegrityError as exc:  # the database overlap guard; checked above, so a race
        raise Conflict("Your availability changed at the same time. Try again.") from exc
    cache.bump()
    return profile
