"""Transactional outbox.

``enqueue`` writes a row inside the caller's transaction, so a side effect
exists if and only if the business change committed. ``dispatch_pending`` runs
in a worker, claims rows with SKIP LOCKED so several publishers can run side by
side, and hands each row to the Celery tasks registered for its topic.
"""

from collections import defaultdict
from datetime import timedelta
from typing import Any

import structlog
from celery import current_app
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.core.models import OutboxEvent

logger = structlog.get_logger(__name__)

# topic -> (celery task name, queue)
_handlers: dict[str, list[tuple[str, str]]] = defaultdict(list)


def register_handler(topic: str, task_name: str, queue: str = "default") -> None:
    entry = (task_name, queue)
    if entry not in _handlers[topic]:
        _handlers[topic].append(entry)


def handlers_for(topic: str) -> list[tuple[str, str]]:
    return list(_handlers.get(topic, []))


def enqueue(topic: str, payload: dict[str, Any]) -> OutboxEvent:
    return OutboxEvent.objects.create(topic=topic, payload=payload)


def purge_published(older_than_days: int = 14) -> int:
    """Delete published events once nobody needs them. Failed ones are kept for review."""
    cutoff = timezone.now() - timedelta(days=older_than_days)
    deleted, _ = OutboxEvent.objects.filter(
        status=OutboxEvent.Status.PUBLISHED, published_at__lt=cutoff
    ).delete()
    return int(deleted)


def _backoff(attempts: int) -> timedelta:
    return timedelta(seconds=min(2**attempts * 5, 3600))


def dispatch_pending(batch_size: int = 100) -> int:
    """Publish due events. Returns the number of events published."""
    published = 0
    with transaction.atomic():
        due = list(
            OutboxEvent.objects.select_for_update(skip_locked=True)
            .filter(status=OutboxEvent.Status.PENDING, available_at__lte=timezone.now())
            .order_by("created_at")[:batch_size]
        )
        for event in due:
            try:
                for task_name, queue in handlers_for(event.topic):
                    current_app.send_task(task_name, args=[str(event.id)], queue=queue)
            except Exception as exc:
                _mark_failure(event, exc)
                continue
            event.status = OutboxEvent.Status.PUBLISHED
            event.published_at = timezone.now()
            event.save(update_fields=["status", "published_at", "updated_at"])
            published += 1
    return published


def _mark_failure(event: OutboxEvent, exc: Exception) -> None:
    event.attempts += 1
    event.last_error = repr(exc)[:2000]
    if event.attempts >= settings.OUTBOX_MAX_ATTEMPTS:
        event.status = OutboxEvent.Status.FAILED
        logger.error("outbox_event_failed", event_id=str(event.id), topic=event.topic)
    else:
        event.available_at = timezone.now() + _backoff(event.attempts)
    event.save(update_fields=["status", "attempts", "last_error", "available_at", "updated_at"])
