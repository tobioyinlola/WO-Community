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
    # Which video provider the mentor prefers; blank means the platform default.
    meeting_provider = models.CharField(max_length=12, blank=True, db_default="")
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


class MentorSettings(BaseModel):
    """How a mentor wants to be booked. Created the first time it is read or saved.

    The weekly windows are `AvailabilitySlot` rows, the time zone, weekly limit, pause switch and
    video provider stay on `MentorProfile`; this holds the rest of what the Settings page edits.
    """

    class Pricing(models.TextChoices):
        FREE = "free"
        PAID = "paid"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="mentor_settings"
    )
    session_lengths = models.JSONField(default=list)  # minutes offered: some of 30, 45, 60
    buffer_minutes = models.PositiveSmallIntegerField(default=0)
    min_notice_hours = models.PositiveSmallIntegerField(default=12)
    booking_window_days = models.PositiveSmallIntegerField(default=30)
    pricing_mode = models.CharField(max_length=4, choices=Pricing.choices, default=Pricing.FREE)
    default_price_minor = models.PositiveIntegerField(null=True, blank=True)
    currency = models.CharField(max_length=3, blank=True)
    personal_link = models.CharField(max_length=500, blank=True)
    topics = models.JSONField(default=list)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(buffer_minutes__in=[0, 10, 15, 30]), name="mentorsettings_buffer_valid"
            ),
            models.CheckConstraint(
                condition=Q(pricing_mode__in=["free", "paid"]), name="mentorsettings_pricing_valid"
            ),
        ]


class MentorSessionPrice(BaseModel):
    """A price for one session length, when it differs from the mentor's default."""

    mentor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="session_prices"
    )
    length_minutes = models.PositiveSmallIntegerField()
    price_minor = models.PositiveIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["mentor", "length_minutes"], name="mentorsessionprice_unique"
            ),
        ]


class AvailabilityException(BaseModel):
    """Whole days a mentor is not available. Extra time on one date is a one off slot."""

    mentor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="availability_blocks"
    )
    starts_on = models.DateField()  # in the mentor time zone, inclusive
    ends_on = models.DateField()
    note = models.CharField(max_length=120, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(ends_on__gte=models.F("starts_on")), name="availabilityblock_span_valid"
            ),
        ]
        indexes = [models.Index(fields=["mentor", "ends_on"], name="availabilityblock_idx")]


PRICING_MODES = ("free", "paid")
SESSION_LENGTHS = (30, 45, 60)
EXCEPTION_KINDS = ("blocked", "extra")

SESSION_STATUSES = (
    "requested",
    "confirmed",
    "declined",
    "cancelled",
    "expired",
    "completed",
    "no_show",
)
# A request holds its time while it waits, so the same slot cannot be asked for twice.
ACTIVE_SESSION_STATUSES = ("requested", "confirmed")


class MentorSession(BaseModel):
    """One mentoring session, from the founder's request to the held (or missed) meeting.

    A single row carries the whole life of the booking, so the database can refuse overlapping
    sessions for a mentor, and for a founder, while it is requested or confirmed.
    """

    class Status(models.TextChoices):
        REQUESTED = "requested"
        CONFIRMED = "confirmed"
        DECLINED = "declined"
        CANCELLED = "cancelled"
        EXPIRED = "expired"
        COMPLETED = "completed"
        NO_SHOW = "no_show"  # the founder did not come

    class MeetingState(models.TextChoices):
        NONE = ""  # no meeting wanted yet (a request, or a closed session)
        PENDING = "pending"
        READY = "ready"
        FAILED = "failed"

    mentor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="mentor_sessions"
    )
    mentee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="mentee_sessions"
    )
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    time_span = DateTimeRangeField()
    topic = models.CharField(max_length=120)
    message = models.CharField(max_length=1000)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.REQUESTED)

    responded_at = models.DateTimeField(null=True, blank=True)  # accepted or declined
    confirmed_at = models.DateTimeField(null=True, blank=True)
    closed_reason = models.CharField(max_length=1000, blank=True)  # decline or cancel reason
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)
    late_cancel = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)

    # What was agreed about length and price when it was requested. `payment_mode` is "arranged"
    # while online payment is off: the price is shown and the two settle it between them.
    length_minutes = models.PositiveSmallIntegerField(default=0)
    price_minor = models.PositiveIntegerField(null=True, blank=True)
    currency = models.CharField(max_length=3, blank=True)
    payment_mode = models.CharField(max_length=8, blank=True)

    meeting_provider = models.CharField(max_length=12, blank=True)
    meeting_state = models.CharField(max_length=8, choices=MeetingState.choices, blank=True)
    meeting_external_id = models.CharField(max_length=120, blank=True)
    meeting_url = models.CharField(max_length=500, blank=True)

    # A proposed new time waits for the other person; the session keeps its time until then.
    proposed_starts_at = models.DateTimeField(null=True, blank=True)
    proposed_ends_at = models.DateTimeField(null=True, blank=True)
    proposed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    proposed_note = models.CharField(max_length=500, blank=True)
    reschedule_count = models.PositiveSmallIntegerField(default=0)

    reminded_24h_at = models.DateTimeField(null=True, blank=True)
    reminded_1h_at = models.DateTimeField(null=True, blank=True)
    feedback_requested_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=SESSION_STATUSES), name="mentorsession_status_valid"
            ),
            models.CheckConstraint(
                condition=Q(ends_at__gt=models.F("starts_at")), name="mentorsession_span_valid"
            ),
            models.CheckConstraint(
                condition=~Q(mentor=models.F("mentee")), name="mentorsession_not_self"
            ),
            # The database settles two people asking for the same time at once.
            ExclusionConstraint(
                name="mentorsession_mentor_no_overlap",
                expressions=[
                    ("mentor", RangeOperators.EQUAL),
                    ("time_span", RangeOperators.OVERLAPS),
                ],
                condition=Q(status__in=ACTIVE_SESSION_STATUSES),
            ),
            ExclusionConstraint(
                name="mentorsession_mentee_no_overlap",
                expressions=[
                    ("mentee", RangeOperators.EQUAL),
                    ("time_span", RangeOperators.OVERLAPS),
                ],
                condition=Q(status__in=ACTIVE_SESSION_STATUSES),
            ),
            # One waiting request from a founder to a mentor at a time.
            models.UniqueConstraint(
                fields=["mentee", "mentor"],
                condition=Q(status="requested"),
                name="mentorsession_one_request_per_pair",
            ),
        ]
        indexes = [
            models.Index(fields=["mentor", "status", "starts_at"], name="mentorsession_mentor_idx"),
            models.Index(fields=["mentee", "status", "starts_at"], name="mentorsession_mentee_idx"),
            models.Index(fields=["status", "starts_at"], name="mentorsession_status_idx"),
        ]


class SessionFeedback(BaseModel):
    """What each side says after a session: stars and comments from the founder, the outcome
    from the mentor. Founder comments are for the mentor and admins, never public."""

    class Role(models.TextChoices):
        MENTEE = "mentee"
        MENTOR = "mentor"

    session = models.ForeignKey(MentorSession, on_delete=models.CASCADE, related_name="feedback")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="session_feedback"
    )
    role = models.CharField(max_length=6, choices=Role.choices)
    stars = models.PositiveSmallIntegerField(null=True, blank=True)  # founders only
    comment = models.CharField(max_length=1000, blank=True)
    # Mentor: "held" or "mentee_no_show". Founder: "held" or "mentor_no_show".
    outcome = models.CharField(max_length=16, default="held")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["session", "author"], name="sessionfeedback_unique"),
            models.CheckConstraint(
                condition=Q(stars__isnull=True) | Q(stars__gte=1, stars__lte=5),
                name="sessionfeedback_stars_range",
            ),
        ]


class CalendarConnection(BaseModel):
    """A mentor private calendar feed, so time they are already busy is never offered."""

    class Status(models.TextChoices):
        ACTIVE = "active"
        ERROR = "error"  # the last read failed; the busy time from the last good read is kept

    mentor = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="calendar_connection"
    )
    # The feed address is a secret (anyone holding it can read the calendar), so it is encrypted
    # and never returned; only its host is shown.
    feed_url_encrypted = models.TextField()
    host = models.CharField(max_length=120)
    include_all_day = models.BooleanField(default=False)
    status = models.CharField(max_length=6, choices=Status.choices, default=Status.ACTIVE)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=40, blank=True)
    event_count = models.PositiveIntegerField(default=0)
    busy_hash = models.CharField(max_length=64, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=["active", "error"]), name="calendarconnection_status_valid"
            )
        ]


class CalendarBusy(BaseModel):
    """One range of time the mentor is busy in their calendar. Times only, never titles."""

    mentor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="calendar_busy"
    )
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(ends_at__gt=models.F("starts_at")), name="calendarbusy_span_valid"
            )
        ]
        indexes = [models.Index(fields=["mentor", "starts_at"], name="calendarbusy_mentor_idx")]
