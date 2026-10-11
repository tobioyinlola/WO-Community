from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import BaseModel

LEVELS = ("beginner", "intermediate", "advanced")
ACCESS = ("free", "paid")
LESSON_TYPES = ("video", "reading", "resource")


class Course(BaseModel):
    class Status(models.TextChoices):
        DRAFT = "draft"
        PUBLISHED = "published"
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

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(level__in=LEVELS), name="course_level_valid"),
            models.CheckConstraint(condition=Q(access__in=ACCESS), name="course_access_valid"),
            models.CheckConstraint(
                condition=Q(status__in=["draft", "published", "removed"]),
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
    # Resource lessons: a link to a downloadable file or page.
    resource_url = models.CharField(max_length=300, blank=True)
    resource_name = models.CharField(max_length=160, blank=True)

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
    # Where the member left off, so the course can be resumed.
    last_lesson = models.ForeignKey(
        Lesson, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

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

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["course", "user"], name="rating_unique"),
            models.CheckConstraint(condition=Q(stars__gte=1, stars__lte=5), name="rating_range"),
        ]


class Certificate(BaseModel):
    enrolment = models.OneToOneField(
        Enrolment, on_delete=models.CASCADE, related_name="certificate"
    )
    code = models.CharField(max_length=16, unique=True)
    # Kept as written on the day, so a later name change never alters an issued certificate.
    holder_name = models.CharField(max_length=160)
    course_title = models.CharField(max_length=160)
    issued_at = models.DateTimeField()
