from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.db import models
from django.db.models import Q

from apps.core.models import BaseModel

JOB_TYPES = ("full_time", "part_time", "contract", "internship", "volunteer", "other")
APPLY_METHODS = ("url", "email")
JOB_STATUSES = ("pending", "published", "closed", "expired", "rejected", "removed")


class Job(BaseModel):
    class Status(models.TextChoices):
        PENDING = "pending"  # waiting for an admin
        PUBLISHED = "published"
        CLOSED = "closed"  # closed by the poster or an admin
        EXPIRED = "expired"
        REJECTED = "rejected"
        REMOVED = "removed"  # taken down by an admin

    class Source(models.TextChoices):
        MEMBER = "member"
        ADMIN = "admin"

    poster = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="jobs_posted"
    )
    startup = models.ForeignKey(
        "startups.Startup", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    # Who is hiring when no startup of ours is named (partners, community-wide roles).
    organisation = models.CharField(max_length=120, blank=True)
    slug = models.SlugField(max_length=90, unique=True)
    title = models.CharField(max_length=140)
    type = models.CharField(max_length=12)
    location = models.CharField(max_length=120, blank=True)
    remote = models.BooleanField(default=False)
    description = models.TextField()  # sanitised HTML
    description_text = models.TextField()  # the same words without markup
    requirements = models.TextField(blank=True)  # sanitised HTML
    compensation = models.CharField(max_length=120, blank=True)
    apply_method = models.CharField(max_length=5)
    apply_target = models.CharField(max_length=300)
    deadline = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    source = models.CharField(max_length=6, choices=Source.choices, default=Source.MEMBER)
    published_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    edited_at = models.DateTimeField(null=True, blank=True)
    expiry_warned_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.CharField(max_length=500, blank=True)
    search_vector = SearchVectorField(null=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(type__in=JOB_TYPES), name="job_type_valid"),
            models.CheckConstraint(
                condition=Q(apply_method__in=APPLY_METHODS), name="job_apply_method_valid"
            ),
            models.CheckConstraint(condition=Q(status__in=JOB_STATUSES), name="job_status_valid"),
            models.CheckConstraint(
                condition=Q(source__in=["member", "admin"]), name="job_source_valid"
            ),
        ]
        indexes = [
            models.Index(fields=["status", "expires_at"], name="job_status_expiry_idx"),
            models.Index(fields=["type", "created_at"], name="job_type_created_idx"),
            models.Index(fields=["poster", "-created_at"], name="job_poster_idx"),
            models.Index(
                fields=["-published_at", "-id"],
                condition=Q(status="published"),
                name="job_published_idx",
            ),
            GinIndex(fields=["search_vector"], name="job_search_idx"),
        ]


class SavedJob(BaseModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="saved_jobs"
    )
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="saves")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "job"], name="saved_job_unique")]
        indexes = [models.Index(fields=["user", "-created_at", "-id"], name="saved_job_list_idx")]


class JobAlert(BaseModel):
    """A saved search that tells the member when matching jobs appear."""

    class Frequency(models.TextChoices):
        INSTANT = "instant"
        DAILY = "daily"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="job_alerts"
    )
    filters = models.JSONField(default=dict)
    frequency = models.CharField(max_length=7, choices=Frequency.choices)
    last_sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["frequency", "last_sent_at"], name="job_alert_due_idx")]


class JobSettings(models.Model):
    """Board-wide settings, edited by a super admin. There is only ever one row."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1)
    require_approval = models.BooleanField(default=True)
    default_duration_days = models.PositiveSmallIntegerField(default=60)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(id=1), name="job_settings_single_row"),
            models.CheckConstraint(
                condition=Q(default_duration_days__gte=1, default_duration_days__lte=365),
                name="job_settings_duration_range",
            ),
        ]

    def __str__(self) -> str:
        return "job board settings"

    @classmethod
    def load(cls) -> "JobSettings":
        row, _ = cls.objects.get_or_create(id=1)
        return row
