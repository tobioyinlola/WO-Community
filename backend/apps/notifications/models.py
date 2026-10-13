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


class NotificationPreference(BaseModel):
    """A member's per type, per channel choices. Only departures from the defaults are stored."""

    user = models.OneToOneField(
        "accounts.User", on_delete=models.CASCADE, related_name="notification_preference"
    )
    choices = models.JSONField(default=dict, blank=True)
    # Set the first time the member saves their choices, even unchanged.
    confirmed_at = models.DateTimeField(null=True, blank=True)


class Notification(BaseModel):
    """One item in a member's in-app notification centre.

    The payload holds ids and short facts only; the wording is produced when it is read, so a
    name that has since been hidden is never shown and text can be improved without a data fix.
    """

    user = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="notifications"
    )
    type = models.CharField(max_length=30)
    payload = models.JSONField(default=dict, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    channels_sent = models.JSONField(default=list, blank=True)
    # Makes delivery idempotent: a retried event cannot notify the same person twice.
    dedupe_key = models.CharField(max_length=80, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "dedupe_key"],
                condition=~models.Q(dedupe_key=""),
                name="notification_dedupe_unique",
            )
        ]
        indexes = [
            models.Index(fields=["user", "read_at", "-created_at"], name="notification_unread_idx"),
            models.Index(fields=["user", "-created_at", "-id"], name="notification_list_idx"),
        ]


class EmailTemplate(BaseModel):
    """An edited wording for one email template. No row means the built-in wording is used.

    Only the words are stored; the layout, the brand and the variables are code
    (see ``apps.notifications.mailtemplates``).
    """

    key = models.CharField(max_length=40, unique=True)
    subject = models.CharField(max_length=200)
    preheader = models.CharField(max_length=200, blank=True)
    body = models.TextField()
    version = models.PositiveIntegerField(default=1)
    updated_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )


class EmailTemplateVersion(BaseModel):
    """Every wording a template has had, so an earlier one can be put back."""

    template_key = models.CharField(max_length=40)
    version = models.PositiveIntegerField()
    subject = models.CharField(max_length=200)
    preheader = models.CharField(max_length=200, blank=True)
    body = models.TextField()
    saved_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    note = models.CharField(max_length=120, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["template_key", "version"], name="email_template_version_unique"
            )
        ]
        ordering = ["-version"]


class AdminAlert(BaseModel):
    """One item that needs an admin's approval. The key is unique, so raising it twice is safe."""

    kind = models.CharField(max_length=30)
    item_key = models.CharField(max_length=120, unique=True)
    what = models.CharField(max_length=200)
    who = models.CharField(max_length=200, blank=True)
    path = models.CharField(max_length=300)
    in_app = models.BooleanField(default=True)

    class Meta:
        indexes = [models.Index(fields=["kind", "created_at"], name="admin_alert_kind_idx")]


class AdminAlertCursor(BaseModel):
    """What one admin has been told about for one kind, and when, for the 15 minute rule."""

    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="+")
    kind = models.CharField(max_length=30)
    last_sent_at = models.DateTimeField(null=True, blank=True)
    covered_until = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "kind"], name="admin_alert_cursor_unique")
        ]


class AdminAlertPreference(BaseModel):
    """An admin's choice to stop (or resume) approval emails of one kind."""

    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="+")
    kind = models.CharField(max_length=30)
    enabled = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "kind"], name="admin_alert_pref_unique")
        ]
