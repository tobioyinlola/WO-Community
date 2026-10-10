"""Email delivery bookkeeping: webhook intake, processing and suppression."""

import hashlib
import json
from collections.abc import Callable
from datetime import timedelta
from typing import Any
from uuid import UUID

import structlog
from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core import events as domain_events
from apps.integrations.email import EmailAdapter
from apps.notifications import events
from apps.notifications.models import (
    DeliveryEvent,
    Suppression,
    SuppressionReason,
    WebhookDelivery,
)

logger = structlog.get_logger(__name__)

# Delivery outcomes that mean we must stop sending marketing mail to the address.
SUPPRESSING = {"bounced": SuppressionReason.BOUNCED, "complained": SuppressionReason.COMPLAINED}


class InvalidWebhook(Exception):
    pass


def hash_email(email: str) -> str:
    return hashlib.sha256(email.strip().lower().encode()).hexdigest()


def is_suppressed(email: str) -> bool:
    return Suppression.objects.filter(email_hash=hash_email(email)).exists()


def suppress(email: str, reason: str) -> None:
    Suppression.objects.get_or_create(email_hash=hash_email(email), defaults={"reason": reason})


# --- intake ---


def accept_webhook(adapter: EmailAdapter, body: bytes, headers: dict[str, str]) -> bool:
    """Verify, store and queue one delivery. Returns False for a repeat.

    Raises ``InvalidWebhook`` if the signature or body is bad. Nothing is
    processed here: the caller can answer the provider immediately.
    """
    if not adapter.verify_webhook(body, headers):
        raise InvalidWebhook("signature")
    event_id = adapter.webhook_event_id(headers)
    try:
        payload = json.loads(body)
    except ValueError as exc:
        raise InvalidWebhook("body") from exc
    if not event_id or not isinstance(payload, dict):
        raise InvalidWebhook("body")
    try:
        with transaction.atomic():
            delivery = WebhookDelivery.objects.create(
                provider=adapter.provider_name, event_id=event_id, payload=payload
            )
            domain_events.publish(events.WebhookReceived(delivery_id=str(delivery.pk)))
    except IntegrityError:
        return False  # the provider sent this one before
    return True


# --- processing (runs in a worker) ---


# Code in modules above this one (such as campaign reporting) can ask to hear about each new
# delivery event, without this module having to know about them.
DeliveryListener = Callable[[str, str], None]
_delivery_listeners: list[DeliveryListener] = []


def add_delivery_listener(listener: DeliveryListener) -> None:
    if listener not in _delivery_listeners:
        _delivery_listeners.append(listener)


def unsuppress_unsubscribed(email: str) -> None:
    """Let an address that unsubscribed be mailed again. Bounces and complaints stay blocked."""
    Suppression.objects.filter(
        email_hash=hash_email(email), reason=SuppressionReason.UNSUBSCRIBED
    ).delete()


def process_delivery(delivery_id: UUID, adapter: EmailAdapter) -> int:
    """Turn a stored delivery into events and suppressions. Safe to run twice."""
    with transaction.atomic():
        delivery = WebhookDelivery.objects.select_for_update().filter(pk=delivery_id).first()
        if delivery is None or delivery.processed_at is not None:
            return 0
        recorded = 0
        for event in adapter.parse_event(delivery.payload):
            _, created = DeliveryEvent.objects.get_or_create(
                delivery=delivery,
                kind=event.kind,
                provider_message_id=event.provider_message_id,
                email_hash=hash_email(event.email),
                defaults={"occurred_at": event.occurred_at[:40]},
            )
            recorded += int(created)
            if created:
                for listener in _delivery_listeners:
                    listener(event.kind, event.provider_message_id)
            reason = SUPPRESSING.get(event.kind)
            if reason is not None:
                suppress(event.email, reason)
                logger.warning(
                    "email_suppressed", reason=reason, email_hash=hash_email(event.email)[:12]
                )
        delivery.processed_at = timezone.now()
        delivery.save(update_fields=["processed_at", "updated_at"])
    return recorded


def purge_old_deliveries(now: Any = None) -> int:
    """Raw deliveries hold recipient addresses, so they are not kept for long."""
    cutoff = (now or timezone.now()) - timedelta(days=settings.EMAIL_WEBHOOK_RETENTION_DAYS)
    deleted, _ = WebhookDelivery.objects.filter(
        processed_at__isnull=False, created_at__lt=cutoff
    ).delete()
    return int(deleted)


def suppressed_among(emails: list[str]) -> set[str]:
    """Which of these addresses (lower-cased) are on the suppression list."""
    by_hash = {hash_email(e): e.strip().lower() for e in emails}
    found = Suppression.objects.filter(email_hash__in=list(by_hash)).values_list(
        "email_hash", flat=True
    )
    return {by_hash[h] for h in found}


def change_marketing_consent(user_id: UUID, email: str, granted: bool, *, ip: str = "") -> None:
    """Record the member's choice about marketing email and keep the suppression list in step."""
    from apps.accounts import services as accounts

    with transaction.atomic():
        accounts.set_marketing_consent(user_id, granted, ip=ip)
        if granted:
            unsuppress_unsubscribed(email)
        else:
            suppress(email, SuppressionReason.UNSUBSCRIBED)
