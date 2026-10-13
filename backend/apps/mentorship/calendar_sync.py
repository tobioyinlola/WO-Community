"""A mentor shares their calendar so busy time is never offered, and previews what is offered.

The mentor pastes the private iCal address their calendar app gives them (Google, Outlook and
Apple all have one). It is stored encrypted, read by a worker every 15 minutes, and reduced to
time ranges with no titles. Offered times are computed from the stored ranges, so no request ever
waits on a calendar provider.
"""

import hashlib
from datetime import timedelta
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID
from zoneinfo import ZoneInfo

import structlog
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import exceptions

from apps.core import crypto, ratelimit
from apps.integrations.calendars import FeedRejected, FeedUnavailable, get_feed_reader
from apps.integrations.calendars.ics import FeedInvalid, busy_intervals
from apps.mentorship import cache, domain, scheduling
from apps.mentorship.applications import Forbidden
from apps.mentorship.models import CalendarBusy, CalendarConnection, MentorProfile

logger = structlog.get_logger(__name__)

MAX_URL = 1000
BATCH = 200
REASONS = {
    "invalid_url": "That is not a usable calendar address.",
    "bad_scheme": "Use the https address of your calendar.",
    "credentials_in_url": "The address must not contain a user name or password.",
    "blocked_address": "That address cannot be used.",
    "bad_port": "That address cannot be used.",
    "unsupported_content_type": "That address does not return a calendar.",
    "not_a_calendar": "That address does not return a calendar.",
    "too_large": "That calendar is too large to read.",
    "too_many_redirects": "That address redirects too many times.",
    "timeout": "The calendar did not answer in time. Try again.",
    "network_error": "The calendar could not be reached. Try again.",
}


def _reason(code: str) -> str:
    if code.startswith("status_"):
        return f"The calendar answered with an error ({code[7:]}). Check the address."
    return REASONS.get(code, "That address cannot be used.")


def clean_url(raw: str) -> str:
    """The https address of a feed. ``webcal://`` is the same thing with another scheme name."""
    value = raw.strip()
    if value.lower().startswith("webcal://"):
        value = "https://" + value[9:]
    if len(value) > MAX_URL or not value.lower().startswith("https://"):
        raise domain.invalid("feed_url", "Use the https address of your calendar.")
    if not urlsplit(value).hostname:
        raise domain.invalid("feed_url", "That is not a usable calendar address.")
    return value


def require_mentor(user_id: UUID) -> MentorProfile:
    profile = MentorProfile.objects.filter(
        user_id=user_id, status=MentorProfile.Status.ACTIVE
    ).first()
    if profile is None:
        raise Forbidden("You are not a mentor.")
    return profile


def status_of(user_id: UUID) -> dict[str, Any]:
    connection = CalendarConnection.objects.filter(mentor_id=user_id).first()
    if connection is None:
        return {
            "connected": False,
            "host": "",
            "include_all_day": False,
            "status": None,
            "last_synced_at": None,
            "last_error": "",
            "stale": False,
            "busy_ranges": 0,
        }
    now = timezone.now()
    synced = connection.last_synced_at
    return {
        "connected": True,
        "host": connection.host,
        "include_all_day": connection.include_all_day,
        "status": connection.status,
        "last_synced_at": synced,
        "last_error": _reason(connection.last_error) if connection.last_error else "",
        "stale": synced is None or now - synced > settings.CALENDAR_STALE_AFTER,
        "busy_ranges": CalendarBusy.objects.filter(mentor_id=user_id, ends_at__gt=now).count(),
    }


def _read(connection: CalendarConnection, profile: MentorProfile | None) -> tuple[list[Any], int]:
    zone = ZoneInfo(profile.timezone) if profile else ZoneInfo("UTC")
    now = timezone.now()
    text = get_feed_reader().read(crypto.decrypt(connection.feed_url_encrypted))
    return busy_intervals(
        text,
        window_start=now - timedelta(days=1),
        window_end=now + timedelta(days=settings.CALENDAR_SYNC_DAYS),
        zone=zone,
        include_all_day=connection.include_all_day,
    )


def sync(connection: CalendarConnection) -> bool:
    """Read the feed and replace the stored busy time. Returns whether the read succeeded.

    A failed read keeps the busy time from the last good read, so a calendar outage makes the
    mentor look busier, never freer.
    """
    now = timezone.now()
    profile = MentorProfile.objects.filter(user_id=connection.mentor_id).first()
    try:
        intervals, count = _read(connection, profile)
    except (FeedRejected, FeedUnavailable, FeedInvalid) as exc:
        code = getattr(exc, "code", "") or str(exc)
        CalendarConnection.objects.filter(pk=connection.pk).update(
            status=CalendarConnection.Status.ERROR, last_error=code[:40], last_attempt_at=now
        )
        logger.info("calendar_sync_failed", mentor_id=str(connection.mentor_id), code=code)
        return False
    _store(connection, intervals, count, now)
    return True


def _store(connection: CalendarConnection, intervals: list[Any], count: int, now: Any) -> None:
    digest = hashlib.sha256(repr(intervals).encode()).hexdigest()
    changed = digest != connection.busy_hash
    with transaction.atomic():
        if changed:
            CalendarBusy.objects.filter(mentor_id=connection.mentor_id).delete()
            CalendarBusy.objects.bulk_create(
                CalendarBusy(mentor_id=connection.mentor_id, starts_at=a, ends_at=b)
                for a, b in intervals
            )
            transaction.on_commit(cache.bump)  # offered times, and so matches, changed
        else:
            CalendarBusy.objects.filter(mentor_id=connection.mentor_id, ends_at__lt=now).delete()
        CalendarConnection.objects.filter(pk=connection.pk).update(
            status=CalendarConnection.Status.ACTIVE,
            last_error="",
            last_synced_at=now,
            last_attempt_at=now,
            event_count=count,
            busy_hash=digest,
        )


def connect(*, user_id: UUID, feed_url: str | None, include_all_day: bool | None) -> dict[str, Any]:
    """Share a calendar (or change what is read from the one already shared).

    The address is read once, here, so a wrong one is refused at once with the reason.
    """
    require_mentor(user_id)
    if ratelimit.hit(f"mentorship:calendar:{user_id}", 3600) > settings.CALENDAR_CONNECTS_PER_HOUR:
        raise exceptions.Throttled(wait=3600, detail="Too many attempts. Try again later.")
    existing = CalendarConnection.objects.filter(mentor_id=user_id).first()
    if feed_url is None and existing is None:
        raise domain.invalid("feed_url", "This field is required.")
    all_day = (
        include_all_day
        if include_all_day is not None
        else (existing.include_all_day if existing else False)
    )
    candidate = existing or CalendarConnection(mentor_id=user_id)
    if feed_url is not None:
        url = clean_url(feed_url)
        candidate.feed_url_encrypted = crypto.encrypt(url)
        candidate.host = (urlsplit(url).hostname or "")[:120]
        candidate.busy_hash = ""  # a new address: replace everything
    candidate.include_all_day = all_day
    if existing is not None and (include_all_day is not None) and feed_url is None:
        candidate.busy_hash = ""
    # Read it before saving anything, so a bad address never replaces a good one.
    try:
        intervals, count = _read(candidate, MentorProfile.objects.filter(user_id=user_id).first())
    except (FeedRejected, FeedUnavailable) as exc:
        raise domain.invalid("feed_url", _reason(exc.code)) from exc
    except FeedInvalid as exc:
        raise domain.invalid("feed_url", _reason(str(exc))) from exc
    candidate.save()
    _store(candidate, intervals, count, timezone.now())
    return status_of(user_id)


def refresh(*, user_id: UUID) -> dict[str, Any]:
    require_mentor(user_id)
    connection = CalendarConnection.objects.filter(mentor_id=user_id).first()
    if connection is None:
        raise exceptions.NotFound()
    if ratelimit.hit(f"mentorship:calendar-sync:{user_id}", 60) > 1:
        raise exceptions.Throttled(wait=60, detail="Refresh at most once a minute.")
    sync(connection)
    return status_of(user_id)


def disconnect(*, user_id: UUID) -> None:
    with transaction.atomic():
        CalendarBusy.objects.filter(mentor_id=user_id).delete()
        CalendarConnection.objects.filter(mentor_id=user_id).delete()
        transaction.on_commit(cache.bump)


def sync_all(limit: int = BATCH) -> int:
    """Refresh the feeds that were read longest ago. Returns how many were read."""
    done = 0
    rows = CalendarConnection.objects.order_by("last_attempt_at").select_related()[:limit]
    for connection in list(rows):
        active = MentorProfile.objects.filter(
            user_id=connection.mentor_id, status=MentorProfile.Status.ACTIVE
        ).exists()
        if not active:
            disconnect(user_id=connection.mentor_id)
            continue
        try:
            if sync(connection):
                done += 1
        except Exception:  # noqa: BLE001  # one mentor's feed must not stop the others
            logger.exception("calendar_sync_crashed", mentor_id=str(connection.mentor_id))
    return done


def _ranges(items: list[tuple[Any, Any]]) -> list[dict[str, Any]]:
    return [{"starts_at": a, "ends_at": b} for a, b in items]


def preview(user_id: UUID, *, days: int) -> dict[str, Any]:
    """What the mentor is offering over the next days, and what removes time from it.

    Shows the mentor's own windows, the calendar busy time, booked sessions, the free time left
    and the start times a founder would be offered, so they can adjust their windows with the
    result in front of them.
    """
    profile = require_mentor(user_id)
    now = timezone.now()
    end = now + timedelta(days=days)
    return {
        "timezone": profile.timezone,
        "session_minutes": profile.session_minutes,
        "windows": _ranges(scheduling.windows(profile, now, end)),
        "calendar_busy": _ranges(scheduling.external_busy(user_id, now, end)),
        "booked": _ranges(scheduling.booked_intervals(user_id, now, end)),
        "free": _ranges(scheduling.free_windows(profile, now, end)),
        "bookable_starts": [] if profile.paused else scheduling.bookable_starts(profile, days=days),
        "calendar": status_of(user_id),
    }
