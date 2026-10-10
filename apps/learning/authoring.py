"""Writing courses: the admin's side of the learning hub."""

import re
import secrets
from typing import Any
from uuid import UUID

from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from django.utils.text import slugify
from rest_framework import exceptions

from apps.audit import services as audit
from apps.core import etag
from apps.core.text import clean_url, plain, rich_post, text_of
from apps.integrations import youtube
from apps.learning.models import ACCESS, LESSON_TYPES, LEVELS, Course, Lesson, Module
from apps.uploads import services as uploads

MAX_DESCRIPTION_TEXT = 10_000
MAX_READING_TEXT = 50_000
MAX_MODULES = 50
MAX_LESSONS_PER_MODULE = 100
CURRENCY = re.compile(r"^[A-Z]{3}$")


class NotFound(exceptions.NotFound):
    default_detail = "Not found."


class Conflict(exceptions.APIException):
    status_code = 409
    default_code = "conflict"


def _invalid(field: str, message: str) -> exceptions.ValidationError:
    return exceptions.ValidationError({field: [message]})


def _lock_course(course_id: UUID) -> Course:
    course = (
        Course.objects.select_for_update()
        .exclude(status=Course.Status.REMOVED)
        .filter(pk=course_id)
        .first()
    )
    if course is None:
        raise NotFound()
    return course


# --- courses ---


def _apply(course: Course, data: dict[str, Any]) -> None:
    if "title" in data:
        course.title = plain(data["title"])
        if not course.title:
            raise _invalid("title", "This field may not be blank.")
    if "description" in data:
        course.description = rich_post(data["description"])
        course.description_text = text_of(course.description)
        if not course.description_text:
            raise _invalid("description", "This field may not be blank.")
        if len(course.description_text) > MAX_DESCRIPTION_TEXT:
            raise _invalid("description", f"Up to {MAX_DESCRIPTION_TEXT} characters.")
    for field in ("instructor", "category"):
        if field in data:
            value = plain(data[field])
            if not value:
                raise _invalid(field, "This field may not be blank.")
            setattr(course, field, value)
    if "level" in data:
        if data["level"] not in LEVELS:
            raise _invalid("level", "Choose beginner, intermediate or advanced.")
        course.level = data["level"]
    for field in ("open_to_visitors", "certificate_enabled"):
        if field in data:
            setattr(course, field, bool(data[field]))
    if "access" in data:
        if data["access"] not in ACCESS:
            raise _invalid("access", "Choose free or paid.")
        course.access = data["access"]
    if "price_minor" in data:
        course.price_minor = data["price_minor"]
    if "currency" in data:
        course.currency = data["currency"].upper()
    _check_pricing(course)


def _check_pricing(course: Course) -> None:
    if course.access == "free":
        course.price_minor, course.currency = None, ""
        return
    if not course.price_minor:
        raise _invalid("price_minor", "A paid course needs a price above zero.")
    if not CURRENCY.match(course.currency):
        raise _invalid("currency", "Use a three-letter currency code such as NGN or USD.")
    if course.open_to_visitors:
        raise _invalid("open_to_visitors", "Only free courses can be opened to visitors.")


def _new_slug(title: str) -> str:
    return f"{slugify(title)[:70] or 'course'}-{secrets.token_hex(3)}"


def create_course(*, actor: Any, data: dict[str, Any], ip: str = "") -> Course:
    course = Course(slug=_new_slug(data.get("title", "")), created_by=actor)
    _apply(course, data)
    with transaction.atomic():
        course.save()
        audit.record(
            actor=actor, action="courses.created", target_type="course", target_id=course.pk, ip=ip
        )
    return course


def update_course(
    *, actor: Any, course_id: UUID, data: dict[str, Any], if_match: str | None, ip: str = ""
) -> Course:
    with transaction.atomic():
        course = _lock_course(course_id)
        etag.assert_matches(if_match, course)
        _apply(course, data)
        course.edited_at = timezone.now()
        course.save()
        audit.record(
            actor=actor, action="courses.updated", target_type="course", target_id=course.pk, ip=ip
        )
    return course


def publish(*, actor: Any, course_id: UUID, ip: str = "") -> Course:
    with transaction.atomic():
        course = _lock_course(course_id)
        if course.status == Course.Status.PUBLISHED:
            raise Conflict("This course is already published.")
        if not course.lessons.exists():
            raise _invalid("lessons", "Add at least one lesson before publishing.")
        course.status = Course.Status.PUBLISHED
        course.published_at = course.published_at or timezone.now()
        course.save(update_fields=["status", "published_at", "updated_at"])
        audit.record(
            actor=actor,
            action="courses.published",
            target_type="course",
            target_id=course.pk,
            ip=ip,
        )
    return course


def unpublish(*, actor: Any, course_id: UUID, ip: str = "") -> Course:
    """Hide a course from the catalogue. People already enrolled keep their progress."""
    with transaction.atomic():
        course = _lock_course(course_id)
        if course.status != Course.Status.PUBLISHED:
            raise Conflict("This course is not published.")
        course.status = Course.Status.DRAFT
        course.save(update_fields=["status", "updated_at"])
        audit.record(
            actor=actor,
            action="courses.unpublished",
            target_type="course",
            target_id=course.pk,
            ip=ip,
        )
    return course


def remove_course(*, actor: Any, course_id: UUID, ip: str = "") -> None:
    with transaction.atomic():
        course = _lock_course(course_id)
        course.status = Course.Status.REMOVED
        course.save(update_fields=["status", "updated_at"])
        audit.record(
            actor=actor, action="courses.removed", target_type="course", target_id=course.pk, ip=ip
        )


def duplicate(*, actor: Any, course_id: UUID, ip: str = "") -> Course:
    """A draft copy with all modules and lessons (not enrolments, ratings or the cover)."""
    with transaction.atomic():
        source = _lock_course(course_id)
        copy = Course.objects.create(
            slug=_new_slug(source.title),
            title=f"Copy of {source.title}"[:160],
            description=source.description,
            description_text=source.description_text,
            instructor=source.instructor,
            category=source.category,
            level=source.level,
            access=source.access,
            price_minor=source.price_minor,
            currency=source.currency,
            open_to_visitors=source.open_to_visitors,
            certificate_enabled=source.certificate_enabled,
            created_by=actor,
        )
        for module in source.modules.all():
            new_module = Module.objects.create(
                course=copy, title=module.title, position=module.position
            )
            Lesson.objects.bulk_create(
                Lesson(
                    module=new_module,
                    course=copy,
                    type=lesson.type,
                    title=lesson.title,
                    position=lesson.position,
                    duration_seconds=lesson.duration_seconds,
                    video_provider=lesson.video_provider,
                    video_id=lesson.video_id,
                    video_url=lesson.video_url,
                    body=lesson.body,
                    resource_url=lesson.resource_url,
                    resource_name=lesson.resource_name,
                )
                for lesson in module.lessons.all()
            )
        audit.record(
            actor=actor,
            action="courses.duplicated",
            target_type="course",
            target_id=copy.pk,
            after={"from": str(source.pk)},
            ip=ip,
        )
    return copy


def set_cover(*, actor: Any, course_id: UUID, upload_id: UUID | None) -> Course:
    with transaction.atomic():
        course = _lock_course(course_id)
        previous = course.cover_key
        if upload_id is None:
            course.cover_key = ""
        else:
            upload = uploads.claim(upload_id=upload_id, owner_id=actor.pk, purpose="course_cover")
            course.cover_key = upload.base_key
        course.save(update_fields=["cover_key", "updated_at"])
        uploads.release(previous)
    return course


# --- modules ---


def add_module(*, actor: Any, course_id: UUID, title: str, ip: str = "") -> Module:
    clean = plain(title)
    if not clean:
        raise _invalid("title", "This field may not be blank.")
    with transaction.atomic():
        course = _lock_course(course_id)
        if course.modules.count() >= MAX_MODULES:
            raise _invalid("title", f"A course can have up to {MAX_MODULES} modules.")
        last = course.modules.aggregate(m=Max("position"))["m"]
        module = Module.objects.create(
            course=course, title=clean, position=0 if last is None else last + 1
        )
        audit.record(
            actor=actor,
            action="courses.module_added",
            target_type="course",
            target_id=course.pk,
            ip=ip,
        )
    return module


def _lock_module(module_id: UUID) -> Module:
    module = (
        Module.objects.select_for_update(of=("self",))
        .select_related("course")
        .exclude(course__status=Course.Status.REMOVED)
        .filter(pk=module_id)
        .first()
    )
    if module is None:
        raise NotFound()
    return module


def update_module(*, actor: Any, module_id: UUID, title: str) -> Module:
    clean = plain(title)
    if not clean:
        raise _invalid("title", "This field may not be blank.")
    with transaction.atomic():
        module = _lock_module(module_id)
        module.title = clean
        module.save(update_fields=["title", "updated_at"])
    return module


def delete_module(*, actor: Any, module_id: UUID, ip: str = "") -> None:
    with transaction.atomic():
        module = _lock_module(module_id)
        course = module.course
        module.delete()
        # Close the gap so positions stay 0..n-1.
        for position, other in enumerate(course.modules.all()):
            if other.position != position:
                Module.objects.filter(pk=other.pk).update(position=position)
        audit.record(
            actor=actor,
            action="courses.module_deleted",
            target_type="course",
            target_id=course.pk,
            ip=ip,
        )


def _reorder(items: Any, ids: list[UUID], model: Any, label: str) -> None:
    current = list(items.values_list("pk", flat=True))
    if len(set(ids)) != len(ids) or set(ids) != set(current):
        raise Conflict(f"List every {label} exactly once, in the order you want.")
    for position, pk in enumerate(ids):
        model.objects.filter(pk=pk).update(position=position)


def reorder_modules(*, actor: Any, course_id: UUID, ids: list[UUID]) -> Course:
    with transaction.atomic():
        course = _lock_course(course_id)
        _reorder(course.modules.all(), ids, Module, "module")
    return course


def reorder_lessons(*, actor: Any, module_id: UUID, ids: list[UUID]) -> Module:
    with transaction.atomic():
        module = _lock_module(module_id)
        _reorder(module.lessons.all(), ids, Lesson, "lesson")
    return module


# --- lessons ---


def _apply_lesson(lesson: Lesson, data: dict[str, Any]) -> None:
    if "type" in data:
        if data["type"] not in LESSON_TYPES:
            raise _invalid("type", "Choose video, reading or resource.")
        lesson.type = data["type"]
    if "title" in data:
        lesson.title = plain(data["title"])
        if not lesson.title:
            raise _invalid("title", "This field may not be blank.")
    if "duration_seconds" in data:
        lesson.duration_seconds = data["duration_seconds"]
    if "video_url" in data:
        try:
            video = youtube.parse(data["video_url"])
        except youtube.InvalidVideoUrl as exc:
            raise _invalid("video_url", str(exc)) from exc
        lesson.video_provider, lesson.video_id, lesson.video_url = (
            "youtube",
            video.video_id,
            video.url,
        )
    if "body" in data:
        lesson.body = rich_post(data["body"])
        if len(text_of(lesson.body)) > MAX_READING_TEXT:
            raise _invalid("body", f"Up to {MAX_READING_TEXT} characters.")
    if "resource_url" in data:
        try:
            lesson.resource_url = clean_url(data["resource_url"])
        except exceptions.ValidationError as exc:
            raise _invalid("resource_url", " ".join(str(m) for m in exc.detail)) from exc
    if "resource_name" in data:
        lesson.resource_name = plain(data["resource_name"])
    _check_lesson(lesson)


def _check_lesson(lesson: Lesson) -> None:
    """A lesson holds exactly what its type needs, and nothing else."""
    if lesson.type == "video":
        if not lesson.video_id:
            raise _invalid("video_url", "A video lesson needs a YouTube link.")
        lesson.body, lesson.resource_url, lesson.resource_name = "", "", ""
    elif lesson.type == "reading":
        if not text_of(lesson.body):
            raise _invalid("body", "A reading lesson needs some text.")
        lesson.video_provider = lesson.video_id = lesson.video_url = ""
        lesson.resource_url = lesson.resource_name = ""
    else:
        if not lesson.resource_url:
            raise _invalid("resource_url", "A resource lesson needs a link to the file.")
        if not lesson.resource_name:
            raise _invalid("resource_name", "Name the file members will download.")
        lesson.video_provider = lesson.video_id = lesson.video_url = ""
        lesson.body = ""


def add_lesson(*, actor: Any, module_id: UUID, data: dict[str, Any], ip: str = "") -> Lesson:
    with transaction.atomic():
        module = _lock_module(module_id)
        if module.lessons.count() >= MAX_LESSONS_PER_MODULE:
            raise _invalid("title", f"A module can have up to {MAX_LESSONS_PER_MODULE} lessons.")
        last = module.lessons.aggregate(m=Max("position"))["m"]
        lesson = Lesson(
            module=module, course=module.course, position=0 if last is None else last + 1
        )
        _apply_lesson(lesson, data)
        lesson.save()
        audit.record(
            actor=actor,
            action="courses.lesson_added",
            target_type="course",
            target_id=module.course_id,
            ip=ip,
        )
    return lesson


def _lock_lesson(lesson_id: UUID) -> Lesson:
    lesson = (
        Lesson.objects.select_for_update(of=("self",))
        .select_related("module", "course")
        .exclude(course__status=Course.Status.REMOVED)
        .filter(pk=lesson_id)
        .first()
    )
    if lesson is None:
        raise NotFound()
    return lesson


def update_lesson(*, actor: Any, lesson_id: UUID, data: dict[str, Any]) -> Lesson:
    with transaction.atomic():
        lesson = _lock_lesson(lesson_id)
        _apply_lesson(lesson, data)
        lesson.save()
    return lesson


def delete_lesson(*, actor: Any, lesson_id: UUID, ip: str = "") -> None:
    with transaction.atomic():
        lesson = _lock_lesson(lesson_id)
        module, course_id = lesson.module, lesson.course_id
        lesson.delete()
        for position, other in enumerate(module.lessons.all()):
            if other.position != position:
                Lesson.objects.filter(pk=other.pk).update(position=position)
        audit.record(
            actor=actor,
            action="courses.lesson_deleted",
            target_type="course",
            target_id=course_id,
            ip=ip,
        )
