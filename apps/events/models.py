from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import BaseModel

EVENT_TYPES = ("demo_day", "workshop", "meetup", "announcement")
EVENT_STATUSES = ("draft", "published", "cancelled", "removed")


class Event(BaseModel):
    class Status(models.TextChoices):
        DRAFT = "draft"
        PUBLISHED = "published"
        CANCELLED = "cancelled"
        REMOVED = "removed"

    type = models.CharField(max_length=12)
    slug = models.SlugField(max_length=90, unique=True)
    title = models.CharField(max_length=160)
    description = models.TextField()  # sanitised HTML
    description_text = models.TextField()
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    # The place the event happens in; times are stored in UTC and shown in this zone.
    timezone = models.CharField(max_length=64, default="UTC")
    location = models.CharField(max_length=200, blank=True)
    link = models.CharField(max_length=300, blank=True)  # where to join online
    capacity = models.PositiveIntegerField(null=True, blank=True)  # blank means unlimited
    registration_open = models.BooleanField(default=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    public = models.BooleanField(default=False)
    # After the event: the archive.
    recording_url = models.CharField(max_length=300, blank=True)
    summary = models.TextField(blank=True)  # sanitised HTML
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    edited_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(type__in=EVENT_TYPES), name="event_type_valid"),
            models.CheckConstraint(
                condition=Q(status__in=EVENT_STATUSES), name="event_status_valid"
            ),
            models.CheckConstraint(
                condition=Q(ends_at__gt=models.F("starts_at")), name="event_ends_after_start"
            ),
        ]
        indexes = [
            models.Index(fields=["status", "starts_at"], name="event_status_start_idx"),
            models.Index(fields=["type", "starts_at"], name="event_type_start_idx"),
        ]


class EventRegistration(BaseModel):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="registrations")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="event_registrations"
    )
    checked_in_at = models.DateTimeField(null=True, blank=True)
    reminded_24h_at = models.DateTimeField(null=True, blank=True)
    reminded_1h_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["event", "user"], name="event_registration_unique")
        ]
        indexes = [models.Index(fields=["user", "-created_at"], name="event_reg_user_idx")]


class DemoDaySlot(BaseModel):
    """One startup's pitch slot at a demo day."""

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="slots")
    startup = models.ForeignKey("startups.Startup", on_delete=models.CASCADE, related_name="+")
    position = models.PositiveSmallIntegerField()
    pitch_link = models.CharField(max_length=300, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["event", "position"], name="slot_position_unique"),
            models.UniqueConstraint(fields=["event", "startup"], name="slot_startup_unique"),
        ]
        ordering = ["position"]
