from uuid import UUID

from celery import shared_task

from apps.core.models import OutboxEvent
from apps.profiles import services


@shared_task(name="profiles.create_from_signup")
def create_from_signup(event_id: str) -> None:
    event = OutboxEvent.objects.filter(pk=event_id).first()
    if event is None:
        return
    services.create_from_signup(UUID(event.payload["user_id"]), event.payload["details"]["profile"])
