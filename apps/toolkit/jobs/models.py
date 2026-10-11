from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import BaseModel

JOB_STATUSES = ("queued", "running", "succeeded", "failed", "cancelled")


class AIJob(BaseModel):
    """One long operation: queued, run by a worker, polled by the front end."""

    class Status(models.TextChoices):
        QUEUED = "queued"
        RUNNING = "running"
        SUCCEEDED = "succeeded"
        FAILED = "failed"
        CANCELLED = "cancelled"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="toolkit_jobs"
    )
    venture = models.ForeignKey(
        "tk_ventures.Venture", null=True, blank=True, on_delete=models.CASCADE, related_name="jobs"
    )
    kind = models.CharField(max_length=60)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.QUEUED)
    progress = models.PositiveSmallIntegerField(default=0)
    step_label = models.CharField(max_length=120, blank=True)
    payload = models.JSONField(default=dict)  # what to do; never member text in logs
    result_ref = models.JSONField(default=dict)  # what was made: {"type": "plan", "id": ...}
    error_code = models.CharField(max_length=40, blank=True)
    error_detail = models.CharField(max_length=300, blank=True)  # safe to show the member
    idempotency_key = models.CharField(max_length=80, blank=True)
    group_id = models.UUIDField(null=True, blank=True)  # jobs started together
    cancel_requested = models.BooleanField(default=False)
    attempts = models.PositiveSmallIntegerField(default=0)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=JOB_STATUSES), name="tk_job_status_valid"
            ),
            models.CheckConstraint(condition=Q(progress__lte=100), name="tk_job_progress_range"),
            # The same key from the same member for the same kind is the same job.
            models.UniqueConstraint(
                fields=["owner", "kind", "idempotency_key"],
                condition=~Q(idempotency_key=""),
                name="tk_job_idempotency_unique",
            ),
        ]
        indexes = [
            models.Index(fields=["owner", "-created_at"], name="tk_job_owner_idx"),
            models.Index(fields=["status", "created_at"], name="tk_job_status_idx"),
            models.Index(fields=["group_id"], name="tk_job_group_idx"),
        ]
