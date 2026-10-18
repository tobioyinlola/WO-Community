"""A published course as a share card: what it is about, never its lectures."""

from apps.core import shareables
from apps.learning.models import Course
from apps.uploads import services as uploads

LEVELS = {
    "beginner": "Beginner",
    "intermediate": "Intermediate",
    "advanced": "Advanced",
    "all": "All levels",
}


def course_card(ref: str) -> shareables.Card | None:
    course = Course.objects.filter(slug=ref, status=Course.Status.PUBLISHED).first()
    if course is None:
        return None
    lessons = course.lessons.count()
    facts = [f"{lessons} lecture{'s' if lessons != 1 else ''}"] if lessons else []
    facts += [LEVELS.get(course.level, ""), "Free" if course.access == "free" else "Paid"]
    cover = uploads.image_urls(course.cover_key)
    return shareables.Card(
        kind="course",
        ref=course.slug,
        title=course.title,
        excerpt=shareables.excerpt(course.subtitle or course.description_text),
        url=f"/app/learn/courses/{course.slug}",
        badge=course.category or "Course",
        action="View course",
        image=cover["large"] if cover else None,
        facts=[f for f in facts if f],
        by=course.instructor,
    )
