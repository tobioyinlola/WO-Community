from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import BaseModel

CAMPAIGN_STATUSES = ("draft", "scheduled", "sending", "paused", "sent", "cancelled")


class Segment(BaseModel):
    """A saved audience: a validated JSON definition compiled into queries when used."""

    name = models.CharField(max_length=100)
    definition = models.JSONField(default=dict)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        indexes = [models.Index(fields=["-created_at"], name="segment_recent_idx")]


class CampaignTemplate(BaseModel):
    name = models.CharField(max_length=100)
    blocks = models.JSONField(default=list)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )


class Campaign(BaseModel):
    class Status(models.TextChoices):
        DRAFT = "draft"
        SCHEDULED = "scheduled"
        SENDING = "sending"
        PAUSED = "paused"  # the kill switch: nothing more is sent until resumed
        SENT = "sent"
        CANCELLED = "cancelled"

    name = models.CharField(max_length=120)
    subject = models.CharField(max_length=150)
    preheader = models.CharField(max_length=150, blank=True)
    blocks = models.JSONField(default=list)
    segment = models.ForeignKey(
        Segment, null=True, blank=True, on_delete=models.SET_NULL, related_name="campaigns"
    )
    # The audience as it was when sending began, kept for the record.
    segment_snapshot = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    scheduled_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    recipient_count = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=CAMPAIGN_STATUSES), name="campaign_status_valid"
            )
        ]
        indexes = [models.Index(fields=["status", "scheduled_at"], name="campaign_due_idx")]


class CampaignRecipient(BaseModel):
    class Status(models.TextChoices):
        QUEUED = "queued"
        SENT = "sent"
        SKIPPED = "skipped"  # no longer eligible when its turn came (unsubscribed, suppressed)
        FAILED = "failed"

    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name="recipients")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.QUEUED)
    provider_message_id = models.CharField(max_length=100, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    opened_at = models.DateTimeField(null=True, blank=True)
    clicked_at = models.DateTimeField(null=True, blank=True)
    bounced_at = models.DateTimeField(null=True, blank=True)
    complained_at = models.DateTimeField(null=True, blank=True)
    unsubscribed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["campaign", "user"], name="campaign_recipient_unique")
        ]
        indexes = [
            models.Index(fields=["campaign", "status"], name="campaign_recipient_status_idx"),
            models.Index(fields=["provider_message_id"], name="campaign_message_idx"),
        ]
