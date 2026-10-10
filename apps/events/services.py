"""Public commands of the events module."""

import secrets
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import structlog
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.text import slugify
from rest_framework import exceptions

from apps.audit import services as audit
from apps.core import etag
from apps.core import events as domain_events
from apps.core.text import clean_url, plain, rich_post, text_of
from apps.events import domain_events as events
from apps.events.models import EVENT_TYPES, DemoDaySlot, Event, EventRegistration
from apps.integrations.cdn import get_cache_purger
from apps.notifications import notify
from apps.startups import selectors as startups

logger = structlog.get_logger(__name__)

MAX_DESCRIPTION_TEXT = 10_000
MAX_DURATION = timedelta(days=14)
MAX_SLOTS = 20
PUBLIC_API = "/api/v1/public/events"
REMINDERS = (("24h", timedelta(hours=24)), ("1h", timedelta(hours=1)))


class NotFound(exceptions.NotFound):
    default_detail = "Not found."


class Conflict(exceptions.APIException):
    status_code = 409
    default_code = "conflict"


def _invalid(field: str, message: str) -> exceptions.ValidationError:
    return exceptions.ValidationError({field: [message]})


def _purge_cdn(event: Event) -> None:
    try:
        get_cache_purger().purge([PUBLIC_API, f"{PUBLIC_API}/{event.slug}"])
    except Exception:  # public pages expire by themselves
        logger.warning("cdn_purge_failed", event_id=str(event.pk))


def _lock(event_id: UUID) -> Event:
    event = (
        Event.objects.select_for_update()
        .exclude(status=Event.Status.REMOVED)
        .filter(pk=event_id)
        .first()
    )
    if event is None:
        raise NotFound()
    return event


def _url(value: str, field: str) -> str:
    try:
        return clean_url(value)
    except exceptions.ValidationError as exc:
        raise _invalid(field, " ".join(str(m) for m in exc.detail)) from exc


# --- writing events ---


def _apply(event: Event, data: dict[str, Any]) -> None:
    if "type" in data:
        if data["type"] not in EVENT_TYPES:
            raise _invalid("type", "Choose a type from the list.")
        event.type = data["type"]
    if "title" in data:
        event.title = plain(data["title"])
        if not event.title:
            raise _invalid("title", "This field may not be blank.")
    if "description" in data:
        event.description = rich_post(data["description"])
        event.description_text = text_of(event.description)
        if not event.description_text:
            raise _invalid("description", "This field may not be blank.")
        if len(event.description_text) > MAX_DESCRIPTION_TEXT:
            raise _invalid("description", f"Up to {MAX_DESCRIPTION_TEXT} characters.")
    if "timezone" in data:
        try:
            ZoneInfo(data["timezone"])
        except (ZoneInfoNotFoundError, ValueError, OSError) as exc:
            raise _invalid("timezone", "Use a time zone name such as Africa/Lagos.") from exc
        event.timezone = data["timezone"]
    for field in ("starts_at", "ends_at"):
        if field in data:
            setattr(event, field, data[field])
    for field in ("location",):
        if field in data:
            setattr(event, field, plain(data[field]))
    for field in ("link", "recording_url"):
        if field in data:
            setattr(event, field, _url(data[field], field))
    if "summary" in data:
        event.summary = rich_post(data["summary"])
    for field in ("registration_open", "public"):
        if field in data:
            setattr(event, field, bool(data[field]))
    if "capacity" in data:
        event.capacity = data["capacity"]


def _check_times(event: Event) -> None:
    if event.ends_at <= event.starts_at:
        raise _invalid("ends_at", "The event must end after it starts.")
    if event.ends_at - event.starts_at > MAX_DURATION:
        raise _invalid("ends_at", "An event can last at most 14 days.")


def create_event(*, actor: Any, data: dict[str, Any], ip: str = "") -> Event:
    event = Event(
        slug=f"{slugify(data.get('title', ''))[:70] or 'event'}-{secrets.token_hex(3)}",
        created_by=actor,
    )
    _apply(event, data)
    _check_times(event)
    with transaction.atomic():
        event.save()
        audit.record(
            actor=actor, action="events.created", target_type="event", target_id=event.pk, ip=ip
        )
    return event


def update_event(
    *, actor: Any, event_id: UUID, data: dict[str, Any], if_match: str | None, ip: str = ""
) -> Event:
    with transaction.atomic():
        event = _lock(event_id)
        if event.status == Event.Status.CANCELLED:
            raise Conflict("A cancelled event cannot be edited.")
        etag.assert_matches(if_match, event)
        before = (event.starts_at, event.ends_at, event.timezone)
        _apply(event, data)
        _check_times(event)
        registered = event.registrations.count()
        if event.capacity is not None and event.capacity < registered:
            raise _invalid("capacity", f"{registered} people have already registered.")
        event.edited_at = timezone.now()
        event.save()
        audit.record(
            actor=actor, action="events.updated", target_type="event", target_id=event.pk, ip=ip
        )
        if event.status == Event.Status.PUBLISHED:
            if (event.starts_at, event.ends_at, event.timezone) != before:
                event.registrations.update(reminded_24h_at=None, reminded_1h_at=None)
                if registered:
                    domain_events.publish(events.EventRescheduled(event_id=str(event.pk)))
            transaction.on_commit(lambda: _purge_cdn(event))
    return event


def publish(*, actor: Any, event_id: UUID, ip: str = "") -> Event:
    with transaction.atomic():
        event = _lock(event_id)
        if event.status != Event.Status.DRAFT:
            raise Conflict("Only a draft can be published.")
        if event.starts_at <= timezone.now():
            raise _invalid("starts_at", "Move the start into the future before publishing.")
        event.status = Event.Status.PUBLISHED
        event.save(update_fields=["status", "updated_at"])
        audit.record(
            actor=actor, action="events.published", target_type="event", target_id=event.pk, ip=ip
        )
        transaction.on_commit(lambda: _purge_cdn(event))
    return event


def unpublish(*, actor: Any, event_id: UUID, ip: str = "") -> Event:
    """Back to draft. Only while nobody has registered; otherwise cancel instead."""
    with transaction.atomic():
        event = _lock(event_id)
        if event.status != Event.Status.PUBLISHED:
            raise Conflict("Only a published event can be unpublished.")
        if event.registrations.exists():
            raise Conflict("People have registered. Cancel the event to tell them.")
        event.status = Event.Status.DRAFT
        event.save(update_fields=["status", "updated_at"])
        audit.record(
            actor=actor, action="events.unpublished", target_type="event", target_id=event.pk, ip=ip
        )
        transaction.on_commit(lambda: _purge_cdn(event))
    return event


def cancel(*, actor: Any, event_id: UUID, reason: str = "", ip: str = "") -> Event:
    with transaction.atomic():
        event = _lock(event_id)
        if event.status != Event.Status.PUBLISHED:
            raise Conflict("Only a published event can be cancelled.")
        event.status = Event.Status.CANCELLED
        event.registration_open = False
        event.save(update_fields=["status", "registration_open", "updated_at"])
        audit.record(
            actor=actor,
            action="events.cancelled",
            target_type="event",
            target_id=event.pk,
            reason=plain(reason),
            ip=ip,
        )
        domain_events.publish(events.EventCancelled(event_id=str(event.pk)))
        transaction.on_commit(lambda: _purge_cdn(event))
    return event


def remove(*, actor: Any, event_id: UUID, ip: str = "") -> None:
    with transaction.atomic():
        event = _lock(event_id)
        was_public = event.status == Event.Status.PUBLISHED
        event.status = Event.Status.REMOVED
        event.save(update_fields=["status", "updated_at"])
        audit.record(
            actor=actor, action="events.removed", target_type="event", target_id=event.pk, ip=ip
        )
        if was_public:
            transaction.on_commit(lambda: _purge_cdn(event))


def set_slots(*, actor: Any, event_id: UUID, slots: list[dict[str, Any]], ip: str = "") -> Event:
    """Replace a demo day's pitch order. The list order is the pitch order."""
    with transaction.atomic():
        event = _lock(event_id)
        if event.type != "demo_day":
            raise Conflict("Only a demo day has pitch slots.")
        if len(slots) > MAX_SLOTS:
            raise _invalid("slots", f"Up to {MAX_SLOTS} presenting startups.")
        ids = [s["startup_id"] for s in slots]
        if len(set(ids)) != len(ids):
            raise _invalid("slots", "A startup can present once.")
        if set(ids) - startups.existing_ids(ids):
            raise _invalid("slots", "Unknown startup.")
        links = [_url(s.get("pitch_link", ""), "slots") for s in slots]
        event.slots.all().delete()
        DemoDaySlot.objects.bulk_create(
            DemoDaySlot(event=event, startup_id=sid, position=pos, pitch_link=link)
            for pos, (sid, link) in enumerate(zip(ids, links, strict=True), start=1)
        )
        event.save(update_fields=["updated_at"])
        audit.record(
            actor=actor, action="events.slots_set", target_type="event", target_id=event.pk, ip=ip
        )
        if event.status == Event.Status.PUBLISHED:
            transaction.on_commit(lambda: _purge_cdn(event))
    return event


# --- registering ---


def register(*, user_id: UUID, event_id: UUID) -> bool:
    """Register for an event. Returns False if already registered; refuses when full."""
    with transaction.atomic():
        event = (
            Event.objects.select_for_update()
            .filter(pk=event_id, status=Event.Status.PUBLISHED)
            .first()
        )
        if event is None:
            raise NotFound()
        if EventRegistration.objects.filter(event=event, user_id=user_id).exists():
            return False
        if not event.registration_open:
            raise Conflict("Registration for this event is closed.")
        if event.starts_at <= timezone.now():
            raise Conflict("This event has already started.")
        if event.capacity is not None and event.registrations.count() >= event.capacity:
            raise Conflict("This event is full.")
        try:
            EventRegistration.objects.create(event=event, user_id=user_id)
        except IntegrityError:
            return False
        domain_events.publish(
            events.RegistrationConfirmed(event_id=str(event.pk), user_id=str(user_id))
        )
    return True


def unregister(*, user_id: UUID, event_id: UUID) -> bool:
    with transaction.atomic():
        event = (
            Event.objects.select_for_update()
            .filter(pk=event_id, status=Event.Status.PUBLISHED)
            .first()
        )
        if event is None:
            raise NotFound()
        if event.starts_at <= timezone.now():
            raise Conflict("This event has already started.")
        removed, _ = EventRegistration.objects.filter(event=event, user_id=user_id).delete()
    return bool(removed)


def check_in(*, actor: Any, event_id: UUID, user_id: UUID, present: bool, ip: str = "") -> None:
    with transaction.atomic():
        registration = (
            EventRegistration.objects.select_for_update()
            .filter(event_id=event_id, user_id=user_id)
            .first()
        )
        if registration is None:
            raise NotFound()
        registration.checked_in_at = timezone.now() if present else None
        registration.save(update_fields=["checked_in_at", "updated_at"])
        audit.record(
            actor=actor,
            action="events.check_in" if present else "events.check_out",
            target_type="event",
            target_id=event_id,
            after={"user_id": str(user_id)},
            ip=ip,
        )


# --- reminders ---


def send_reminders() -> int:
    """Remind registrants 24 hours and 1 hour before the start.

    Someone who registered inside a window is not sent that window's reminder, because the
    confirmation they just received already said the same thing.
    """
    now = timezone.now()
    sent = 0
    for label, lead in REMINDERS:
        field = f"reminded_{label}_at"
        due = EventRegistration.objects.filter(
            event__status=Event.Status.PUBLISHED,
            event__starts_at__gt=now,
            event__starts_at__lte=now + lead,
            **{f"{field}__isnull": True},
        ).select_related("event")
        for registration in due:
            claimed = EventRegistration.objects.filter(
                pk=registration.pk, **{f"{field}__isnull": True}
            ).update(**{field: now})
            if not claimed or registration.created_at > registration.event.starts_at - lead:
                continue
            notify.notify(
                registration.user_id,
                "event_reminder",
                {
                    "event_id": str(registration.event_id),
                    "title": registration.event.title,
                    "when": label,
                },
                dedupe_key=f"event-reminder:{registration.event_id}:{label}",
            )
            sent += 1
    return sent


# --- calendar ---


def _ics_text(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r", "")
        .replace("\n", "\\n")
    )


def _ics_time(value: datetime) -> str:
    return value.astimezone(ZoneInfo("UTC")).strftime("%Y%m%dT%H%M%SZ")


def calendar_file(event: Event, frontend_url: str) -> str:
    """An iCalendar file that adds the event to any calendar app."""
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//WO Community//Events//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{event.pk}@wocommunity",
        f"DTSTAMP:{_ics_time(timezone.now())}",
        f"DTSTART:{_ics_time(event.starts_at)}",
        f"DTEND:{_ics_time(event.ends_at)}",
        f"SUMMARY:{_ics_text(event.title)}",
        f"DESCRIPTION:{_ics_text(event.description_text[:1000])}",
        f"URL:{frontend_url}/events/{event.pk}",
    ]
    if event.location:
        lines.append(f"LOCATION:{_ics_text(event.location)}")
    if event.status == Event.Status.CANCELLED:
        lines.append("STATUS:CANCELLED")
    lines += ["END:VEVENT", "END:VCALENDAR"]
    return "\r\n".join(lines) + "\r\n"
