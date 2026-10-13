from typing import Any
from uuid import UUID

import structlog
from celery import shared_task
from django.db import transaction

from apps.accounts import services as accounts
from apps.core.models import OutboxEvent
from apps.integrations.email import get_email_adapter
from apps.notifications import adminalerts, centre, emails, notify, services
from apps.notifications.models import AdminAlert

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


@shared_task(name="notifications.send_invitation_email")
def send_invitation_email(event_id: str) -> None:
    event = OutboxEvent.objects.filter(pk=event_id).first()
    if event is None:
        return
    # One transaction: if the email cannot be sent, the link is not kept and a retry starts over.
    with transaction.atomic():
        issued = accounts.issue_invitation_token(
            UUID(event.payload["invitation_id"]), event.payload["nonce"]
        )
        if issued is not None:
            emails.send_invitation(issued.to, issued.token, issued.message, issued.expires_at)


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


def _payload_contact(event_id: str) -> tuple[Any, dict[str, Any]] | None:
    event = OutboxEvent.objects.filter(pk=event_id).first()
    if event is None:
        return None
    contact = accounts.get_contact(UUID(event.payload["user_id"]))
    return (contact, dict(event.payload)) if contact is not None else None


@shared_task(name="notifications.send_suspended_email")
def send_suspended_email(event_id: str) -> None:
    found = _payload_contact(event_id)
    if found is not None:
        emails.send_suspended(found[0].email, found[1].get("reason", ""))


@shared_task(name="notifications.send_removed_email")
def send_removed_email(event_id: str) -> None:
    found = _payload_contact(event_id)
    if found is not None:
        emails.send_removed(found[0].email, found[1].get("reason", ""))


@shared_task(name="notifications.send_reinstated_email")
def send_reinstated_email(event_id: str) -> None:
    found = _payload_contact(event_id)
    if found is not None:
        emails.send_reinstated(found[0].email)


@shared_task(name="notifications.send_password_reset_email")
def send_password_reset_email(event_id: str) -> None:
    user_id = _user_id(event_id)
    if user_id is None:
        return
    issued = accounts.issue_email_token(user_id, accounts.PASSWORD_RESET)
    if issued is not None:
        emails.send_password_reset(*issued)


@shared_task(name="notifications.process_webhook")
def process_webhook(event_id: str) -> None:
    event = OutboxEvent.objects.filter(pk=event_id).first()
    if event is not None:
        services.process_delivery(UUID(event.payload["delivery_id"]), get_email_adapter())


@shared_task(name="notifications.purge_webhooks")
def purge_webhooks() -> int:
    return services.purge_old_deliveries()


@shared_task(name="notifications.notify_approved")
def notify_approved(event_id: str) -> None:
    user_id = _user_id(event_id)
    if user_id is not None:
        notify.notify(user_id, "member_approved", {}, dedupe_key=f"{event_id}:approved")


@shared_task(name="notifications.purge_notifications")
def purge_notifications() -> int:
    return centre.purge_old()


@shared_task(name="notifications.deliver_admin_alert")
def deliver_admin_alert(event_id: str) -> None:
    event = OutboxEvent.objects.filter(pk=event_id).first()
    if event is None:
        return
    alert = AdminAlert.objects.filter(pk=event.payload["alert_id"]).first()
    if alert is None:
        return
    adminalerts.deliver_in_app(alert.pk)
    adminalerts.dispatch(alert.kind)


@shared_task(name="notifications.dispatch_admin_alerts")
def dispatch_admin_alerts() -> int:
    """The sweep that sends the digests whose 15 minutes are up."""
    return adminalerts.dispatch_all()


@shared_task(name="notifications.alert_signup")
def alert_signup(event_id: str) -> None:
    user_id = _user_id(event_id)
    contact = accounts.get_contact(user_id) if user_id else None
    if contact is None:
        return
    adminalerts.raise_alert(
        "member_signup",
        item_key=f"signup:{user_id}",
        what="New member request",
        who=contact.email,
        path=f"/admin/members/{user_id}",
    )
