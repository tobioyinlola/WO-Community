from django.conf import settings
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateTimeRangeField, IntegerRangeField, RangeOperators
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


class MentorInterest(BaseModel):
    """Ticked "I am also a mentor" at registration. Only a prompt to apply; it grants nothing."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="mentor_interest"
    )


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
    session_minutes = models.PositiveSmallIntegerField(default=45)
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
            models.CheckConstraint(
                condition=Q(session_minutes__in=[30, 45, 60]),
                name="mentorprofile_session_minutes_valid",
            ),
        ]
        indexes = [
            GinIndex(fields=["expertise"], name="mentorprofile_expertise_gin"),
            models.Index(fields=["status", "paused"], name="mentorprofile_listing_idx"),
        ]


class AvailabilitySlot(BaseModel):
    """A window in which a mentor can take sessions: weekly (in the mentor time zone) or one off.

    Windows of one kind cannot overlap for the same mentor; the database enforces it, so two
    concurrent edits cannot leave an ambiguous schedule.
    """

    class Kind(models.TextChoices):
        WEEKLY = "weekly"
        ONE_OFF = "one_off"

    mentor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="availability_slots"
    )
    kind = models.CharField(max_length=8, choices=Kind.choices)
    weekday = models.PositiveSmallIntegerField(null=True, blank=True)  # 0 is Monday
    start_minute = models.PositiveSmallIntegerField(null=True, blank=True)  # from local midnight
    end_minute = models.PositiveSmallIntegerField(null=True, blank=True)
    week_span = IntegerRangeField(null=True, blank=True)  # minutes from Monday 00:00, half open
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    time_span = DateTimeRangeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(kind="weekly")
                    & Q(weekday__gte=0, weekday__lte=6)
                    & Q(start_minute__gte=0, end_minute__lte=1440)
                    & Q(end_minute__gt=models.F("start_minute"))
                    & Q(week_span__isnull=False)
                    & Q(starts_at__isnull=True, ends_at__isnull=True, time_span__isnull=True)
                )
                | (
                    Q(kind="one_off")
                    & Q(starts_at__isnull=False, ends_at__isnull=False, time_span__isnull=False)
                    & Q(ends_at__gt=models.F("starts_at"))
                    & Q(weekday__isnull=True, week_span__isnull=True)
                ),
                name="availabilityslot_shape_valid",
            ),
            ExclusionConstraint(
                name="availabilityslot_weekly_no_overlap",
                expressions=[
                    ("mentor", RangeOperators.EQUAL),
                    ("week_span", RangeOperators.OVERLAPS),
                ],
                condition=Q(kind="weekly"),
            ),
            ExclusionConstraint(
                name="availabilityslot_one_off_no_overlap",
                expressions=[
                    ("mentor", RangeOperators.EQUAL),
                    ("time_span", RangeOperators.OVERLAPS),
                ],
                condition=Q(kind="one_off"),
            ),
        ]
        indexes = [models.Index(fields=["mentor", "kind"], name="availabilityslot_mentor_idx")]


class SeekerNeeds(BaseModel):
    """What a member wants help with, kept so recommendations need no typing each time."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="mentoring_needs"
    )
    needs = models.JSONField(default=list)
    languages = models.JSONField(default=list)
