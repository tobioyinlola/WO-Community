from uuid import UUID

import structlog
from celery import shared_task

from apps.accounts import services as accounts
from apps.core.models import OutboxEvent
from apps.notifications import emails

logger = structlog.get_logger(__name__)


def _user_id(event_id: str) -> UUID | None:
    event = OutboxEvent.objects.filter(pk=event_id).first()
    if event is None:
        logger.warning("outbox_event_missing", event_id=event_id)
        return None
    return UUID(event.payload["user_id"])


@shared_task(name="notifications.send_verification_email")
def send_verification_email(event_id: str) -> None:
    user_id = _user_id(event_id)
    if user_id is None:
        return
    issued = accounts.issue_email_token(user_id, accounts.VERIFY_EMAIL)
    if issued is not None:
        emails.send_verification(*issued)


@shared_task(name="notifications.send_already_registered_email")
def send_already_registered_email(event_id: str) -> None:
    user_id = _user_id(event_id)
    contact = accounts.get_contact(user_id) if user_id else None
    if contact is not None:
        emails.send_already_registered(contact.email)


@shared_task(name="notifications.send_approved_email")
def send_approved_email(event_id: str) -> None:
    user_id = _user_id(event_id)
    contact = accounts.get_contact(user_id) if user_id else None
    if contact is not None:
        emails.send_approved(contact.email)


@shared_task(name="notifications.send_rejected_email")
def send_rejected_email(event_id: str) -> None:
    event = OutboxEvent.objects.filter(pk=event_id).first()
    if event is None:
        return
    contact = accounts.get_contact(UUID(event.payload["user_id"]))
    if contact is not None:
        emails.send_rejected(contact.email, event.payload["reason"])


@shared_task(name="notifications.send_password_reset_email")
def send_password_reset_email(event_id: str) -> None:
    user_id = _user_id(event_id)
    if user_id is None:
        return
    issued = accounts.issue_email_token(user_id, accounts.PASSWORD_RESET)
    if issued is not None:
        emails.send_password_reset(*issued)
