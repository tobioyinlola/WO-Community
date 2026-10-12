"""What a mentor sets up in Settings: how they are booked, when, at what price, and with what link.

Weekly windows and extra one off time are `AvailabilitySlot` rows; days off are
`AvailabilityException` rows; everything else about booking is on `MentorSettings`,
`MentorSessionPrice` and the existing `MentorProfile`. A change that would leave an agreed session
outside the new schedule is refused with the sessions named, and goes through only when the mentor
says to keep them: sessions already agreed are never deleted or moved by editing the schedule.
"""

from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.backends.postgresql.psycopg_any import (  # type: ignore[import-untyped]
    DateTimeTZRange,
)
from django.utils import timezone
from rest_framework import exceptions

from apps.core.errors import ConflictError
from apps.core.text import clean_url, plain
from apps.integrations import meetings
from apps.mentorship import availability, cache, domain, scheduling
from apps.mentorship.applications import Forbidden
from apps.mentorship.models import (
    ACTIVE_SESSION_STATUSES,
    AvailabilityException,
    AvailabilitySlot,
    MentorProfile,
    MentorSession,
    MentorSessionPrice,
    MentorSettings,
)

LENGTHS = (30, 45, 60)
BUFFERS = (0, 10, 15, 30)
NOTICE_HOURS = (1, 2, 6, 12, 24, 48, 72)
WINDOW_DAYS = (7, 14, 30, 60, 90)
CURRENCIES = ("NGN", "USD", "KES", "GHS", "ZAR", "EGP", "GBP", "EUR")
MAX_PRICE_MINOR = 100_000_000
MAX_EXCEPTIONS = 60


class ScheduleConflict(ConflictError):
    """A change would leave agreed sessions outside the schedule; carries them for the response."""

    default_detail = "This change affects sessions that are already agreed."

    def __init__(self, sessions: list[dict[str, Any]]):
        super().__init__(self.default_detail)
        self.sessions = sessions


# --- reading ---


def profile_of(user_id: UUID, *, lock: bool = False) -> MentorProfile:
    queryset = MentorProfile.objects.filter(user_id=user_id)
    profile = (queryset.select_for_update() if lock else queryset).first()
    if profile is None or profile.status != MentorProfile.Status.ACTIVE:
        raise Forbidden("You are not a mentor.")
    return profile


def prefs_row(profile: MentorProfile) -> MentorSettings:
    """The saved preferences, made from the old single length and platform defaults on first use."""
    row = MentorSettings.objects.filter(user_id=profile.user_id).first()
    if row is None:
        row, _ = MentorSettings.objects.get_or_create(
            user_id=profile.user_id,
            defaults={
                "session_lengths": [profile.session_minutes],
                "min_notice_hours": settings.MENTORSHIP_MIN_NOTICE_HOURS,
                "booking_window_days": min(30, settings.MENTORSHIP_HORIZON_DAYS),
            },
        )
    return row


def price_table(user_id: UUID) -> dict[int, int]:
    return {
        p.length_minutes: p.price_minor
        for p in MentorSessionPrice.objects.filter(mentor_id=user_id)
    }


def quote(profile: MentorProfile, length: int) -> dict[str, Any]:
    """What a session of this length costs and how it is settled.

    Online payment is not switched on, so a price is informational: the mentor confirms the request
    and the two arrange payment directly (`payment_mode` "arranged"). When payments arrive, this is
    the one place that decides the mode and a payment step can attach to the booking.
    """
    row = scheduling.preferences(profile)
    if row.pricing_mode != MentorSettings.Pricing.PAID:
        return {"mode": "free", "price_minor": None, "currency": "", "payment": ""}
    price = price_table(profile.user_id).get(length) or row.default_price_minor
    if not price:
        return {"mode": "free", "price_minor": None, "currency": "", "payment": ""}
    return {"mode": "paid", "price_minor": price, "currency": row.currency, "payment": "arranged"}


def exceptions_view(user_id: UUID) -> list[dict[str, Any]]:
    today = timezone.now().date() - timedelta(days=1)
    blocks = AvailabilityException.objects.filter(mentor_id=user_id, ends_on__gte=today).order_by(
        "starts_on"
    )
    out: list[dict[str, Any]] = [
        {
            "id": b.pk,
            "type": "blocked",
            "starts_on": b.starts_on,
            "ends_on": b.ends_on,
            "starts_at": None,
            "ends_at": None,
            "note": b.note,
        }
        for b in blocks
    ]
    extras = AvailabilitySlot.objects.filter(
        mentor_id=user_id, kind=AvailabilitySlot.Kind.ONE_OFF, ends_at__gt=timezone.now()
    ).order_by("starts_at")
    out += [
        {
            "id": e.pk,
            "type": "extra",
            "starts_on": None,
            "ends_on": None,
            "starts_at": e.starts_at,
            "ends_at": e.ends_at,
            "note": "",
        }
        for e in extras
    ]
    return out


def settings_view(user_id: UUID) -> dict[str, Any]:
    profile = profile_of(user_id)
    row = prefs_row(profile)
    weekly = availability.schedule(profile)["weekly"]
    return {
        "timezone": profile.timezone,
        "accepting_new": not profile.paused,
        "weekly": weekly,
        "exceptions": exceptions_view(user_id),
        "session_lengths": scheduling.offered_lengths(profile),
        "default_length": scheduling.default_length(profile),
        "buffer_minutes": row.buffer_minutes,
        "min_notice_hours": row.min_notice_hours,
        "max_per_week": profile.capacity_per_week,
        "booking_window_days": row.booking_window_days,
        "pricing_mode": row.pricing_mode,
        "default_price_minor": row.default_price_minor,
        "currency": row.currency,
        "prices": [
            {"length_minutes": n, "price_minor": v} for n, v in sorted(price_table(user_id).items())
        ],
        "payments_enabled": settings.FEATURE_PAYMENTS_ENABLED,
        "meeting_provider": profile.meeting_provider,
        "personal_link": row.personal_link,
        "meeting_providers": meetings.provider_names(),
        "about": profile.about,
        "expertise": profile.expertise,
        "topics": row.topics,
        "languages": profile.languages,
        "stages": profile.stages,
        "industries": profile.industries,
        "options": {
            "lengths": list(LENGTHS),
            "buffers": list(BUFFERS),
            "notice_hours": list(NOTICE_HOURS),
            "window_days": list(WINDOW_DAYS),
            "currencies": list(CURRENCIES),
        },
    }


# --- what a change would disturb ---


def agreed_outside(profile: MentorProfile) -> list[dict[str, Any]]:
    """Upcoming requested or confirmed sessions that no longer sit inside an open window."""
    now = timezone.now()
    sessions = list(
        MentorSession.objects.filter(
            mentor_id=profile.user_id, status__in=ACTIVE_SESSION_STATUSES, ends_at__gt=now
        ).order_by("starts_at")
    )
    if not sessions:
        return []
    horizon = max(s.ends_at for s in sessions) + timedelta(days=1)
    open_windows = scheduling.windows(profile, now - timedelta(days=1), horizon)
    lengths = set(scheduling.offered_lengths(profile))
    clashing = []
    for s in sessions:
        inside = any(a <= s.starts_at and s.ends_at <= b for a, b in open_windows)
        length = s.length_minutes or round((s.ends_at - s.starts_at).total_seconds() / 60)
        if not inside or length not in lengths:
            clashing.append(
                {
                    "id": s.pk,
                    "starts_at": s.starts_at,
                    "ends_at": s.ends_at,
                    "status": s.status,
                    "topic": s.topic,
                }
            )
    return clashing


def _guard(profile: MentorProfile, before: list[dict[str, Any]], acknowledge: bool) -> None:
    """Refuse a change that newly strands sessions, unless the mentor has said to keep them."""
    after = agreed_outside(profile)
    known = {c["id"] for c in before}
    fresh = [c for c in after if c["id"] not in known]
    if fresh and not acknowledge:
        raise ScheduleConflict(fresh)


# --- weekly availability ---


def save_weekly(
    *, user_id: UUID, weekly: list[dict[str, Any]], tz: str | None, acknowledge: bool = False
) -> MentorProfile:
    """Replace the weekly windows (and the time zone), keeping extra one off time and days off."""
    if len(weekly) > availability.MAX_WEEKLY:
        raise exceptions.ValidationError({"weekly": ["Too many windows."]})
    try:
        with transaction.atomic():
            profile = profile_of(user_id, lock=True)
            before = agreed_outside(profile)
            if tz:
                profile.timezone = domain.timezone_name(tz)
                profile.save(update_fields=["timezone", "updated_at"])
            minimum = min(scheduling.offered_lengths(profile))
            rows = availability._weekly_rows(user_id, weekly, minimum)  # noqa: SLF001
            if not rows and not profile.paused:
                raise domain.invalid(
                    "weekly", "Add at least one time range, or turn off accepting new mentees."
                )
            AvailabilitySlot.objects.filter(
                mentor_id=user_id, kind=AvailabilitySlot.Kind.WEEKLY
            ).delete()
            AvailabilitySlot.objects.bulk_create(rows)
            _guard(profile, before, acknowledge)
    except IntegrityError as exc:
        raise ConflictError("Your availability changed at the same time. Try again.") from exc
    cache.bump()
    return profile


# --- days off and extra time ---


def add_exception(*, user_id: UUID, data: dict[str, Any], acknowledge: bool = False) -> None:
    kind = data["type"]
    with transaction.atomic():
        profile = profile_of(user_id, lock=True)
        if (
            AvailabilityException.objects.filter(mentor_id=user_id).count()
            + AvailabilitySlot.objects.filter(
                mentor_id=user_id, kind=AvailabilitySlot.Kind.ONE_OFF
            ).count()
            >= MAX_EXCEPTIONS
        ):
            raise domain.invalid("type", "That is as many dates as can be kept. Remove old ones.")
        before = agreed_outside(profile)
        zone = ZoneInfo(profile.timezone)
        today = timezone.now().astimezone(zone).date()
        if kind == "blocked":
            first: date | None = data.get("starts_on")
            if first is None:
                raise domain.invalid("starts_on", "Choose the first day.")
            last: date = data.get("ends_on") or first
            if last < first:
                raise domain.invalid("ends_on", "The last day cannot be before the first.")
            if last < today:
                raise domain.invalid("starts_on", "Choose dates that have not passed.")
            if (last - first).days > 120:
                raise domain.invalid("ends_on", "At most 120 days at a time.")
            AvailabilityException.objects.create(
                mentor_id=user_id, starts_on=first, ends_on=last, note=plain(data.get("note", ""))
            )
            _guard(profile, before, acknowledge)
        else:
            day: date | None = data.get("date")
            if day is None or "start" not in data or "end" not in data:
                raise domain.invalid("date", "Give the date and the start and end times.")
            start_min = availability._minutes(data["start"], "start")  # noqa: SLF001
            end_min = availability._minutes(data["end"], "end")  # noqa: SLF001
            if end_min <= start_min:
                raise domain.invalid("end", "The end must be after the start.")
            if end_min - start_min < min(scheduling.offered_lengths(profile)):
                raise domain.invalid("end", "Leave room for at least one session.")
            start = datetime.combine(day, time(start_min // 60, start_min % 60), tzinfo=zone)
            end = datetime.combine(day, time(0, 0), tzinfo=zone) + timedelta(minutes=end_min)
            start, end = start.astimezone(UTC), end.astimezone(UTC)
            if start <= timezone.now():
                raise domain.invalid("date", "Extra time must start in the future.")
            try:
                AvailabilitySlot.objects.create(
                    mentor_id=user_id,
                    kind=AvailabilitySlot.Kind.ONE_OFF,
                    starts_at=start,
                    ends_at=end,
                    time_span=DateTimeTZRange(start, end, "[)"),
                )
            except IntegrityError as exc:
                raise domain.invalid("date", "That overlaps other extra time.") from exc
    cache.bump()


def remove_exception(*, user_id: UUID, item_id: UUID, acknowledge: bool = False) -> None:
    with transaction.atomic():
        profile = profile_of(user_id, lock=True)
        before = agreed_outside(profile)
        block = AvailabilityException.objects.filter(mentor_id=user_id, pk=item_id).first()
        if block is not None:
            block.delete()  # removing a day off only adds time, so nothing is stranded
        else:
            slot = AvailabilitySlot.objects.filter(
                mentor_id=user_id, kind=AvailabilitySlot.Kind.ONE_OFF, pk=item_id
            ).first()
            if slot is None:
                raise exceptions.NotFound()
            slot.delete()
            _guard(profile, before, acknowledge)
    cache.bump()


# --- the rest of the settings ---


def _choice(field: str, value: Any, allowed: tuple[int, ...]) -> int:
    if value not in allowed:
        raise domain.invalid(field, f"Choose one of: {', '.join(str(a) for a in allowed)}.")
    return int(value)


def save_settings(*, user_id: UUID, data: dict[str, Any], acknowledge: bool = False) -> None:
    with transaction.atomic():
        profile = profile_of(user_id, lock=True)
        before = agreed_outside(profile)
        row = prefs_row(profile)
        row = MentorSettings.objects.select_for_update().get(pk=row.pk)

        if "session_lengths" in data:
            lengths = sorted(
                {_choice("session_lengths", n, LENGTHS) for n in data["session_lengths"]}
            )
            if not lengths:
                raise domain.invalid("session_lengths", "Offer at least one session length.")
            row.session_lengths = lengths
            if profile.session_minutes not in lengths:
                profile.session_minutes = lengths[0]
        if "default_length" in data:
            if data["default_length"] not in row.session_lengths:
                raise domain.invalid("default_length", "Choose one of the lengths you offer.")
            profile.session_minutes = data["default_length"]
        if "buffer_minutes" in data:
            row.buffer_minutes = _choice("buffer_minutes", data["buffer_minutes"], BUFFERS)
        if "min_notice_hours" in data:
            row.min_notice_hours = _choice(
                "min_notice_hours", data["min_notice_hours"], NOTICE_HOURS
            )
        if "booking_window_days" in data:
            row.booking_window_days = _choice(
                "booking_window_days", data["booking_window_days"], WINDOW_DAYS
            )
        if "max_per_week" in data:
            profile.capacity_per_week = domain.capacity(data["max_per_week"])
        if "accepting_new" in data:
            profile.paused = not data["accepting_new"]
        if (
            not profile.paused
            and not AvailabilitySlot.objects.filter(
                mentor_id=user_id, kind=AvailabilitySlot.Kind.WEEKLY
            ).exists()
        ):
            raise domain.invalid(
                "accepting_new", "Add at least one weekly time range before accepting mentees."
            )
        _pricing(row, profile, data)
        if "meeting_provider" in data:
            provider = data["meeting_provider"]
            if provider not in ("", "personal", *meetings.provider_names()):
                raise domain.invalid(
                    "meeting_provider", "Choose Google Meet, Zoom or a personal link."
                )
            profile.meeting_provider = provider
        if "personal_link" in data:
            try:
                row.personal_link = (
                    clean_url(data["personal_link"]) if data["personal_link"] else ""
                )
            except exceptions.ValidationError as exc:
                raise domain.invalid("personal_link", " ".join(str(m) for m in exc.detail)) from exc
        if profile.meeting_provider == "personal" and not row.personal_link:
            raise domain.invalid("personal_link", "Add the link people should join.")
        if "about" in data:
            profile.about = domain.text("about", data["about"], limit=domain.MAX_ABOUT, minimum=0)
        if "topics" in data:
            row.topics = _tags("topics", data["topics"], 10)
        for field in ("expertise", "languages", "stages", "industries"):
            if field in data:
                setattr(profile, field, _profile_list(field, data[field]))
        if "timezone" in data:
            profile.timezone = domain.timezone_name(data["timezone"])
        row.save()
        profile.save()
        _guard(profile, before, acknowledge)
    cache.bump()


def _tags(field: str, values: list[str], limit: int) -> list[str]:
    tags: list[str] = []
    for raw in values:
        tag = " ".join(plain(str(raw)).split())
        if not 2 <= len(tag) <= 50:
            raise domain.invalid(field, "Each entry must be 2 to 50 characters.")
        if tag.lower() not in [t.lower() for t in tags]:
            tags.append(tag)
    if len(tags) > limit:
        raise domain.invalid(field, f"At most {limit}.")
    return tags


def _profile_list(field: str, values: list[str]) -> list[str]:
    if field == "expertise":
        return domain.expertise(values)
    if field == "languages":
        return domain.languages(values)
    if field == "stages":
        return domain.stages(values)
    return domain.industries(values)


def _pricing(row: MentorSettings, profile: MentorProfile, data: dict[str, Any]) -> None:
    if "pricing_mode" in data:
        if data["pricing_mode"] not in ("free", "paid"):
            raise domain.invalid("pricing_mode", "Choose free or paid.")
        row.pricing_mode = data["pricing_mode"]
    if "currency" in data:
        if data["currency"] and data["currency"] not in CURRENCIES:
            raise domain.invalid("currency", f"Choose one of: {', '.join(CURRENCIES)}.")
        row.currency = data["currency"]
    if "default_price_minor" in data:
        price = data["default_price_minor"]
        if price is not None and not 1 <= price <= MAX_PRICE_MINOR:
            raise domain.invalid("default_price_minor", "Enter a price above zero.")
        row.default_price_minor = price
    if row.pricing_mode == "paid":
        if not row.currency:
            raise domain.invalid("currency", "Choose a currency.")
        if not row.default_price_minor:
            raise domain.invalid("default_price_minor", "Enter a price above zero.")
    if "prices" in data:
        seen: set[int] = set()
        keep: list[MentorSessionPrice] = []
        for item in data["prices"]:
            length = _choice("prices", item["length_minutes"], LENGTHS)
            if length in seen:
                raise domain.invalid("prices", "One price for each length.")
            seen.add(length)
            if not 1 <= item["price_minor"] <= MAX_PRICE_MINOR:
                raise domain.invalid("prices", "Enter prices above zero.")
            keep.append(
                MentorSessionPrice(
                    mentor_id=profile.user_id,
                    length_minutes=length,
                    price_minor=item["price_minor"],
                )
            )
        MentorSessionPrice.objects.filter(mentor_id=profile.user_id).delete()
        MentorSessionPrice.objects.bulk_create(keep)


# --- what a mentee sees ---


def slots_for(
    profile: MentorProfile, *, start: date | None, end: date | None, length: int | None, tz: str
) -> dict[str, Any]:
    """Bookable times for a length between two dates, in the viewer's time zone."""
    zone = ZoneInfo(domain.timezone_name(tz) if tz else profile.timezone)
    prefs = scheduling.preferences(profile)
    now = timezone.now()
    chosen = length or scheduling.default_length(profile)
    if chosen not in scheduling.offered_lengths(profile):
        raise domain.invalid("length", "This mentor does not offer that length.")
    first = start or now.astimezone(zone).date()
    last = end or first + timedelta(days=min(14, prefs.booking_window_days))
    if last < first or (last - first).days > 31:
        raise domain.invalid("to", "Ask for at most 31 days at a time.")
    lo = datetime.combine(first, time(0, 0), tzinfo=zone).astimezone(UTC)
    hi = datetime.combine(last + timedelta(days=1), time(0, 0), tzinfo=zone).astimezone(UTC)
    starts = (
        []
        if profile.paused
        else [
            s
            for s in scheduling.bookable_starts(
                profile, days=prefs.booking_window_days, now=now, length_minutes=chosen
            )
            if lo <= s < hi
        ]
    )
    quoted = quote(profile, chosen)
    return {
        "mentor_timezone": profile.timezone,
        "timezone": str(zone),
        "length_minutes": chosen,
        "lengths": scheduling.offered_lengths(profile),
        "accepting_new": not profile.paused,
        "price": (
            {
                "price_minor": quoted["price_minor"],
                "currency": quoted["currency"],
                "payment": quoted["payment"],
            }
            if quoted["mode"] == "paid"
            else None
        ),
        "slots": [
            {
                "starts_at": s,
                "ends_at": s + timedelta(minutes=chosen),
                "local_date": s.astimezone(zone).date(),
                "local_time": s.astimezone(zone).strftime("%H:%M"),
            }
            for s in starts
        ],
        "sessions_left_this_week": scheduling.capacity_left(profile),
    }
