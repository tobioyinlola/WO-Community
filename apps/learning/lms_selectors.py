"""Read side for the parts of a course beyond its outline: the landing page, reviews, questions,
notes, announcements and the learner's own shelves."""

from typing import Any
from uuid import UUID

from django.db.models import Count, QuerySet
from rest_framework import exceptions

from apps.core.keyset import paginate
from apps.integrations import youtube
from apps.learning import engage, learn, lms, selectors
from apps.learning.models import (
    Course,
    CourseAnnouncement,
    CourseRating,
    Enrolment,
    LectureNote,
    LectureQuestion,
    WishlistItem,
)
from apps.profiles import selectors as profiles


def _lookup(ref: str) -> Course:
    """A course by its id or its slug. Removed ones do not exist."""
    try:
        course = Course.objects.filter(pk=UUID(ref)).first()
    except ValueError:
        course = Course.objects.filter(slug=ref).first()
    if course is None or course.status == Course.Status.REMOVED:
        raise exceptions.NotFound()
    return course


def distribution(course: Course) -> dict[str, int]:
    """How many showing reviews gave each number of stars."""
    counts = dict(
        course.ratings.filter(hidden_at__isnull=True)
        .values_list("stars")
        .annotate(n=Count("id"))
        .values_list("stars", "n")
    )
    return {str(stars): counts.get(stars, 0) for stars in (5, 4, 3, 2, 1)}


def can_review(viewer_id: UUID | None, course: Course) -> bool:
    if viewer_id is None or learn.enrolment_of(viewer_id, course.pk) is None:
        return False
    return learn.progress_summary(viewer_id, course)["percent"] >= lms.RATING_MIN_PERCENT


def related(course: Course, viewer_id: UUID | None, limit: int = 4) -> list[dict[str, Any]]:
    rows = (
        selectors.published()
        .filter(category__iexact=course.category)
        .exclude(pk=course.pk)
        .order_by("-learners_count", "-published_at")[:limit]
    )
    return [selectors.course_summary(c, viewer_id) for c in rows]


def course_page(viewer_id: UUID | None, ref: str) -> dict[str, Any]:
    """Everything the landing page shows, for the id or the slug."""
    course = _lookup(ref)
    view = selectors.course_detail(viewer_id, course.pk)
    view.update(
        {
            "learn_bullets": course.learn_bullets,
            "requirements": course.requirements,
            "audience": course.audience,
            "promo_video": (
                {
                    "video_id": course.promo_video_id,
                    "embed_url": youtube.embed_url(course.promo_video_id),
                }
                if course.promo_video_id
                else None
            ),
            "rating_distribution": distribution(course),
            "can_review": can_review(viewer_id, course),
            "related": related(course, viewer_id),
            "announcement_count": course.announcements.count(),
            "last_updated": course.edited_at or course.published_at or course.updated_at,
            "section_count": course.modules.count(),
        }
    )
    return view


def reviews(viewer_id: UUID, course_id: UUID, *, cursor: str, limit: int) -> dict[str, Any]:
    course = selectors._visible_course(viewer_id, course_id)
    rows, next_cursor = paginate(
        course.ratings.filter(hidden_at__isnull=True),
        fields=("created_at", "id"),
        sort="reviews",
        cursor=cursor,
        limit=limit,
    )
    cards = profiles.cards_for(_Viewer(viewer_id), [r.user_id for r in rows])
    return {
        "results": [
            {
                "id": r.pk,
                "stars": r.stars,
                "feedback": r.feedback,
                "created_at": r.created_at,
                "reviewer": cards[r.user_id]["name"],
                "mine": r.user_id == viewer_id,
            }
            for r in rows
        ],
        "next_cursor": next_cursor,
        "average": selectors._rating(course)["average"],
        "count": course.rating_count,
        "distribution": distribution(course),
    }


class _Viewer:
    """Enough of a user for the profile visibility rules."""

    is_authenticated = True
    status = "active"

    def __init__(self, user_id: UUID) -> None:
        self.pk = user_id


# --- the learner's shelves ---


def shelf(viewer_id: UUID, *, state: str, cursor: str, limit: int) -> dict[str, Any]:
    """`all` and `in_progress` and `completed` are enrolments; `wishlist` is what was saved."""
    if state == "wishlist":
        rows, next_cursor = paginate(
            WishlistItem.objects.filter(user_id=viewer_id)
            .exclude(course__status="removed")
            .select_related("course"),
            fields=("created_at", "id"),
            sort="wishlist",
            cursor=cursor,
            limit=limit,
        )
        return {
            "results": [selectors.course_summary(w.course, viewer_id) for w in rows],
            "next_cursor": next_cursor,
        }
    enrolments: QuerySet[Enrolment] = (
        Enrolment.objects.filter(user_id=viewer_id)
        .exclude(course__status="removed")
        .select_related("course")
    )
    if state == "completed":
        enrolments = enrolments.filter(completed_at__isnull=False)
    elif state == "in_progress":
        enrolments = enrolments.filter(completed_at__isnull=True)
    rows, next_cursor = paginate(
        enrolments, fields=("started_at", "id"), sort=f"shelf-{state}", cursor=cursor, limit=limit
    )
    return {
        "results": [selectors.course_summary(e.course, viewer_id) for e in rows],
        "next_cursor": next_cursor,
    }


# --- questions, notes, announcements ---


def questions(user: Any, lesson_id: UUID) -> list[dict[str, Any]]:
    lesson = engage._open(user, lesson_id)
    rows = list(
        LectureQuestion.objects.filter(lesson=lesson, hidden_at__isnull=True)
        .prefetch_related("answers")
        .order_by("-created_at")[:100]
    )
    people = {r.user_id for r in rows} | {a.user_id for r in rows for a in r.answers.all()}
    cards = profiles.cards_for(user, list(people))

    def name(user_id: UUID) -> str:
        return str(cards[user_id]["name"])

    return [
        {
            "id": q.pk,
            "body": q.body,
            "asker": name(q.user_id),
            "mine": q.user_id == user.pk,
            "created_at": q.created_at,
            "answers": [
                {
                    "id": a.pk,
                    "body": a.body,
                    "author": name(a.user_id),
                    "is_staff": a.is_staff,
                    "mine": a.user_id == user.pk,
                    "created_at": a.created_at,
                }
                for a in q.answers.all()
                if a.hidden_at is None
            ],
        }
        for q in rows
    ]


def notes(user_id: UUID, lesson_id: UUID) -> list[dict[str, Any]]:
    rows = LectureNote.objects.filter(user_id=user_id, lesson_id=lesson_id).order_by(
        "seconds", "created_at"
    )
    return [
        {"id": n.pk, "seconds": n.seconds, "body": n.body, "created_at": n.created_at} for n in rows
    ]


def announcements(user: Any, course_id: UUID) -> list[dict[str, Any]]:
    course = selectors._visible_course(user.pk, course_id)
    if not engage.is_staff(user) and learn.enrolment_of(user.pk, course.pk) is None:
        raise learn.EntitlementRequired("Enrol in this course to read its announcements.")
    rows = CourseAnnouncement.objects.filter(course=course).order_by("-created_at")[:50]
    return [
        {"id": a.pk, "title": a.title, "body": a.body, "created_at": a.created_at} for a in rows
    ]


def review_of(viewer_id: UUID, course: Course) -> CourseRating | None:
    return CourseRating.objects.filter(course=course, user_id=viewer_id).first()
