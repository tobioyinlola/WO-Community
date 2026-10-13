"""Read side for the course management page: who asked, who is learning, what they said."""

import csv
import io
from typing import Any
from uuid import UUID

from django.db.models import Count, QuerySet

from apps.accounts.models import User
from apps.learning.models import (
    Course,
    Enrolment,
    EnrolmentRequest,
    LectureQuestion,
    LessonProgress,
)
from apps.profiles.models import FounderProfile


def people(user_ids: list[UUID]) -> dict[UUID, dict[str, str]]:
    """Name and email for a page of people, in two queries. An admin sees both in full."""
    names = dict(
        FounderProfile.objects.filter(user_id__in=user_ids).values_list("user_id", "full_name")
    )
    emails = dict(User.objects.filter(pk__in=user_ids).values_list("pk", "email"))
    return {
        uid: {
            "name": names.get(uid) or emails.get(uid, "").split("@")[0],
            "email": emails.get(uid, ""),
        }
        for uid in user_ids
    }


def request_rows(course: Course | None, status: str) -> QuerySet[EnrolmentRequest]:
    rows = EnrolmentRequest.objects.select_related("course").order_by("-created_at", "-id")
    if course is not None:
        rows = rows.filter(course=course)
    if status:
        rows = rows.filter(status=status)
    return rows


def request_views(rows: list[EnrolmentRequest]) -> list[dict[str, Any]]:
    who = people([r.user_id for r in rows])
    return [
        {
            "id": r.pk,
            "status": r.status,
            "message": r.message,
            "created_at": r.created_at,
            "decided_at": r.decided_at,
            "course": {"id": r.course_id, "title": r.course.title},
            "user": {"id": r.user_id, **who[r.user_id]},
        }
        for r in rows
    ]


def learner_views(course: Course, rows: list[Enrolment]) -> list[dict[str, Any]]:
    total = course.lessons.count()
    done = {
        r["enrolment_id"]: r["n"]
        for r in LessonProgress.objects.filter(
            enrolment__in=rows, completed_at__isnull=False, lesson__course=course
        )
        .values("enrolment_id")
        .annotate(n=Count("id"))
    }
    who = people([e.user_id for e in rows])
    return [
        {
            "user_id": e.user_id,
            "name": who[e.user_id]["name"],
            "email": who[e.user_id]["email"],
            "origin": e.source,
            "started_at": e.started_at,
            "completed_at": e.completed_at,
            "percent": int(done.get(e.pk, 0) * 100 / total) if total else 0,
        }
        for e in rows
    ]


def learners_csv(course: Course) -> str:
    """Everyone enrolled, as a spreadsheet: for an admin to keep, so it names people in full."""
    rows = list(course.enrolments.order_by("started_at", "id"))
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["Name", "Email", "How they joined", "Started", "Progress %", "Completed"])
    for item in learner_views(course, rows):
        writer.writerow(
            [
                _safe(item["name"]),
                item["email"],
                item["origin"],
                item["started_at"].date().isoformat(),
                item["percent"],
                item["completed_at"].date().isoformat() if item["completed_at"] else "",
            ]
        )
    return out.getvalue()


def _safe(value: str) -> str:
    """Stop a name that starts like a formula from being run when the file is opened."""
    return f"'{value}" if value[:1] in ("=", "+", "-", "@") else value


def review_views(course: Course) -> list[dict[str, Any]]:
    rows = list(course.ratings.order_by("-created_at"))
    who = people([r.user_id for r in rows])
    return [
        {
            "id": r.pk,
            "user_id": r.user_id,
            "reviewer": who[r.user_id]["name"],
            "stars": r.stars,
            "feedback": r.feedback,
            "created_at": r.created_at,
            "hidden": r.hidden_at is not None,
        }
        for r in rows
    ]


def question_views(course: Course) -> list[dict[str, Any]]:
    rows = list(
        LectureQuestion.objects.filter(course=course)
        .select_related("lesson")
        .prefetch_related("answers")
        .order_by("-created_at")[:200]
    )
    ids = {q.user_id for q in rows} | {a.user_id for q in rows for a in q.answers.all()}
    who = people(list(ids))
    return [
        {
            "id": q.pk,
            "lecture": q.lesson.title,
            "lesson_id": q.lesson_id,
            "body": q.body,
            "asker": who[q.user_id]["name"],
            "created_at": q.created_at,
            "hidden": q.hidden_at is not None,
            "answers": [
                {
                    "id": a.pk,
                    "body": a.body,
                    "author": who[a.user_id]["name"],
                    "is_staff": a.is_staff,
                    "hidden": a.hidden_at is not None,
                    "created_at": a.created_at,
                }
                for a in q.answers.all()
            ],
        }
        for q in rows
    ]
