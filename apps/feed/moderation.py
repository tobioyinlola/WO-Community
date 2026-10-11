"""Reports from members and the actions admins take on them."""

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
from apps.core.text import plain, text_of
from apps.feed import events, selectors, services
from apps.feed.models import Comment, Post, Report
from apps.profiles import selectors as profiles

EXCERPT = 200


class AlreadyHandled(exceptions.APIException):
    status_code = 409
    default_code = "already_handled"
    default_detail = "This report has already been actioned."


# --- members report content ---


def report(
    *, viewer: Any, target_type: str, target_id: UUID, reason: str, details: str = ""
) -> tuple[Report, bool]:
    """File a report. Returns the report and False if this member had already reported it.

    A member can report only what they can see, and not their own content.
    """
    if target_type == "post":
        _, view = selectors.get_post(viewer, target_id)
        if view["hidden"]:
            raise exceptions.NotFound()
        author_id = view["author"]["id"]
    else:
        view = selectors.get_comment(viewer, target_id)
        author_id = view["author"]["id"]
    if author_id == viewer.pk:
        raise exceptions.ValidationError({"target": ["You cannot report your own content."]})
    existing = Report.objects.filter(
        reporter_id=viewer.pk, target_type=target_type, target_id=target_id
    ).first()
    if existing is not None:
        return existing, False
    services.spend("report", viewer.pk, settings.FEED_REPORTS_PER_DAY)
    try:
        with transaction.atomic():
            created = Report.objects.create(
                reporter_id=viewer.pk,
                target_type=target_type,
                target_id=target_id,
                reason=reason,
                details=plain(details),
            )
    except IntegrityError:  # the same member reported it twice at once
        return (
            Report.objects.get(reporter_id=viewer.pk, target_type=target_type, target_id=target_id),
            False,
        )
    return created, True


# --- admin: comments ---


def moderate_comment(
    *, actor: Any, comment_id: UUID, action: str, reason: str = "", ip: str = ""
) -> Comment:
    """Hide, unhide or remove a comment (removing takes its replies with it)."""
    with transaction.atomic():
        comment = (
            Comment.objects.select_for_update()
            .filter(pk=comment_id, deleted_at__isnull=True)
            .first()
        )
        if comment is None:
            raise exceptions.NotFound()
        if action == "hide":
            comment.hidden_at = timezone.now()
            comment.save(update_fields=["hidden_at", "updated_at"])
        elif action == "unhide":
            comment.hidden_at = None
            comment.save(update_fields=["hidden_at", "updated_at"])
        elif action == "remove":
            services.remove_comment(comment)
        else:
            raise ValueError(action)
        services.recount(comment.post_id)
        audit.record(
            actor=actor,
            action=f"feed.comment_{action}",
            target_type="comment",
            target_id=comment.pk,
            reason=reason,
            ip=ip,
        )
    return comment


# --- admin: the queue ---


def open_report_count() -> int:
    return Report.objects.filter(status=Report.Status.OPEN).count()


def queue(*, status: str, target_type: str, reason: str) -> QuerySet[Report]:
    """Oldest first, so the longest-waiting report is handled first."""
    queryset = Report.objects.all()
    if status:
        queryset = queryset.filter(status=status)
    if target_type:
        queryset = queryset.filter(target_type=target_type)
    if reason:
        queryset = queryset.filter(reason=reason)
    return queryset.order_by("created_at", "id")


def _state(row: Post | Comment | None) -> str:
    if row is None or row.deleted_at is not None:
        return "removed"
    return "hidden" if row.hidden_at is not None else "visible"


def report_views(viewer: Any, reports: list[Report]) -> list[dict[str, Any]]:
    """Reports with a short look at the thing reported, for the moderator to judge."""
    post_ids = [r.target_id for r in reports if r.target_type == "post"]
    comment_ids = [r.target_id for r in reports if r.target_type == "comment"]
    posts = Post.objects.in_bulk(post_ids)
    comments = Comment.objects.in_bulk(comment_ids)
    open_counts = {
        (row["target_type"], row["target_id"]): row["n"]
        for row in Report.objects.filter(
            status=Report.Status.OPEN, target_id__in=post_ids + comment_ids
        )
        .values("target_type", "target_id")
        .annotate(n=Count("id"))
    }
    people = {
        *(r.reporter_id for r in reports),
        *(p.author_id for p in posts.values()),
        *(c.author_id for c in comments.values()),
    }
    cards = profiles.cards_for(viewer, list(people))
    views = []
    for item in reports:
        target: Post | Comment | None
        post_id: UUID | None
        if item.target_type == "post":
            target = posts.get(item.target_id)
            excerpt = target.body_text[:EXCERPT] if target else ""
            post_id = item.target_id
        else:
            target = comments.get(item.target_id)
            excerpt = text_of(target.body)[:EXCERPT] if target else ""
            post_id = target.post_id if target else None
        views.append(
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
                "open_reports_on_target": open_counts.get((item.target_type, item.target_id), 0),
                "target": {
                    "type": item.target_type,
                    "id": item.target_id,
                    "post_id": post_id,
                    "state": _state(target),
                    "excerpt": excerpt,
                    "created_at": target.created_at if target else None,
                    "author": (
                        {"id": target.author_id, "name": cards[target.author_id]["name"]}
                        if target
                        else None
                    ),
                },
            }
        )
    return views


def _tell_reporters(reports: list[Report], outcome: str) -> None:
    for item in reports:
        domain_events.publish(
            events.ReportHandled(
                reporter_id=str(item.reporter_id), outcome=outcome, target_type=item.target_type
            )
        )


def get_report(report_id: UUID) -> Report:
    found = Report.objects.filter(pk=report_id).first()
    if found is None:
        raise exceptions.NotFound()
    return found


def review(*, actor: Any, report_id: UUID, note: str = "", ip: str = "") -> Report:
    """Mark a report as looked at, with no action needed."""
    with transaction.atomic():
        found = Report.objects.select_for_update().filter(pk=report_id).first()
        if found is None:
            raise exceptions.NotFound()
        if found.status == Report.Status.ACTIONED:
            raise AlreadyHandled()
        found.status = Report.Status.REVIEWED
        found.handled_by = actor
        found.handled_at = timezone.now()
        found.note = plain(note)
        found.save()
        _tell_reporters([found], "reviewed")
        analytics.track("report_actioned", actor_id=actor.pk, properties={"outcome": "reviewed"})
        audit.record(
            actor=actor,
            action="feed.report_reviewed",
            target_type="report",
            target_id=found.pk,
            reason=found.note,
            ip=ip,
        )
    return found


def act(*, actor: Any, report_id: UUID, action: str, note: str = "", ip: str = "") -> Report:
    """Hide or remove what was reported. Every open report about it is closed as actioned."""
    with transaction.atomic():
        found = Report.objects.select_for_update().filter(pk=report_id).first()
        if found is None:
            raise exceptions.NotFound()
        clean_note = plain(note)
        try:
            if found.target_type == "post":
                services.moderate_post(
                    actor=actor, post_id=found.target_id, action=action, reason=clean_note, ip=ip
                )
            else:
                moderate_comment(
                    actor=actor,
                    comment_id=found.target_id,
                    action=action,
                    reason=clean_note,
                    ip=ip,
                )
        except exceptions.NotFound:
            pass  # already removed by someone else; the report is still closed below
        now = timezone.now()
        closing = list(
            Report.objects.filter(target_type=found.target_type, target_id=found.target_id).exclude(
                status=Report.Status.ACTIONED
            )
        )
        _tell_reporters(closing, "actioned")
        analytics.track("report_actioned", actor_id=actor.pk, properties={"outcome": "actioned"})
        Report.objects.filter(target_type=found.target_type, target_id=found.target_id).exclude(
            status=Report.Status.ACTIONED
        ).update(
            status=Report.Status.ACTIONED,
            handled_by=actor,
            handled_at=now,
            note=clean_note,
            updated_at=now,
        )
        audit.record(
            actor=actor,
            action="feed.report_actioned",
            target_type="report",
            target_id=found.pk,
            after={"action": action},
            reason=clean_note,
            ip=ip,
        )
        found.refresh_from_db()
    return found
