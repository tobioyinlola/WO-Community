from typing import Any
from uuid import UUID

import structlog
from celery import shared_task

from apps.core.models import OutboxEvent
from apps.events import services
from apps.events.models import Event, EventRegistration
from apps.notifications import notify

logger = structlog.get_logger(__name__)


def _load(event_id: str) -> tuple[dict[str, Any], Event] | None:
    row = OutboxEvent.objects.filter(pk=event_id).first()
    if row is None:
        logger.warning("outbox_event_missing", event_id=event_id)
        return None
    event = Event.objects.filter(pk=row.payload["event_id"]).first()
    return (dict(row.payload), event) if event is not None else None


@shared_task(name="events.notify_registered")
def notify_registered(event_id: str) -> None:
    loaded = _load(event_id)
    if loaded is None:
        return
    payload, event = loaded
    notify.notify(
        UUID(payload["user_id"]),
        "event_registered",
        {"event_id": str(event.pk), "title": event.title},
        dedupe_key=f"{event_id}:registered",
    )


def _notify_registrants(event_id: str, kind: str) -> None:
    loaded = _load(event_id)
    if loaded is None:
        return
    _, event = loaded
    for user_id in EventRegistration.objects.filter(event=event).values_list("user_id", flat=True):
        notify.notify(
            user_id,
            kind,
            {"event_id": str(event.pk), "title": event.title},
            dedupe_key=f"{event_id}:{kind}",
        )


@shared_task(name="events.notify_cancelled")
def notify_cancelled(event_id: str) -> None:
    _notify_registrants(event_id, "event_cancelled")


@shared_task(name="events.notify_rescheduled")
def notify_rescheduled(event_id: str) -> None:
    _notify_registrants(event_id, "event_rescheduled")


@shared_task(name="events.send_reminders")
def send_reminders() -> int:
    return services.send_reminders()
