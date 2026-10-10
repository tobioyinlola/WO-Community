"""The member's side of the learning hub: enrolling, progress, ratings and certificates."""

import secrets
from typing import Any
from uuid import UUID

import structlog
from django.db import IntegrityError, transaction
from django.db.models import Count, Sum
from django.utils import timezone
from rest_framework import exceptions

from apps.analytics import services as analytics
from apps.audit import services as audit
from apps.core import events as domain_events
from apps.core.text import plain
from apps.learning import events
from apps.learning.models import (
    Certificate,
    Course,
    CourseRating,
    Enrolment,
    Lesson,
    LessonProgress,
)
from apps.notifications import notify
from apps.profiles import selectors as profiles

logger = structlog.get_logger(__name__)

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O, 1/I/L
MAX_POSITION_SECONDS = 24 * 3600


class NotFound(exceptions.NotFound):
    default_detail = "Not found."


class Conflict(exceptions.APIException):
    status_code = 409
    default_code = "conflict"


class PaymentRequired(exceptions.APIException):
    status_code = 402
    default_code = "payment_required"
    default_detail = "This is a paid course. Purchasing is not available yet."


class EntitlementRequired(exceptions.PermissionDenied):
    default_code = "entitlement_required"
    default_detail = "Enrol in this course to open its lessons."


def _invalid(field: str, message: str) -> exceptions.ValidationError:
    return exceptions.ValidationError({field: [message]})


# --- access ---


def enrolment_of(user_id: UUID, course_id: UUID) -> Enrolment | None:
    return Enrolment.objects.filter(user_id=user_id, course_id=course_id).first()


def can_open_lessons(course: Course, viewer_id: UUID | None) -> bool:
    """Whether the viewer may see lesson content: enrolled, or a free course open to visitors."""
    if viewer_id is not None and enrolment_of(viewer_id, course.pk) is not None:
        return course.status != Course.Status.REMOVED
    return (
        course.status == Course.Status.PUBLISHED
        and course.access == "free"
        and course.open_to_visitors
    )


# --- enrolling ---


def enrol(*, user_id: UUID, course_id: UUID) -> tuple[Enrolment, bool]:
    """Enrol in a free, published course. Returns the enrolment and whether it is new."""
    course = Course.objects.filter(pk=course_id, status=Course.Status.PUBLISHED).first()
    if course is None:
        raise NotFound()
    if course.access == "paid":
        existing = enrolment_of(user_id, course_id)
        if existing is not None:
            return existing, False
        raise PaymentRequired()
    try:
        with transaction.atomic():
            enrolment, created = Enrolment.objects.get_or_create(
                course=course,
                user_id=user_id,
                defaults={"source": Enrolment.Source.FREE, "started_at": timezone.now()},
            )
            if created:
                analytics.track(
                    "course_enrolled",
                    actor_id=user_id,
                    properties={"course_id": course.slug, "access": course.access},
                )
    except IntegrityError:  # two taps at once
        return Enrolment.objects.get(course=course, user_id=user_id), False
    return enrolment, created


def grant(*, actor: Any, course_id: UUID, user_id: UUID, ip: str = "") -> tuple[Enrolment, bool]:
    """Give a member access without payment (the way into a paid course until purchases exist)."""
    course = Course.objects.filter(pk=course_id).exclude(status=Course.Status.REMOVED).first()
    if course is None:
        raise NotFound()
    from apps.accounts import services as accounts

    if not accounts.is_active(user_id):
        raise _invalid("user_id", "Only active members can be given a course.")
    with transaction.atomic():
        enrolment, created = Enrolment.objects.get_or_create(
            course=course,
            user_id=user_id,
            defaults={"source": Enrolment.Source.GRANT, "started_at": timezone.now()},
        )
        if created:
            analytics.track(
                "course_enrolled",
                actor_id=user_id,
                properties={"course_id": course.slug, "access": course.access},
            )
            domain_events.publish(
                events.CourseGranted(course_id=str(course.pk), user_id=str(user_id))
            )
            audit.record(
                actor=actor,
                action="courses.granted",
                target_type="course",
                target_id=course.pk,
                after={"user_id": str(user_id)},
                ip=ip,
            )
    return enrolment, created


# --- progress ---


def update_progress(
    *, user_id: UUID, lesson_id: UUID, position_seconds: int | None, completed: bool | None
) -> LessonProgress:
    """Save where the member is in a lesson and whether they finished it.

    The front end calls this every 15 seconds and on pause. Finishing the last lesson completes
    the course (once) and queues the certificate.
    """
    lesson = Lesson.objects.select_related("course").filter(pk=lesson_id).first()
    if lesson is None or lesson.course.status == Course.Status.REMOVED:
        raise NotFound()
    if position_seconds is not None and not 0 <= position_seconds <= MAX_POSITION_SECONDS:
        raise _invalid("position_seconds", "That position is out of range.")
    with transaction.atomic():
        enrolment = (
            Enrolment.objects.select_for_update()
            .filter(user_id=user_id, course_id=lesson.course_id)
            .first()
        )
        if enrolment is None:
            raise EntitlementRequired()
        progress, created = LessonProgress.objects.get_or_create(enrolment=enrolment, lesson=lesson)
        slug = lesson.course.slug
        if created:
            analytics.track("lesson_started", actor_id=user_id, properties={"course_id": slug})
        if position_seconds is not None:
            progress.position_seconds = position_seconds
        if completed is True and progress.completed_at is None:
            progress.completed_at = timezone.now()
            analytics.track("lesson_completed", actor_id=user_id, properties={"course_id": slug})
        elif completed is False:
            progress.completed_at = None
        progress.save()
        enrolment.last_lesson = lesson
        enrolment.save(update_fields=["last_lesson", "updated_at"])
        if completed is True:
            _complete_if_finished(enrolment, lesson.course)
    return progress


def _complete_if_finished(enrolment: Enrolment, course: Course) -> None:
    if enrolment.completed_at is not None:
        return
    total = course.lessons.count()
    done = LessonProgress.objects.filter(
        enrolment=enrolment, completed_at__isnull=False, lesson__course=course
    ).count()
    if total and done >= total:
        enrolment.completed_at = timezone.now()
        enrolment.save(update_fields=["completed_at", "updated_at"])
        analytics.track(
            "course_completed", actor_id=enrolment.user_id, properties={"course_id": course.slug}
        )
        domain_events.publish(events.CourseCompleted(enrolment_id=str(enrolment.pk)))


# --- ratings ---


def rate(*, user_id: UUID, course_id: UUID, stars: int, feedback: str) -> CourseRating:
    course = Course.objects.filter(pk=course_id).exclude(status=Course.Status.REMOVED).first()
    if course is None:
        raise NotFound()
    with transaction.atomic():
        locked = Course.objects.select_for_update().get(pk=course.pk)
        if enrolment_of(user_id, course.pk) is None:
            raise EntitlementRequired("Enrol in a course before rating it.")
        rating, _ = CourseRating.objects.update_or_create(
            course=locked, user_id=user_id, defaults={"stars": stars, "feedback": plain(feedback)}
        )
        totals = locked.ratings.aggregate(n=Count("id"), total=Sum("stars"))
        locked.rating_count = totals["n"]
        locked.rating_total = totals["total"] or 0
        locked.save(update_fields=["rating_count", "rating_total", "updated_at"])
    return rating


# --- certificates ---


def _new_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(12))


def issue_certificate(enrolment_id: UUID) -> Certificate | None:
    """Create the certificate for a completed course. Safe to run twice."""
    enrolment = (
        Enrolment.objects.select_related("course")
        .filter(pk=enrolment_id, completed_at__isnull=False)
        .first()
    )
    if enrolment is None or not enrolment.course.certificate_enabled:
        return None
    existing = Certificate.objects.filter(enrolment=enrolment).first()
    if existing is not None:
        return existing
    holder = profiles.full_name_of(enrolment.user_id) or "WO Community member"
    for _ in range(5):  # a clash on the random code is astronomically unlikely, but handled
        try:
            with transaction.atomic():
                certificate = Certificate.objects.create(
                    enrolment=enrolment,
                    code=_new_code(),
                    holder_name=plain(holder)[:160],
                    course_title=enrolment.course.title,
                    issued_at=timezone.now(),
                )
            break
        except IntegrityError:
            existing = Certificate.objects.filter(enrolment=enrolment).first()
            if existing is not None:
                return existing
    else:
        raise RuntimeError("could not allocate a certificate code")
    notify.notify(
        enrolment.user_id,
        "certificate_ready",
        {"certificate_id": str(certificate.pk), "title": certificate.course_title},
        dedupe_key=f"certificate:{certificate.pk}",
    )
    return certificate


def progress_summary(user_id: UUID, course: Course) -> dict[str, Any]:
    """Percent complete and where to resume for one member in one course."""
    enrolment = enrolment_of(user_id, course.pk)
    total = course.lessons.count()
    if enrolment is None:
        return {"enrolled": False, "percent": 0, "completed_lessons": 0, "total_lessons": total}
    done = LessonProgress.objects.filter(
        enrolment=enrolment, completed_at__isnull=False, lesson__course=course
    ).count()
    return {
        "enrolled": True,
        "percent": int(done * 100 / total) if total else 0,
        "completed_lessons": done,
        "total_lessons": total,
        "completed_at": enrolment.completed_at,
        "origin": enrolment.source,
    }


def resume_point(user_id: UUID, course: Course) -> dict[str, Any] | None:
    """The lesson to continue with: the last one touched if unfinished, else the next unfinished."""
    enrolment = enrolment_of(user_id, course.pk)
    if enrolment is None:
        return None
    finished = set(
        LessonProgress.objects.filter(enrolment=enrolment, completed_at__isnull=False).values_list(
            "lesson_id", flat=True
        )
    )
    last = enrolment.last_lesson_id
    if last is not None and last not in finished:
        progress = LessonProgress.objects.filter(enrolment=enrolment, lesson_id=last).first()
        return {"lesson_id": last, "position_seconds": progress.position_seconds if progress else 0}
    for lesson_id in course.lessons.order_by("module__position", "position").values_list(
        "pk", flat=True
    ):
        if lesson_id not in finished:
            return {"lesson_id": lesson_id, "position_seconds": 0}
    return None
