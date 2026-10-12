"""Shared rules for the learning hub that are not about one screen: counts kept on a course, what a
course needs before it can be published, and when a promotion applies."""

from datetime import datetime
from typing import Any
from uuid import UUID

from django.db.models import Count, Sum
from django.utils import timezone

from apps.learning.models import Course, Enrolment, Lesson

LANGUAGES = {
    "en": "English",
    "fr": "French",
    "pt": "Portuguese",
    "ar": "Arabic",
    "sw": "Swahili",
    "ha": "Hausa",
    "yo": "Yoruba",
    "ig": "Igbo",
    "am": "Amharic",
}
CURRENCIES = ("NGN", "USD", "KES", "GHS", "ZAR", "EGP", "GBP", "EUR")
MIN_LECTURES_TO_PUBLISH = 3
MAX_BULLETS = 8
MAX_REQUIREMENTS = 10
RATING_MIN_PERCENT = 25


def refresh_counts(course_id: UUID) -> None:
    """Recompute what a course keeps for the catalogue: learners and total running time."""
    learners = Enrolment.objects.filter(course_id=course_id).aggregate(n=Count("id"))["n"]
    seconds = Lesson.objects.filter(course_id=course_id).aggregate(s=Sum("duration_seconds"))["s"]
    Course.objects.filter(pk=course_id).update(
        learners_count=learners or 0, total_duration_seconds=seconds or 0
    )


def promo_active(course: Course, now: datetime | None = None) -> bool:
    """Whether the promotional price is the one to show right now."""
    if course.access != "paid" or not course.promo_price_minor:
        return False
    moment = now or timezone.now()
    if course.promo_starts_at and moment < course.promo_starts_at:
        return False
    return not (course.promo_ends_at and moment >= course.promo_ends_at)


def current_price_minor(course: Course) -> int | None:
    if course.access != "paid":
        return None
    return course.promo_price_minor if promo_active(course) else course.price_minor


def publish_checklist(course: Course) -> list[dict[str, Any]]:
    """What a course needs before it can go live, each with the wizard step that fixes it."""
    lectures = course.lessons.count()
    videos = course.lessons.filter(type="video")
    return [
        {"key": "title", "text": "A title", "done": bool(course.title.strip()), "step": 1},
        {
            "key": "description",
            "text": "A description",
            "done": bool(course.description_text),
            "step": 1,
        },
        {"key": "category", "text": "A category", "done": bool(course.category), "step": 1},
        {
            "key": "thumbnail",
            "text": "A thumbnail image",
            "done": bool(course.cover_key),
            "step": 1,
        },
        {
            "key": "curriculum",
            "text": f"At least one section and {MIN_LECTURES_TO_PUBLISH} lectures",
            "done": course.modules.exists() and lectures >= MIN_LECTURES_TO_PUBLISH,
            "step": 2,
        },
        {
            "key": "links",
            "text": "A valid YouTube link on every video lecture",
            "done": not videos.filter(video_id="").exists(),
            "step": 2,
        },
        {
            "key": "pricing",
            "text": "A price, or free",
            "done": course.access == "free" or bool(course.price_minor and course.currency),
            "step": 3,
        },
    ]
