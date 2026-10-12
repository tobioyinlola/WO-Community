from uuid import UUID

from celery import shared_task

from apps.core.models import OutboxEvent
from apps.directory import services


def _payload(event_id: str) -> dict[str, str] | None:
    event = OutboxEvent.objects.filter(pk=event_id).first()
    return event.payload if event else None


@shared_task(name="directory.refresh_startup")
def refresh_startup(event_id: str) -> None:
    payload = _payload(event_id)
    if payload:
        services.refresh_startup(UUID(payload["startup_id"]))


@shared_task(name="directory.refresh_member")
def refresh_member(event_id: str) -> None:
    payload = _payload(event_id)
    if payload:
        services.refresh_member(UUID(payload["user_id"]))


@shared_task(name="directory.take_down_member")
def take_down_member(event_id: str) -> None:
    payload = _payload(event_id)
    if payload:
        services.take_down_member(UUID(payload["user_id"]))


@shared_task(name="directory.reference_changed")
def reference_changed(event_id: str) -> None:
    payload = _payload(event_id)
    if payload:
        services.refresh_for_reference(payload["kind"], payload["slug"])


@shared_task(name="directory.reconcile")
def reconcile() -> dict[str, int]:
    return services.reconcile()
