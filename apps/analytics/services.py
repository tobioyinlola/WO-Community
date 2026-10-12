"""Recording analytics events.

``track`` is the one way server code records an event. It writes inside the
caller's transaction, so an event exists exactly when the action it describes
committed: nothing is lost on a crash and nothing is recorded for a rolled
back change. Recording must never break the request it is part of, so in
production any failure is logged and swallowed (inside a savepoint, so the
outer transaction stays usable); in tests and local runs it raises so a wrong
event is caught straight away.
"""

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

import structlog
from django.conf import settings
from django.core.cache import cache
from django.db import connection, transaction
from django.db.models import Avg, Count, FloatField
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Cast, TruncDate
from django.utils import timezone

from apps.analytics import registry
from apps.analytics.models import AnalyticsEvent, AnalyticsPreference, ForwardCursor, IdentityLink

logger = structlog.get_logger(__name__)

MAX_BACKDATE = timedelta(hours=24)
OPT_OUT_TTL = 300
FORWARD_EVENTS = "events"


# --- opting out ---


def _opt_out_key(user_id: UUID) -> str:
    return f"analytics:optout:{user_id}"


def is_opted_out(user_id: UUID) -> bool:
    cached = cache.get(_opt_out_key(user_id))
    if cached is not None:
        return bool(cached)
    opted_out = AnalyticsPreference.objects.filter(user_id=user_id, opted_out=True).exists()
    cache.set(_opt_out_key(user_id), opted_out, OPT_OUT_TTL)
    return opted_out


def set_opt_out(user_id: UUID, opted_out: bool) -> None:
    AnalyticsPreference.objects.update_or_create(user_id=user_id, defaults={"opted_out": opted_out})
    cache.set(_opt_out_key(user_id), opted_out, OPT_OUT_TTL)


# --- recording ---


def _clamp(when: datetime | None, now: datetime) -> datetime:
    """A client's clock is not trusted: nothing from the future, nothing over a day old."""
    if when is None or when > now or when < now - MAX_BACKDATE:
        return now
    return when


def track(
    name: str,
    *,
    actor_id: UUID | None = None,
    anonymous_id: UUID | None = None,
    properties: dict[str, Any] | None = None,
    source: str = "server",
    occurred_at: datetime | None = None,
) -> bool:
    """Record one event. Returns True if it was stored."""
    try:
        cleaned = registry.validate(name, properties, from_client=source == "client")
        if actor_id is not None and is_opted_out(actor_id):
            return False
        now = timezone.now()
        with transaction.atomic():  # a savepoint: a failure here cannot poison the caller
            with connection.cursor() as cursor:
                cursor.execute("SELECT nextval('analytics_event_seq')")
                seq = cursor.fetchone()[0]
            AnalyticsEvent.objects.create(
                seq=seq,
                name=name,
                actor_id=actor_id,
                anonymous_id=anonymous_id,
                properties=cleaned,
                source=source,
                occurred_at=_clamp(occurred_at, now),
                received_at=now,
            )
    except Exception as exc:
        if settings.ANALYTICS_STRICT:
            raise
        logger.warning("analytics_event_dropped", event_name=name, reason=str(exc)[:120])
        return False
    return True


def identify(anonymous_id: UUID, user_id: UUID) -> bool:
    """Link a visitor's anonymous id to the member. The first link wins.

    A browser shared by two people keeps its original owner, so one person's
    activity is never credited to another.
    """
    if is_opted_out(user_id):
        return False
    _, created = IdentityLink.objects.get_or_create(
        anonymous_id=anonymous_id, defaults={"user_id": user_id}
    )
    return created


# --- forwarding to the analytics tool ---


def forward_events(send: Callable[[list[dict[str, Any]]], None], limit: int | None = None) -> int:
    """Send the next batch of events, in order, and move the cursor past them.

    The cursor moves only if ``send`` succeeds, and the cursor row is locked
    while sending, so two forwarders never send the same events. Events are
    held back for a short time so one that was numbered early but commits late
    is not skipped: the cursor can only move past events that are old enough
    that every earlier one has committed.
    """
    limit = limit or settings.ANALYTICS_FORWARD_BATCH
    cutoff = timezone.now() - timedelta(seconds=settings.ANALYTICS_FORWARD_DELAY_SECONDS)
    with transaction.atomic():
        ForwardCursor.objects.get_or_create(name=FORWARD_EVENTS)
        cursor = (
            ForwardCursor.objects.select_for_update(skip_locked=True)
            .filter(name=FORWARD_EVENTS)
            .first()
        )
        if cursor is None:
            return 0  # another forwarder is working
        rows = list(
            AnalyticsEvent.objects.filter(
                seq__gt=cursor.last_seq, received_at__lte=cutoff
            ).order_by("seq")[:limit]
        )
        if not rows:
            return 0
        send([_forwarded(row) for row in rows])
        cursor.last_seq = rows[-1].seq
        cursor.save(update_fields=["last_seq"])
    return len(rows)


def _forwarded(row: AnalyticsEvent) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "name": row.name,
        "actor_id": str(row.actor_id) if row.actor_id else None,
        "anonymous_id": str(row.anonymous_id) if row.anonymous_id else None,
        "properties": row.properties,
        "source": row.source,
        "occurred_at": row.occurred_at.isoformat(),
    }


def forward_links(send: Callable[[list[dict[str, str]]], None], limit: int = 200) -> int:
    """Tell the analytics tool which anonymous ids belong to which members."""
    with transaction.atomic():
        links = list(
            IdentityLink.objects.select_for_update(skip_locked=True)
            .filter(forwarded_at__isnull=True)
            .order_by("created_at")[:limit]
        )
        if not links:
            return 0
        send(
            [
                {"anonymous_id": str(link.anonymous_id), "user_id": str(link.user_id)}
                for link in links
            ]
        )
        IdentityLink.objects.filter(pk__in=[link.pk for link in links]).update(
            forwarded_at=timezone.now()
        )
    return len(links)


# --- summaries for dashboards ---


def daily_event_counts(start: datetime, end: datetime) -> dict[tuple[Any, str], int]:
    """How many events of each name were recorded on each day in [start, end)."""
    rows = (
        AnalyticsEvent.objects.filter(occurred_at__gte=start, occurred_at__lt=end)
        .annotate(day=TruncDate("occurred_at"))
        .values("day", "name")
        .annotate(n=Count("id"))
    )
    return {(row["day"], row["name"]): row["n"] for row in rows}


def daily_property_average(
    names: list[str], prop: str, start: datetime, end: datetime
) -> dict[Any, float]:
    """The average of a numeric property across events with these names, per day in [start, end)."""
    rows = (
        AnalyticsEvent.objects.filter(name__in=names, occurred_at__gte=start, occurred_at__lt=end)
        .annotate(
            day=TruncDate("occurred_at"),
            value=Cast(KeyTextTransform(prop, "properties"), FloatField()),
        )
        .values("day")
        .annotate(avg=Avg("value"))
    )
    return {row["day"]: row["avg"] for row in rows if row["avg"] is not None}
