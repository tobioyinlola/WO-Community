"""Read side of the events module."""

import csv
import io
from typing import Any
from uuid import UUID

from django.conf import settings
from django.db.models import Count, QuerySet
from django.utils import timezone
from rest_framework import exceptions

from apps.accounts import services as accounts
from apps.core.keyset import paginate
from apps.events.models import DemoDaySlot, Event, EventRegistration
from apps.profiles import selectors as profiles
from apps.startups import selectors as startups

EXCERPT = 200
FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")


def live() -> QuerySet[Event]:
    """Events members can see: published or cancelled (so people see why it is gone)."""
    return Event.objects.filter(status__in=[Event.Status.PUBLISHED, Event.Status.CANCELLED])


def _excerpt(event: Event) -> str:
    text = event.description_text
    return text if len(text) <= EXCERPT else text[: EXCERPT - 1] + "…"


def _views(
    viewer: Any, events: list[Event], *, public: bool = False, detail: bool = False
) -> list[dict[str, Any]]:
    ids = [e.pk for e in events]
    counts = dict(
        EventRegistration.objects.filter(event_id__in=ids)
        .values_list("event_id")
        .annotate(n=Count("id"))
    )
    mine = (
        set(
            EventRegistration.objects.filter(user_id=viewer.pk, event_id__in=ids).values_list(
                "event_id", flat=True
            )
        )
        if not public
        else set()
    )
    slots = {e.pk: list(e.slots.all()) for e in events} if detail else {}
    cards = (
        startups.cards_for(viewer, [s.startup_id for row in slots.values() for s in row])
        if detail
        else {}
    )
    now = timezone.now()
    views = []
    for event in events:
        registered = counts.get(event.pk, 0)
        past = event.ends_at <= now
        view: dict[str, Any] = {
            "id": event.pk,
            "slug": event.slug,
            "type": event.type,
            "title": event.title,
            "excerpt": _excerpt(event),
            "starts_at": event.starts_at,
            "ends_at": event.ends_at,
            "timezone": event.timezone,
            "location": event.location,
            "status": event.status,
            "past": past,
        }
        if not public:
            view.update(
                capacity=event.capacity,
                registered_count=registered,
                spots_left=None if event.capacity is None else max(event.capacity - registered, 0),
                registration_open=event.registration_open
                and event.status == Event.Status.PUBLISHED
                and not past,
                registered=event.pk in mine,
            )
        if detail:
            view.update(
                description=event.description,
                link=event.link if not public else "",
                recording_url=event.recording_url if past else "",
                summary=event.summary if past else "",
                slots=[
                    {
                        "position": s.position,
                        "pitch_link": s.pitch_link,
                        "startup": cards[s.startup_id],
                    }
                    for s in slots[event.pk]
                    if s.startup_id in cards
                ],
            )
        views.append(view)
    return views


def listing(
    viewer: Any, *, when: str, type: str, registered: bool, cursor: str, limit: int  # noqa: A002
) -> dict[str, Any]:
    now = timezone.now()
    queryset = live()
    if type:
        queryset = queryset.filter(type=type)
    if registered:
        queryset = queryset.filter(registrations__user_id=viewer.pk)
    if when == "past":
        queryset = queryset.filter(ends_at__lte=now, status=Event.Status.PUBLISHED)
        fields, descending = ("starts_at", "id"), True
    else:
        queryset = queryset.filter(ends_at__gt=now)
        fields, descending = ("starts_at", "id"), False
    rows, next_cursor = paginate(
        queryset,
        fields=fields,
        sort=f"events:{when}",
        cursor=cursor,
        limit=limit,
        descending=descending,
    )
    return {"results": _views(viewer, rows), "next_cursor": next_cursor}


def get_event(viewer: Any, event_id: UUID) -> tuple[Event, dict[str, Any]]:
    event = live().prefetch_related("slots").filter(pk=event_id).first()
    if event is None:
        raise exceptions.NotFound()
    return event, _views(viewer, [event], detail=True)[0]


# --- public ---


def public_listing(
    *, when: str, type: str, cursor: str, limit: int
) -> dict[str, Any]:  # noqa: A002
    now = timezone.now()
    queryset = Event.objects.filter(status=Event.Status.PUBLISHED, public=True)
    if type:
        queryset = queryset.filter(type=type)
    queryset = (
        queryset.filter(ends_at__lte=now) if when == "past" else queryset.filter(ends_at__gt=now)
    )
    rows, next_cursor = paginate(
        queryset,
        fields=("starts_at", "id"),
        sort=f"public-events:{when}",
        cursor=cursor,
        limit=limit,
        descending=when == "past",
    )
    keep = (
        "slug",
        "type",
        "title",
        "excerpt",
        "starts_at",
        "ends_at",
        "timezone",
        "location",
        "past",
    )
    return {
        "results": [{k: v[k] for k in keep} for v in _views(None, rows, public=True)],
        "next_cursor": next_cursor,
    }


def public_detail(slug: str) -> dict[str, Any]:
    event = (
        Event.objects.filter(status=Event.Status.PUBLISHED, public=True, slug=slug)
        .prefetch_related("slots")
        .first()
    )
    if event is None:
        raise exceptions.NotFound()
    view = _views(None, [event], public=True, detail=True)[0]
    url = f"{settings.FRONTEND_BASE_URL}/events/{event.slug}"
    return {
        **{
            k: view[k]
            for k in (
                "slug",
                "type",
                "title",
                "excerpt",
                "starts_at",
                "ends_at",
                "timezone",
                "location",
                "past",
            )
        },
        "description": view["description"],
        "recording_url": view["recording_url"],
        "summary": view["summary"],
        "slots": view["slots"],
        "share_url": url,
        "open_graph": {
            "title": event.title,
            "description": view["excerpt"],
            "url": url,
            "type": "website",
            "image": None,
        },
    }


# --- admin ---


def admin_queryset(*, status: str, type: str, q: str) -> QuerySet[Event]:  # noqa: A002
    queryset = Event.objects.exclude(status=Event.Status.REMOVED)
    if status:
        queryset = queryset.filter(status=status)
    if type:
        queryset = queryset.filter(type=type)
    if q:
        queryset = queryset.filter(title__icontains=q)
    return queryset.order_by("-starts_at", "-id")


def admin_views(actor: Any, events: list[Event], *, detail: bool = False) -> list[dict[str, Any]]:
    views = _views(actor, events, detail=detail)
    for event, view in zip(events, views, strict=True):
        view.update(
            public=event.public,
            registration_open=event.registration_open,
            created_by=event.created_by_id,
            created_at=event.created_at,
            edited_at=event.edited_at,
            description=event.description,
            link=event.link,
            recording_url=event.recording_url,
            summary=event.summary,
        )
    return views


def attendees(event_id: UUID) -> QuerySet[EventRegistration]:
    return EventRegistration.objects.filter(event_id=event_id).order_by("created_at", "id")


def attendee_views(actor: Any, rows: list[EventRegistration]) -> list[dict[str, Any]]:
    cards = profiles.cards_for(actor, [r.user_id for r in rows])
    emails = {uid: _email(uid) for uid in {r.user_id for r in rows}}
    return [
        {
            "user_id": r.user_id,
            "name": cards[r.user_id]["name"],
            "email": emails[r.user_id],
            "registered_at": r.created_at,
            "checked_in_at": r.checked_in_at,
        }
        for r in rows
    ]


def _email(user_id: UUID) -> str:
    contact = accounts.get_contact(user_id)
    return contact.email if contact else ""


def _safe_cell(value: Any) -> str:
    """Text that a spreadsheet will show as text, never run as a formula."""
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(FORMULA_STARTS) else text


def attendees_csv(actor: Any, event_id: UUID) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["name", "email", "registered_at", "checked_in_at"])
    for row in attendee_views(actor, list(attendees(event_id))):
        writer.writerow(
            [
                _safe_cell(row["name"]),
                _safe_cell(row["email"]),
                row["registered_at"].isoformat(),
                row["checked_in_at"].isoformat() if row["checked_in_at"] else "",
            ]
        )
    return out.getvalue()


def slot_exists(event: Event) -> bool:
    return DemoDaySlot.objects.filter(event=event).exists()
