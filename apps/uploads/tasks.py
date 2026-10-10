from uuid import UUID

from celery import shared_task

from apps.core.models import OutboxEvent
from apps.uploads import services


@shared_task(name="uploads.process_upload")
def process_upload(event_id: str) -> None:
    event = OutboxEvent.objects.filter(pk=event_id).first()
    if event is not None:
        services.process_upload(UUID(event.payload["upload_id"]))


@shared_task(name="uploads.cleanup")
def cleanup() -> dict[str, int]:
    return services.cleanup()
