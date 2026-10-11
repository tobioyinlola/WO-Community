"""Read side of the learning hub."""

from typing import Any
from uuid import UUID

from django.conf import settings
from django.db.models import Count, Q, QuerySet
from rest_framework import exceptions

from apps.core.keyset import paginate
from apps.integrations import youtube
from apps.learning import learn
from apps.learning.models import (
    Certificate,
    Course,
    CourseRating,
    Enrolment,
    Lesson,
    LessonProgress,
)
from apps.uploads import services as uploads

EXCERPT = 200


def published() -> QuerySet[Course]:
    return Course.objects.filter(status=Course.Status.PUBLISHED)


def _excerpt(course: Course) -> str:
    text = course.description_text
    return text if len(text) <= EXCERPT else text[: EXCERPT - 1] + "…"


def _rating(course: Course) -> dict[str, Any]:
    average = round(course.rating_total / course.rating_count, 2) if course.rating_count else None
    return {"average": average, "count": course.rating_count}


def _price(course: Course) -> dict[str, Any] | None:
    if course.access == "free":
        return None
    return {"amount_minor": course.price_minor, "currency": course.currency}


def course_summary(course: Course, viewer_id: UUID | None) -> dict[str, Any]:
    view: dict[str, Any] = {
        "id": course.pk,
        "slug": course.slug,
        "title": course.title,
        "excerpt": _excerpt(course),
        "instructor": course.instructor,
        "category": course.category,
        "level": course.level,
        "cover": uploads.image_urls(course.cover_key),
        "access": course.access,
        "price": _price(course),
        "open_to_visitors": course.open_to_visitors,
        "certificate_enabled": course.certificate_enabled,
        "rating": _rating(course),
        "lesson_count": course.lessons.count(),
        "status": course.status,
    }
    view["progress"] = (
        learn.progress_summary(viewer_id, course)
        if viewer_id is not None
        else {"enrolled": False, "percent": 0}
    )
    return view


def catalogue(
    viewer_id: UUID,
    *,
    q: str,
    category: str,
    level: str,
    access: str,
    enrolled: bool,
    cursor: str,
    limit: int,
) -> dict[str, Any]:
    queryset = published()
    if q:
        queryset = queryset.filter(Q(title__icontains=q) | Q(description_text__icontains=q))
    if category:
        queryset = queryset.filter(category__iexact=category)
    if level:
        queryset = queryset.filter(level=level)
    if access:
        queryset = queryset.filter(access=access)
    if enrolled:
        queryset = queryset.filter(enrolments__user_id=viewer_id)
    rows, next_cursor = paginate(
        queryset, fields=("published_at", "id"), sort="courses", cursor=cursor, limit=limit
    )
    return {"results": [course_summary(c, viewer_id) for c in rows], "next_cursor": next_cursor}


def categories() -> list[str]:
    return sorted(published().values_list("category", flat=True).distinct())


def _visible_course(viewer_id: UUID | None, course_id: UUID) -> Course:
    course = Course.objects.filter(pk=course_id).exclude(status=Course.Status.REMOVED).first()
    if course is None:
        raise exceptions.NotFound()
    if course.status != Course.Status.PUBLISHED:
        # Unpublished courses stay open to people already enrolled, and to no one else.
        if viewer_id is None or learn.enrolment_of(viewer_id, course.pk) is None:
            raise exceptions.NotFound()
    return course


def outline(course: Course, viewer_id: UUID | None) -> list[dict[str, Any]]:
    """Modules and lessons, with what is locked and what the member has finished."""
    open_ = learn.can_open_lessons(course, viewer_id)
    finished: set[UUID] = set()
    enrolment = learn.enrolment_of(viewer_id, course.pk) if viewer_id is not None else None
    if enrolment is not None:
        finished = set(
            LessonProgress.objects.filter(
                enrolment=enrolment, completed_at__isnull=False
            ).values_list("lesson_id", flat=True)
        )
    modules = []
    for module in course.modules.prefetch_related("lessons"):
        modules.append(
            {
                "id": module.pk,
                "title": module.title,
                "position": module.position,
                "lessons": [
                    {
                        "id": lesson.pk,
                        "type": lesson.type,
                        "title": lesson.title,
                        "position": lesson.position,
                        "duration_seconds": lesson.duration_seconds,
                        "locked": not open_,
                        "completed": lesson.pk in finished,
                    }
                    for lesson in module.lessons.all()
                ],
            }
        )
    return modules


def course_detail(viewer_id: UUID | None, course_id: UUID) -> dict[str, Any]:
    course = _visible_course(viewer_id, course_id)
    view = course_summary(course, viewer_id)
    view["description"] = course.description
    view["modules"] = outline(course, viewer_id)
    view["resume"] = learn.resume_point(viewer_id, course) if viewer_id is not None else None
    mine = (
        CourseRating.objects.filter(course=course, user_id=viewer_id).first()
        if viewer_id is not None
        else None
    )
    view["my_rating"] = {"stars": mine.stars, "feedback": mine.feedback} if mine else None
    return view


def my_courses(viewer_id: UUID, *, cursor: str, limit: int) -> dict[str, Any]:
    rows, next_cursor = paginate(
        Enrolment.objects.filter(user_id=viewer_id)
        .exclude(course__status=Course.Status.REMOVED)
        .select_related("course"),
        fields=("started_at", "id"),
        sort="my-courses",
        cursor=cursor,
        limit=limit,
    )
    return {
        "results": [course_summary(e.course, viewer_id) for e in rows],
        "next_cursor": next_cursor,
    }


def lesson_detail(viewer_id: UUID | None, lesson_id: UUID) -> dict[str, Any]:
    lesson = Lesson.objects.select_related("course", "module").filter(pk=lesson_id).first()
    if lesson is None or lesson.course.status == Course.Status.REMOVED:
        raise exceptions.NotFound()
    course = lesson.course
    if not learn.can_open_lessons(course, viewer_id):
        if course.status != Course.Status.PUBLISHED and viewer_id is None:
            raise exceptions.NotFound()
        if viewer_id is None:
            raise exceptions.NotAuthenticated()
        raise learn.EntitlementRequired(
            "Buy this course to open its lessons."
            if course.access == "paid"
            else "Enrol in this course to open its lessons."
        )
    order = list(
        course.lessons.order_by("module__position", "position").values_list("pk", flat=True)
    )
    index = order.index(lesson.pk)
    view: dict[str, Any] = {
        "id": lesson.pk,
        "course": {"id": course.pk, "slug": course.slug, "title": course.title},
        "module": {"id": lesson.module_id, "title": lesson.module.title},
        "type": lesson.type,
        "title": lesson.title,
        "duration_seconds": lesson.duration_seconds,
        "video": None,
        "body": "",
        "resource": None,
        "previous_lesson_id": order[index - 1] if index > 0 else None,
        "next_lesson_id": order[index + 1] if index + 1 < len(order) else None,
        "progress": None,
    }
    if lesson.type == "video":
        view["video"] = {
            "provider": lesson.video_provider,
            "video_id": lesson.video_id,
            "url": lesson.video_url,
            "embed_url": youtube.embed_url(lesson.video_id),
        }
    elif lesson.type == "reading":
        view["body"] = lesson.body
    else:
        view["resource"] = {"url": lesson.resource_url, "name": lesson.resource_name}
    enrolment = learn.enrolment_of(viewer_id, course.pk) if viewer_id is not None else None
    if enrolment is not None:
        row = LessonProgress.objects.filter(enrolment=enrolment, lesson=lesson).first()
        view["progress"] = {
            "position_seconds": row.position_seconds if row else 0,
            "completed": bool(row and row.completed_at),
        }
    return view


# --- certificates ---


def certificate_view(certificate: Certificate, *, public: bool = False) -> dict[str, Any]:
    view: dict[str, Any] = {
        "code": certificate.code,
        "holder_name": certificate.holder_name,
        "course_title": certificate.course_title,
        "issued_at": certificate.issued_at,
        "verify_url": f"{settings.FRONTEND_BASE_URL}/verify/{certificate.code}",
    }
    if not public:
        view["id"] = certificate.pk
    return view


def my_certificates(viewer_id: UUID) -> list[dict[str, Any]]:
    rows = Certificate.objects.filter(enrolment__user_id=viewer_id).order_by("-issued_at")
    return [certificate_view(c) for c in rows]


def get_certificate(viewer_id: UUID, certificate_id: UUID) -> Certificate:
    certificate = Certificate.objects.filter(
        pk=certificate_id, enrolment__user_id=viewer_id
    ).first()
    if certificate is None:
        raise exceptions.NotFound()  # someone else's certificate is not even confirmed to exist
    return certificate


def verify(code: str) -> dict[str, Any]:
    certificate = Certificate.objects.filter(code=code.upper().strip()).first()
    if certificate is None:
        raise exceptions.NotFound()
    return {"valid": True, **certificate_view(certificate, public=True)}


# --- public catalogue ---


def public_courses(*, cursor: str, limit: int) -> dict[str, Any]:
    queryset = published().filter(access="free", open_to_visitors=True)
    rows, next_cursor = paginate(
        queryset, fields=("published_at", "id"), sort="public-courses", cursor=cursor, limit=limit
    )
    keep = ("slug", "title", "excerpt", "instructor", "category", "level", "cover", "lesson_count")
    return {
        "results": [{k: course_summary(c, None)[k] for k in keep} for c in rows],
        "next_cursor": next_cursor,
    }


def public_course(slug: str) -> dict[str, Any]:
    course = published().filter(access="free", open_to_visitors=True, slug=slug).first()
    if course is None:
        raise exceptions.NotFound()
    view = course_summary(course, None)
    modules = outline(course, None)
    for module in modules:
        for lesson in module["lessons"]:
            lesson["locked"] = False
            del lesson["completed"]
    return {
        **{
            k: view[k]
            for k in ("slug", "title", "instructor", "category", "level", "cover", "rating")
        },
        "description": course.description,
        "modules": modules,
    }


# --- admin ---


def admin_queryset(*, status: str, access: str, q: str) -> QuerySet[Course]:
    queryset = Course.objects.exclude(status=Course.Status.REMOVED)
    if status:
        queryset = queryset.filter(status=status)
    if access:
        queryset = queryset.filter(access=access)
    if q:
        queryset = queryset.filter(title__icontains=q)
    return queryset.order_by("-created_at", "-id")


def admin_course(course: Course) -> dict[str, Any]:
    modules = []
    for module in course.modules.prefetch_related("lessons"):
        modules.append(
            {
                "id": module.pk,
                "title": module.title,
                "position": module.position,
                "lessons": [
                    {
                        "id": lesson.pk,
                        "type": lesson.type,
                        "title": lesson.title,
                        "position": lesson.position,
                        "duration_seconds": lesson.duration_seconds,
                        "video_url": lesson.video_url,
                        "video_id": lesson.video_id,
                        "body": lesson.body,
                        "resource_url": lesson.resource_url,
                        "resource_name": lesson.resource_name,
                    }
                    for lesson in module.lessons.all()
                ],
            }
        )
    return {
        **course_summary(course, None),
        "description": course.description,
        "price_minor": course.price_minor,
        "currency": course.currency,
        "published_at": course.published_at,
        "created_at": course.created_at,
        "edited_at": course.edited_at,
        "modules": modules,
    }


def stats(course: Course) -> dict[str, Any]:
    enrolled = course.enrolments.count()
    completed = course.enrolments.filter(completed_at__isnull=False).count()
    per_lesson = {
        row["lesson_id"]: row["n"]
        for row in LessonProgress.objects.filter(lesson__course=course, completed_at__isnull=False)
        .values("lesson_id")
        .annotate(n=Count("id"))
    }
    return {
        "enrolled": enrolled,
        "completed": completed,
        "completion_rate": round(completed / enrolled, 4) if enrolled else None,
        "rating": _rating(course),
        "lessons": [
            {"id": lesson.pk, "title": lesson.title, "completed_by": per_lesson.get(lesson.pk, 0)}
            for lesson in course.lessons.order_by("module__position", "position")
        ],
    }


def enrolment_rows(course: Course) -> QuerySet[Enrolment]:
    return course.enrolments.order_by("-started_at", "-id")


def enrolment_views(rows: list[Enrolment], course: Course) -> list[dict[str, Any]]:
    total = course.lessons.count()
    done = {
        r["enrolment_id"]: r["n"]
        for r in LessonProgress.objects.filter(
            enrolment__in=rows, completed_at__isnull=False, lesson__course=course
        )
        .values("enrolment_id")
        .annotate(n=Count("id"))
    }
    return [
        {
            "user_id": e.user_id,
            "origin": e.source,
            "started_at": e.started_at,
            "completed_at": e.completed_at,
            "percent": int(done.get(e.pk, 0) * 100 / total) if total else 0,
        }
        for e in rows
    ]


def rating_rows(course: Course) -> list[dict[str, Any]]:
    return [
        {"user_id": r.user_id, "stars": r.stars, "feedback": r.feedback, "created_at": r.created_at}
        for r in course.ratings.order_by("-created_at")
    ]


# --- for segments and dashboards ---


def learner_ids(access: str) -> set[UUID]:
    """Members enrolled in at least one course of the given access (free or paid)."""
    return set(
        Enrolment.objects.filter(course__access=access)
        .exclude(course__status=Course.Status.REMOVED)
        .values_list("user_id", flat=True)
    )


def completer_ids() -> set[UUID]:
    """Members who have completed any course."""
    return set(
        Enrolment.objects.filter(completed_at__isnull=False).values_list("user_id", flat=True)
    )


def snapshot() -> dict[str, int]:
    live = Enrolment.objects.exclude(course__status=Course.Status.REMOVED)
    return {
        "published_courses": published().count(),
        "enrolments": live.count(),
        "completed": live.filter(completed_at__isnull=False).count(),
        "certificates": Certificate.objects.count(),
    }
