from django.db import models

from apps.core.models import BaseModel


class WebhookDelivery(BaseModel):
    """One signed delivery from the email provider, stored exactly as received.

    The provider's delivery id is unique, so a repeated delivery is recognised
    and ignored. Processing happens later in a worker.
    """

    provider = models.CharField(max_length=20)
    event_id = models.CharField(max_length=100)
    payload = models.JSONField()
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["provider", "event_id"], name="webhook_delivery_unique")
        ]
        indexes = [models.Index(fields=["processed_at", "created_at"], name="webhook_pending_idx")]

    def __str__(self) -> str:
        return f"{self.provider}:{self.event_id}"


class DeliveryEvent(BaseModel):
    """What happened to a message we sent: delivered, bounced, complained and so on.

    Addresses are kept only as a hash.
    """

    delivery = models.ForeignKey(WebhookDelivery, on_delete=models.CASCADE, related_name="events")
    kind = models.CharField(max_length=20)
    provider_message_id = models.CharField(max_length=100)
    email_hash = models.CharField(max_length=64)
    occurred_at = models.CharField(max_length=40, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["delivery", "kind", "provider_message_id", "email_hash"],
                name="delivery_event_unique",
            )
        ]
        indexes = [
            models.Index(fields=["provider_message_id"], name="delivery_event_message_idx"),
            models.Index(fields=["email_hash", "kind"], name="delivery_event_email_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.kind} {self.provider_message_id}"


class SuppressionReason(models.TextChoices):
    BOUNCED = "bounced"
    COMPLAINED = "complained"
    UNSUBSCRIBED = "unsubscribed"


class Suppression(BaseModel):
    """An address we must not send marketing mail to. Checked before every marketing send."""

    email_hash = models.CharField(max_length=64, unique=True)
    reason = models.CharField(max_length=12, choices=SuppressionReason.choices)

    def __str__(self) -> str:
        return f"{self.reason} {self.email_hash[:8]}"
