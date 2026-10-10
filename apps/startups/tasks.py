from uuid import UUID

from celery import shared_task

from apps.accounts import services as accounts
from apps.core.models import OutboxEvent
from apps.startups import services


@shared_task(name="startups.create_from_signup")
def create_from_signup(event_id: str) -> None:
    event = OutboxEvent.objects.filter(pk=event_id).first()
    if event is None:
        return
    services.create_from_signup(UUID(event.payload["user_id"]), event.payload["details"]["startup"])


@shared_task(name="startups.link_invited_member")
def link_invited_member(event_id: str) -> None:
    """When someone is approved, attach them to teams that listed their email."""
    event = OutboxEvent.objects.filter(pk=event_id).first()
    if event is None:
        return
    user_id = UUID(event.payload["user_id"])
    contact = accounts.get_contact(user_id)
    if contact is not None:
        services.link_invited(user_id, contact.email)
