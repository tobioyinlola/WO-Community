"""Members report comments on news and wins; moderators handle them in the shared queue.

The queue itself is in the admin console, which lists these reports beside the feed's. This module
owns what only editorial can know: whether a comment can be seen, how to hide it, and who is told.
"""

from typing import Any
from uuid import UUID

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Count, QuerySet
from django.utils import timezone
from rest_framework import exceptions

from apps.analytics import services as analytics
from apps.audit import services as audit
from apps.core import events as domain_events
from apps.core import ratelimit
from apps.core.text import plain, text_of
from apps.editorial import events, services
from apps.editorial.models import CommentReport, ItemComment
from apps.profiles import selectors as profiles

DAY = 86400
EXCERPT = 200
TARGET_TYPE = "news_comment"


class AlreadyHandled(exceptions.APIException):
    status_code = 409
    default_code = "already_handled"
    default_detail = "This report has already been actioned."


def report(
    *, viewer: Any, comment_id: UUID, reason: str, details: str = ""
) -> tuple[CommentReport, bool]:
    """File a report. Returns it and False if this member had already reported the comment.

    A member can report only a comment they can see, and not their own.
    """
    from apps.editorial import selectors

    view = selectors.get_comment(viewer, comment_id)
    if view["author"]["id"] == viewer.pk:
        raise exceptions.ValidationError({"target": ["You cannot report your own content."]})
    existing = CommentReport.objects.filter(reporter_id=viewer.pk, comment_id=comment_id).first()
    if existing is not None:
        return existing, False
    if ratelimit.hit(f"editorial:report:{viewer.pk}", DAY) > settings.FEED_REPORTS_PER_DAY:
        raise exceptions.Throttled(wait=DAY, detail="Daily limit for reports reached.")
    try:
        with transaction.atomic():
            created = CommentReport.objects.create(
                reporter_id=viewer.pk,
                comment_id=comment_id,
                reason=reason,
                details=plain(details),
            )
    except IntegrityError:  # the same member reported it twice at once
        return CommentReport.objects.get(reporter_id=viewer.pk, comment_id=comment_id), False
    return created, True


# --- the moderators' side ---


def open_count() -> int:
    return CommentReport.objects.filter(status=CommentReport.Status.OPEN).count()


def queue(*, status: str, reason: str) -> QuerySet[CommentReport]:
    queryset = CommentReport.objects.all()
    if status:
        queryset = queryset.filter(status=status)
    if reason:
        queryset = queryset.filter(reason=reason)
    return queryset.order_by("created_at", "id")


def get_report(report_id: UUID) -> CommentReport | None:
    return CommentReport.objects.filter(pk=report_id).first()


def _state(comment: ItemComment | None) -> str:
    if comment is None or comment.deleted_at is not None:
        return "removed"
    return "hidden" if comment.hidden_at is not None else "visible"


def views(viewer: Any, reports: list[CommentReport]) -> list[dict[str, Any]]:
    """Reports in the same shape as the feed's, with the comment's news item as ``post_id``."""
    comments = ItemComment.objects.in_bulk([r.comment_id for r in reports])
    open_counts = {
        row["comment_id"]: row["n"]
        for row in CommentReport.objects.filter(
            status=CommentReport.Status.OPEN, comment_id__in=list(comments)
        )
        .values("comment_id")
        .annotate(n=Count("id"))
    }
    people = {*(r.reporter_id for r in reports), *(c.author_id for c in comments.values())}
    cards = profiles.cards_for(viewer, list(people))
    out = []
    for item in reports:
        comment = comments.get(item.comment_id)
        out.append(
            {
                "id": item.pk,
                "status": item.status,
                "reason": item.reason,
                "details": item.details,
                "created_at": item.created_at,
                "reporter": {"id": item.reporter_id, "name": cards[item.reporter_id]["name"]},
                "handled_by": item.handled_by_id,
                "handled_at": item.handled_at,
                "note": item.note,
                "open_reports_on_target": open_counts.get(item.comment_id, 0),
                "target": {
                    "type": TARGET_TYPE,
                    "id": item.comment_id,
                    "post_id": comment.item_id if comment else None,
                    "state": _state(comment),
                    "excerpt": text_of(comment.body)[:EXCERPT] if comment else "",
                    "created_at": comment.created_at if comment else None,
                    "author": (
                        {"id": comment.author_id, "name": cards[comment.author_id]["name"]}
                        if comment
                        else None
                    ),
                },
            }
        )
    return out


def _tell(reports: list[CommentReport], outcome: str) -> None:
    for item in reports:
        domain_events.publish(
            events.CommentReportHandled(
                reporter_id=str(item.reporter_id), outcome=outcome, target_type=TARGET_TYPE
            )
        )


def review(*, actor: Any, report_id: UUID, note: str = "", ip: str = "") -> CommentReport:
    with transaction.atomic():
        found = CommentReport.objects.select_for_update().filter(pk=report_id).first()
        if found is None:
            raise exceptions.NotFound()
        if found.status == CommentReport.Status.ACTIONED:
            raise AlreadyHandled()
        found.status = CommentReport.Status.REVIEWED
        found.handled_by = actor
        found.handled_at = timezone.now()
        found.note = plain(note)
        found.save()
        _tell([found], "reviewed")
        analytics.track("report_actioned", actor_id=actor.pk, properties={"outcome": "reviewed"})
        audit.record(
            actor=actor,
            action="editorial.report_reviewed",
            target_type="report",
            target_id=found.pk,
            reason=found.note,
            ip=ip,
        )
    return found


def act(*, actor: Any, report_id: UUID, action: str, note: str = "", ip: str = "") -> CommentReport:
    """Hide or remove the comment and close every open report about it as actioned."""
    with transaction.atomic():
        found = CommentReport.objects.select_for_update().filter(pk=report_id).first()
        if found is None:
            raise exceptions.NotFound()
        clean_note = plain(note)
        try:
            services.moderate_comment(
                actor=actor, comment_id=found.comment_id, action=action, reason=clean_note, ip=ip
            )
        except services.NotFound:
            pass  # already removed by someone else; the report is still closed below
        now = timezone.now()
        siblings = CommentReport.objects.filter(comment_id=found.comment_id).exclude(
            status=CommentReport.Status.ACTIONED
        )
        _tell(list(siblings), "actioned")
        siblings.update(
            status=CommentReport.Status.ACTIONED,
            handled_by=actor,
            handled_at=now,
            note=clean_note,
            updated_at=now,
        )
        analytics.track("report_actioned", actor_id=actor.pk, properties={"outcome": "actioned"})
        audit.record(
            actor=actor,
            action="editorial.report_actioned",
            target_type="report",
            target_id=found.pk,
            after={"action": action},
            reason=clean_note,
            ip=ip,
        )
        found.refresh_from_db()
    return found
