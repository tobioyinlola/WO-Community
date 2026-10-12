"""What learners and course staff do around a course: saving it, asking for access, asking and
answering questions, keeping notes, and announcements. Each rule is checked here, not in a view."""

from typing import Any
from uuid import UUID

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import exceptions

from apps.accounts import selectors as accounts
from apps.accounts import services as account_services
from apps.audit import services as audit
from apps.core.rbac import permissions_for
from apps.core.text import plain, rich_post, text_of
from apps.learning import learn, lms
from apps.learning.models import (
    Course,
    CourseAnnouncement,
    CourseRating,
    Enrolment,
    EnrolmentRequest,
    LectureAnswer,
    LectureNote,
    LectureQuestion,
    Lesson,
    WishlistItem,
)
from apps.notifications import notify

STAFF_ROLES = ["content_editor", "community_admin", "super_admin"]
MAX_NOTES_PER_LESSON = 200


def _invalid(field: str, message: str) -> exceptions.ValidationError:
    return exceptions.ValidationError({field: [message]})


def _course(course_id: UUID) -> Course:
    course = Course.objects.filter(pk=course_id).exclude(status=Course.Status.REMOVED).first()
    if course is None:
        raise exceptions.NotFound()
    return course


def is_staff(user: Any) -> bool:
    return "courses.manage" in permissions_for(user.role_names())


# --- saving for later ---


def set_wishlist(*, user_id: UUID, course_id: UUID, saved: bool) -> bool:
    course = _course(course_id)
    if course.status not in learn.OPEN_STATUSES:
        raise exceptions.NotFound()
    if saved:
        try:
            with transaction.atomic():
                WishlistItem.objects.get_or_create(user_id=user_id, course=course)
        except IntegrityError:  # two taps at once
            pass
    else:
        WishlistItem.objects.filter(user_id=user_id, course=course).delete()
    return saved


# --- asking for a paid course while payments are off ---


def request_access(*, user_id: UUID, course_id: UUID, message: str) -> EnrolmentRequest:
    course = _course(course_id)
    if course.status not in learn.OPEN_STATUSES:
        raise exceptions.NotFound()
    if course.access != "paid":
        raise learn.Conflict("This course is free: enrol directly.")
    if not course.enrolment_active:
        raise learn.Conflict("Enrolment for this course is closed for now.")
    if learn.enrolment_of(user_id, course.pk) is not None:
        raise learn.Conflict("You already have access to this course.")
    try:
        with transaction.atomic():
            request, created = EnrolmentRequest.objects.get_or_create(
                course=course,
                user_id=user_id,
                status=EnrolmentRequest.Status.PENDING,
                defaults={"message": plain(message)[:500]},
            )
    except IntegrityError:
        request = EnrolmentRequest.objects.get(
            course=course, user_id=user_id, status=EnrolmentRequest.Status.PENDING
        )
        created = False
    if created:
        for admin_id in accounts.ids_with_roles(STAFF_ROLES).distinct():
            notify.notify(
                admin_id,
                "course_request",
                {"course_id": str(course.pk), "title": course.title, "actor_id": str(user_id)},
                dedupe_key=f"course-request:{request.pk}",
            )
    return request


def my_request(user_id: UUID, course_id: UUID) -> EnrolmentRequest | None:
    return (
        EnrolmentRequest.objects.filter(user_id=user_id, course_id=course_id)
        .order_by("-created_at")
        .first()
    )


@transaction.atomic
def decide_request(
    *, actor: Any, request_id: UUID, approve: bool, ip: str = ""
) -> EnrolmentRequest:
    request = (
        EnrolmentRequest.objects.select_for_update(of=("self",))
        .select_related("course")
        .filter(pk=request_id)
        .first()
    )
    if request is None:
        raise exceptions.NotFound()
    if request.status != EnrolmentRequest.Status.PENDING:
        raise learn.Conflict("This request has already been decided.")
    if approve:
        if not account_services.is_active(request.user_id):
            raise _invalid("user_id", "Only active members can be given a course.")
        learn.grant(actor=actor, course_id=request.course_id, user_id=request.user_id, ip=ip)
    request.status = (
        EnrolmentRequest.Status.APPROVED if approve else EnrolmentRequest.Status.REJECTED
    )
    request.decided_by, request.decided_at = actor, timezone.now()
    request.save(update_fields=["status", "decided_by", "decided_at", "updated_at"])
    audit.record(
        actor=actor,
        action="courses.request_approved" if approve else "courses.request_declined",
        target_type="course",
        target_id=request.course_id,
        after={"user_id": str(request.user_id)},
        ip=ip,
    )
    if not approve:
        notify.notify(
            request.user_id,
            "course_request_declined",
            {"course_id": str(request.course_id), "title": request.course.title},
            dedupe_key=f"course-request-declined:{request.pk}",
        )
    return request


# --- questions and answers ---


def _open(viewer: Any, lesson_id: UUID) -> Lesson:
    """The lesson, if this person may open it (staff may open any)."""
    lesson = Lesson.objects.select_related("course").filter(pk=lesson_id).first()
    if lesson is None or lesson.course.status == Course.Status.REMOVED:
        raise exceptions.NotFound()
    if is_staff(viewer) or learn.enrolment_of(viewer.pk, lesson.course_id) is not None:
        return lesson
    raise learn.EntitlementRequired("Enrol in this course to ask or answer questions.")


def ask(*, user: Any, lesson_id: UUID, body: str) -> LectureQuestion:
    lesson = _open(user, lesson_id)
    text = plain(body)
    if not text:
        raise _invalid("body", "Write your question first.")
    return LectureQuestion.objects.create(lesson=lesson, course=lesson.course, user=user, body=text)


def answer(*, user: Any, question_id: UUID, body: str) -> LectureAnswer:
    question = (
        LectureQuestion.objects.select_related("lesson", "course")
        .filter(pk=question_id, hidden_at__isnull=True)
        .first()
    )
    if question is None:
        raise exceptions.NotFound()
    _open(user, question.lesson_id)
    text = plain(body)
    if not text:
        raise _invalid("body", "Write your answer first.")
    reply = LectureAnswer.objects.create(
        question=question, user=user, body=text, is_staff=is_staff(user)
    )
    notify.notify(
        question.user_id,
        "lecture_answer",
        {
            "course_id": str(question.course_id),
            "lesson_id": str(question.lesson_id),
            "title": question.course.title,
            "actor_id": str(user.pk),
        },
        dedupe_key=f"answer:{reply.pk}",
    )
    return reply


def set_hidden(*, actor: Any, kind: str, item_id: UUID, hidden: bool, ip: str = "") -> None:
    """Take a question, answer or review down (or put it back). Reviews leave the average."""
    when = timezone.now() if hidden else None
    with transaction.atomic():
        if kind == "review":
            rating = CourseRating.objects.select_related("course").filter(pk=item_id).first()
            if rating is None:
                raise exceptions.NotFound()
            rating.hidden_at, rating.hidden_by = when, (actor if hidden else None)
            rating.save(update_fields=["hidden_at", "hidden_by", "updated_at"])
            learn.recount_ratings(rating.course)
            target_id = rating.pk
        elif kind == "question":
            question = LectureQuestion.objects.filter(pk=item_id).first()
            if question is None:
                raise exceptions.NotFound()
            question.hidden_at = when
            question.save(update_fields=["hidden_at", "updated_at"])
            target_id = question.pk
        else:
            reply = LectureAnswer.objects.filter(pk=item_id).first()
            if reply is None:
                raise exceptions.NotFound()
            reply.hidden_at = when
            reply.save(update_fields=["hidden_at", "updated_at"])
            target_id = reply.pk
        audit.record(
            actor=actor,
            action=f"courses.{kind}_{'hidden' if hidden else 'restored'}",
            target_type=kind,
            target_id=target_id,
            ip=ip,
        )


# --- notes ---


def add_note(*, user_id: UUID, lesson_id: UUID, seconds: int, body: str) -> LectureNote:
    lesson = Lesson.objects.select_related("course").filter(pk=lesson_id).first()
    if lesson is None or learn.enrolment_of(user_id, lesson.course_id) is None:
        raise exceptions.NotFound()
    text = plain(body)
    if not text:
        raise _invalid("body", "Write a note first.")
    if LectureNote.objects.filter(user_id=user_id, lesson=lesson).count() >= MAX_NOTES_PER_LESSON:
        raise _invalid("body", f"You can keep up to {MAX_NOTES_PER_LESSON} notes on one lecture.")
    return LectureNote.objects.create(user_id=user_id, lesson=lesson, seconds=seconds, body=text)


def delete_note(*, user_id: UUID, note_id: UUID) -> None:
    deleted, _ = LectureNote.objects.filter(pk=note_id, user_id=user_id).delete()
    if not deleted:
        raise exceptions.NotFound()


# --- announcements ---


def announce(
    *, actor: Any, course_id: UUID, title: str, body: str, ip: str = ""
) -> CourseAnnouncement:
    """Post a message to a course's learners, and tell each of them."""
    course = _course(course_id)
    clean_title, html = plain(title), rich_post(body)
    if not clean_title:
        raise _invalid("title", "Give the announcement a title.")
    if not text_of(html):
        raise _invalid("body", "Write the announcement.")
    with transaction.atomic():
        item = CourseAnnouncement.objects.create(
            course=course, author=actor, title=clean_title[:160], body=html
        )
        audit.record(
            actor=actor,
            action="courses.announced",
            target_type="course",
            target_id=course.pk,
            ip=ip,
        )
    learners = Enrolment.objects.filter(course=course).values_list("user_id", flat=True)
    for learner_id in learners:
        notify.notify(
            learner_id,
            "course_announcement",
            {
                "course_id": str(course.pk),
                "title": course.title,
                "announcement": item.title,
                "actor_id": str(actor.pk),
            },
            dedupe_key=f"announcement:{item.pk}",
        )
    return item


def remove_enrolment(*, actor: Any, course_id: UUID, user_id: UUID, ip: str = "") -> None:
    """Take a learner off a course. Their progress goes with the enrolment."""
    course = _course(course_id)
    with transaction.atomic():
        deleted, _ = Enrolment.objects.filter(course=course, user_id=user_id).delete()
        if not deleted:
            raise exceptions.NotFound()
        lms.refresh_counts(course.pk)
        audit.record(
            actor=actor,
            action="courses.enrolment_removed",
            target_type="course",
            target_id=course.pk,
            after={"user_id": str(user_id)},
            ip=ip,
        )
