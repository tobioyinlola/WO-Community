from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import BaseModel

LEVELS = ("beginner", "intermediate", "advanced", "all")
ACCESS = ("free", "paid")
CERTIFICATE_STATUSES = ("valid", "revoked")
LESSON_TYPES = ("video", "reading", "resource")


class Course(BaseModel):
    class Status(models.TextChoices):
        DRAFT = "draft"
        PUBLISHED = "published"
        # Reachable by its link and open for enrolment, but not listed in the catalogue.
        UNLISTED = "unlisted"
        REMOVED = "removed"

    slug = models.SlugField(max_length=90, unique=True)
    title = models.CharField(max_length=160)
    description = models.TextField()  # sanitised HTML
    description_text = models.TextField()
    instructor = models.CharField(max_length=120)
    category = models.CharField(max_length=60)
    level = models.CharField(max_length=12)
    cover_key = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    access = models.CharField(max_length=4, default="free")
    # Money is whole minor units (kobo, cents) with an ISO currency code.
    price_minor = models.PositiveIntegerField(null=True, blank=True)
    currency = models.CharField(max_length=3, blank=True)
    open_to_visitors = models.BooleanField(default=False)
    certificate_enabled = models.BooleanField(default=True)
    published_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    edited_at = models.DateTimeField(null=True, blank=True)
    rating_count = models.PositiveIntegerField(default=0)
    rating_total = models.PositiveIntegerField(default=0)
    subtitle = models.CharField(max_length=180, blank=True)
    language = models.CharField(max_length=8, default="en")
    # Short lists shown on the landing page. Each entry is a plain sentence.
    learn_bullets = models.JSONField(default=list, blank=True)
    requirements = models.JSONField(default=list, blank=True)
    audience = models.TextField(blank=True)
    promo_video_id = models.CharField(max_length=20, blank=True)
    # Off while a course is being reworked: nobody new can enrol, and those enrolled keep going.
    enrolment_active = models.BooleanField(default=True)
    # Kept up to date by the services, so the catalogue never has to count.
    learners_count = models.PositiveIntegerField(default=0)
    total_duration_seconds = models.PositiveIntegerField(default=0)
    promo_price_minor = models.PositiveIntegerField(null=True, blank=True)
    promo_starts_at = models.DateTimeField(null=True, blank=True)
    promo_ends_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(level__in=LEVELS), name="course_level_valid"),
            models.CheckConstraint(condition=Q(access__in=ACCESS), name="course_access_valid"),
            models.CheckConstraint(
                condition=Q(status__in=["draft", "published", "unlisted", "removed"]),
                name="course_status_valid",
            ),
            models.CheckConstraint(
                condition=Q(access="free") | Q(price_minor__isnull=False, currency__gt=""),
                name="paid_course_has_price",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "access"], name="course_status_access_idx"),
            models.Index(fields=["-published_at", "-id"], name="course_published_idx"),
        ]


class Module(BaseModel):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="modules")
    title = models.CharField(max_length=160)
    position = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ["position"]
        constraints = [
            models.UniqueConstraint(
                fields=["course", "position"],
                name="module_position_unique",
                deferrable=models.Deferrable.DEFERRED,
            )
        ]


class Lesson(BaseModel):
    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name="lessons")
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="lessons")
    type = models.CharField(max_length=8)
    title = models.CharField(max_length=160)
    position = models.PositiveSmallIntegerField()
    duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    # Video lessons: only YouTube, and only the validated id and address are kept.
    video_provider = models.CharField(max_length=10, blank=True)
    video_id = models.CharField(max_length=20, blank=True)
    video_url = models.CharField(max_length=300, blank=True)
    # Reading lessons: sanitised rich text.
    body = models.TextField(blank=True)
    # Resource lessons: a link to a page or file elsewhere, or a document we store. The display
    # name is shared; ``file_key`` is the object in the private bucket (never a public address).
    resource_url = models.CharField(max_length=300, blank=True)
    resource_name = models.CharField(max_length=160, blank=True)
    # db_default keeps the column safe to add while the previous release is still inserting rows.
    file_key = models.CharField(max_length=200, blank=True, db_default="")
    file_size = models.PositiveIntegerField(null=True, blank=True)
    file_content_type = models.CharField(max_length=100, blank=True, db_default="")
    # A short note shown under the video, and whether anyone may watch it before enrolling.
    description = models.TextField(blank=True, db_default="")
    is_preview = models.BooleanField(default=False, db_default=False)

    class Meta:
        ordering = ["module__position", "position"]
        constraints = [
            models.UniqueConstraint(
                fields=["module", "position"],
                name="lesson_position_unique",
                deferrable=models.Deferrable.DEFERRED,
            ),
            models.CheckConstraint(condition=Q(type__in=LESSON_TYPES), name="lesson_type_valid"),
        ]


class ActiveEnrolments(models.Manager):
    """Enrolments a member still holds; ones they left stay, with progress, out of sight."""

    def get_queryset(self):
        return super().get_queryset().filter(ended_at__isnull=True)


class Enrolment(BaseModel):
    class Source(models.TextChoices):
        FREE = "free"
        PURCHASE = "purchase"  # arrives with payments
        GRANT = "grant"  # given by an admin

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="enrolments")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="enrolments"
    )
    source = models.CharField(max_length=8, choices=Source.choices)
    started_at = models.DateTimeField()
    completed_at = models.DateTimeField(null=True, blank=True)
    # Set when the member leaves the course; the row and its progress stay for if they return.
    ended_at = models.DateTimeField(null=True, blank=True)
    # Where the member left off, so the course can be resumed.
    last_lesson = models.ForeignKey(
        Lesson, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    objects = ActiveEnrolments()
    everything = models.Manager()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["course", "user"], name="enrolment_unique")]
        indexes = [
            models.Index(fields=["user", "-started_at"], name="enrolment_user_idx"),
            models.Index(fields=["course", "completed_at"], name="enrolment_course_idx"),
        ]


class LessonProgress(BaseModel):
    enrolment = models.ForeignKey(Enrolment, on_delete=models.CASCADE, related_name="progress")
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name="progress")
    position_seconds = models.PositiveIntegerField(default=0)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["enrolment", "lesson"], name="progress_unique")
        ]


class CourseRating(BaseModel):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="ratings")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="course_ratings"
    )
    stars = models.PositiveSmallIntegerField()
    feedback = models.CharField(max_length=1000, blank=True)
    # Set by an admin who takes a review down; hidden reviews stay out of the average.
    hidden_at = models.DateTimeField(null=True, blank=True)
    hidden_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["course", "user"], name="rating_unique"),
            models.CheckConstraint(condition=Q(stars__gte=1, stars__lte=5), name="rating_range"),
        ]


class Certificate(BaseModel):
    enrolment = models.OneToOneField(
        Enrolment, on_delete=models.CASCADE, related_name="certificate"
    )
    # The certificate number, `WO-C-2026-000341` for new ones. Older certificates keep the shorter
    # code they were given, and both are looked up the same way.
    code = models.CharField(max_length=16, unique=True)
    # Kept as written on the day, so a later name change never alters an issued certificate.
    holder_name = models.CharField(max_length=160)
    course_title = models.CharField(max_length=160)
    issued_at = models.DateTimeField()
    # Whole hours and tenths of the course at the time, from the lecture durations.
    hours = models.DecimalField(max_digits=5, decimal_places=1, default=0)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_reason = models.CharField(max_length=300, blank=True)
    # The rendered PDF in the private bucket. Empty until the job has run, then made on demand.
    pdf_key = models.CharField(max_length=200, blank=True)
    # The template this certificate was drawn with (title, signatory, signature, version), copied
    # when it was issued so later changes to the settings never alter it. A reissue takes a new one.
    template = models.JSONField(default=dict, blank=True)
    # The holder's choice to list this certificate on their profile. Off until they turn it on.
    show_on_profile = models.BooleanField(default=False)

    @property
    def is_valid(self) -> bool:
        return self.revoked_at is None


class CertificateSettings(BaseModel):
    """What appears on every new certificate. One row; changes apply to new certificates only."""

    title_text = models.CharField(max_length=60, default="Certificate of completion")
    signatory_name = models.CharField(max_length=120, default="Onyeka Akumah")
    signatory_title = models.CharField(max_length=120, default="")
    # The base key of a processed `certificate_signature` image in the media bucket. Optional.
    signature_key = models.CharField(max_length=200, blank=True)
    # Raised whenever the template changes, and stamped on each certificate when it is drawn.
    version = models.PositiveIntegerField(default=1)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )


class EnrolmentRequest(BaseModel):
    """A member asking for a paid course while payments are off; an admin decides."""

    class Status(models.TextChoices):
        PENDING = "pending"
        APPROVED = "approved"
        REJECTED = "rejected"

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="requests")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="course_requests"
    )
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.PENDING)
    message = models.CharField(max_length=500, blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            # One open request per member and course; a decided one can be followed by another.
            models.UniqueConstraint(
                fields=["course", "user"],
                condition=Q(status="pending"),
                name="request_one_pending",
            ),
            models.CheckConstraint(
                condition=Q(status__in=["pending", "approved", "rejected"]),
                name="request_status_valid",
            ),
        ]
        indexes = [
            models.Index(fields=["course", "status", "-created_at"], name="request_queue_idx")
        ]


class WishlistItem(BaseModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="course_wishlist"
    )
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="wishlisted")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "course"], name="wishlist_unique")]


class LectureQuestion(BaseModel):
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name="questions")
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="questions")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="lecture_questions"
    )
    body = models.CharField(max_length=2000)
    hidden_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["lesson", "-created_at"], name="question_lesson_idx")]


class LectureAnswer(BaseModel):
    question = models.ForeignKey(LectureQuestion, on_delete=models.CASCADE, related_name="answers")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="lecture_answers"
    )
    body = models.CharField(max_length=2000)
    # Shown with a badge: the answer came from the course's staff.
    is_staff = models.BooleanField(default=False)
    hidden_at = models.DateTimeField(null=True, blank=True)


class LectureNote(BaseModel):
    """A private note a learner keeps against a moment in a lecture."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="lecture_notes"
    )
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name="notes")
    seconds = models.PositiveIntegerField(default=0)
    body = models.CharField(max_length=2000)

    class Meta:
        indexes = [models.Index(fields=["user", "lesson", "seconds"], name="note_lesson_idx")]


class CourseAnnouncement(BaseModel):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="announcements")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    title = models.CharField(max_length=160)
    body = models.TextField()  # sanitised HTML

    class Meta:
        ordering = ["-created_at"]
