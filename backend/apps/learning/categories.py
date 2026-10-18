"""Courses and the course category list the admins manage.

A course keeps its category's name, so filters and pages read it directly. The list tells this
module when an entry is renamed, and asks how many courses use one before it may be deleted.
Categories are picked from the list; one typed that is not there yet joins it.
"""

from django.db.models import Count
from django.db.models.functions import Lower

from apps.learning.models import Course
from apps.reference import selectors as reference
from apps.reference import services as reference_services


def count_by_category(slugs: list[str]) -> dict[str, int]:
    names = reference.course_category_names(slugs)
    used = dict(
        Course.objects.annotate(key=Lower("category"))
        .filter(key__in=[n.lower() for n in names.values()])
        .values("key")
        .annotate(n=Count("id"))
        .values_list("key", "n")
    )
    return {slug: used.get(name.lower(), 0) for slug, name in names.items()}


def rename(old: str, new: str) -> None:
    Course.objects.filter(category__iexact=old).update(category=new[:60])


def checked(value: str, current: str = "") -> str:
    """The category as the list spells it. A name not on the list yet is added to it, so a
    course is never held up for want of an entry; the admins tidy the list under Lists."""
    name = reference.course_category_named(value, include_retired=True)
    if name is not None:
        return name[:60]
    if current and value.strip().lower() == current.strip().lower():
        return current
    return str(reference_services.create_item(kind="course_categories", name=value[:60]).name)
