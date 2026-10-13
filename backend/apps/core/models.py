from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.ids import uuid7


class BaseModel(models.Model):
    """Identity and timestamps shared by every table."""

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class SoftDeleteModel(models.Model):
    """User content is hidden, not removed, so moderation can recover it."""

    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True

    def soft_delete(self) -> None:
        self.deleted_at = timezone.now()
        self.save(update_fields=["deleted_at", "updated_at"])


class UserStampedModel(models.Model):
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        abstract = True


class OutboxEvent(BaseModel):
    """A side effect recorded in the same transaction as the change that caused it."""

    class Status(models.TextChoices):
        PENDING = "pending"
        PUBLISHED = "published"
        FAILED = "failed"

    topic = models.CharField(max_length=100)
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    available_at = models.DateTimeField(default=timezone.now)
    attempts = models.PositiveSmallIntegerField(default=0)
    published_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)

    class Meta:
        indexes = [models.Index(fields=["status", "available_at"], name="outbox_status_avail_idx")]

    def __str__(self) -> str:
        return f"{self.topic} ({self.status})"


class FailedTask(BaseModel):
    """Dead letter record for a Celery task that exhausted its retries."""

    task_name = models.CharField(max_length=200)
    task_id = models.CharField(max_length=100)
    queue = models.CharField(max_length=50, blank=True)
    args = models.JSONField(default=list)
    kwargs = models.JSONField(default=dict)
    exception = models.TextField()
    replayed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["replayed_at", "created_at"], name="failedtask_open_idx")]

    def __str__(self) -> str:
        return f"{self.task_name} ({self.task_id})"
