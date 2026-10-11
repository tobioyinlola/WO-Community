from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.db import models
from django.db.models import Q

from apps.core.models import BaseModel

APPLICATION_STATUSES = ("pending", "info_requested", "approved", "declined", "withdrawn")
OPEN_STATUSES = ("pending", "info_requested")


class MentorApplication(BaseModel):
    class Status(models.TextChoices):
        PENDING = "pending"
        INFO_REQUESTED = "info_requested"
        APPROVED = "approved"
        DECLINED = "declined"
        WITHDRAWN = "withdrawn"

    applicant = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="mentor_applications"
    )
    expertise = models.JSONField(default=list)  # free tags, lower case
    years_experience = models.PositiveSmallIntegerField()
    current_role = models.CharField(max_length=120)
    company = models.CharField(max_length=120)
    linkedin_url = models.CharField(max_length=300)
    industries = models.JSONField(default=list)  # sector slugs
    stages = models.JSONField(default=list)  # stage slugs
    languages = models.JSONField(default=list)  # ISO 639-1 codes
    timezone = models.CharField(max_length=64)
    weekly_hours = models.PositiveSmallIntegerField()
    availability_note = models.CharField(max_length=500, blank=True)
    motivation = models.TextField()
    conduct_accepted_at = models.DateTimeField()
    status = models.CharField(max_length=14, choices=Status.choices, default=Status.PENDING)
    decision_reason = models.TextField(blank=True)  # the decline reason, or what is asked for
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=APPLICATION_STATUSES), name="mentorapp_status_valid"
            ),
            # One live application per person; the database settles a double submit.
            models.UniqueConstraint(
                fields=["applicant"],
                condition=Q(status__in=OPEN_STATUSES),
                name="mentorapp_one_open_per_applicant",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "created_at"], name="mentorapp_status_created_idx"),
        ]


class MentorProfile(BaseModel):
    class Status(models.TextChoices):
        ACTIVE = "active"
        REVOKED = "revoked"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="mentor_profile"
    )
    application = models.ForeignKey(
        MentorApplication, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    about = models.CharField(max_length=1000, blank=True)
    expertise = models.JSONField(default=list)
    years_experience = models.PositiveSmallIntegerField()
    current_role = models.CharField(max_length=120)
    company = models.CharField(max_length=120)
    industries = models.JSONField(default=list)
    stages = models.JSONField(default=list)
    languages = models.JSONField(default=list)
    timezone = models.CharField(max_length=64)
    capacity_per_week = models.PositiveSmallIntegerField(default=3)
    paused = models.BooleanField(default=False)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.ACTIVE)
    approved_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    revoke_reason = models.TextField(blank=True)
    rating_count = models.PositiveIntegerField(default=0)
    rating_total = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=["active", "revoked"]), name="mentorprofile_status_valid"
            ),
            models.CheckConstraint(
                condition=Q(capacity_per_week__gte=1, capacity_per_week__lte=20),
                name="mentorprofile_capacity_range",
            ),
        ]
        indexes = [
            GinIndex(fields=["expertise"], name="mentorprofile_expertise_gin"),
            models.Index(fields=["status", "paused"], name="mentorprofile_listing_idx"),
        ]
