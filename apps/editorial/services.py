"""Public commands of the editorial module: stories, comments, reactions and win submissions."""

import secrets
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

import structlog
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from django.utils.text import slugify
from rest_framework import exceptions

from apps.analytics import services as analytics
from apps.audit import services as audit
from apps.core import etag, ratelimit
from apps.core import events as domain_events
from apps.core.text import clean_url, plain, rich_comment, rich_post, text_of
from apps.editorial import events
from apps.editorial.models import (
    ITEM_TYPES,
    REACTION_KINDS,
    EditorialItem,
    ItemComment,
    ItemReaction,
    ItemStartup,
    WinSubmission,
)
from apps.integrations.cdn import get_cache_purger
from apps.startups import selectors as startups
from apps.uploads import services as uploads

logger = structlog.get_logger(__name__)

MAX_BODY_TEXT = 20_000
MAX_COMMENT_TEXT = 1500
MAX_STARTUPS = 5
MAX_BANNER_DAYS = 90
COMMENTS_PER_DAY = 100
WINS_PER_DAY = 5
MAX_PENDING_WINS = 3
DAY = 24 * 3600
PUBLIC_API = "/api/v1/public/news"


class NotFound(exceptions.NotFound):
    default_detail = "Not found."


class Conflict(exceptions.APIException):
    status_code = 409
    default_code = "conflict"


def _invalid(field: str, message: str) -> exceptions.ValidationError:
    return exceptions.ValidationError({field: [message]})


def _purge_cdn(item: EditorialItem) -> None:
    try:
        get_cache_purger().purge([PUBLIC_API, f"{PUBLIC_API}/{item.slug}"])
    except Exception:  # public pages expire by themselves
        logger.warning("cdn_purge_failed", item_id=str(item.pk))


def _lock(item_id: UUID) -> EditorialItem:
    item = (
        EditorialItem.objects.select_for_update()
        .exclude(status=EditorialItem.Status.REMOVED)
        .filter(pk=item_id)
        .first()
    )
    if item is None:
        raise NotFound()
    return item


# --- writing stories ---


def _check_banner(item: EditorialItem) -> None:
    start, end = item.banner_starts_at, item.banner_ends_at
    if start is None and end is None:
        return
    if item.type != "announcement":
        raise _invalid("banner_ends_at", "Only announcements can be pinned as a banner.")
    if end is None:
        raise _invalid("banner_ends_at", "Say when the banner ends.")
    if start is not None and end <= start:
        raise _invalid("banner_ends_at", "The banner must end after it starts.")
    if end <= timezone.now():
        raise _invalid("banner_ends_at", "The banner must end in the future.")
    if end - (start or timezone.now()) > timedelta(days=MAX_BANNER_DAYS):
        raise _invalid("banner_ends_at", f"A banner can run for at most {MAX_BANNER_DAYS} days.")


def _apply(item: EditorialItem, data: dict[str, Any]) -> None:
    if "type" in data:
        if data["type"] not in ITEM_TYPES:
            raise _invalid("type", "Choose a type from the list.")
        item.type = data["type"]
    if "title" in data:
        item.title = plain(data["title"])
        if not item.title:
            raise _invalid("title", "This field may not be blank.")
    if "body" in data:
        item.body = rich_post(data["body"])
        item.body_text = text_of(item.body)
        if not item.body_text:
            raise _invalid("body", "This field may not be blank.")
        if len(item.body_text) > MAX_BODY_TEXT:
            raise _invalid("body", f"Up to {MAX_BODY_TEXT} characters.")
    if "external_url" in data:
        try:
            item.external_url = clean_url(data["external_url"])
        except exceptions.ValidationError as exc:
            raise _invalid("external_url", " ".join(str(m) for m in exc.detail)) from exc
    for field in ("comments_enabled", "public"):
        if field in data:
            setattr(item, field, bool(data[field]))
    for field in ("banner_starts_at", "banner_ends_at"):
        if field in data:
            setattr(item, field, data[field])


def _link_startups(item: EditorialItem, startup_ids: list[UUID]) -> None:
    unique = list(dict.fromkeys(startup_ids))
    if len(unique) > MAX_STARTUPS:
        raise _invalid("startup_ids", f"Link up to {MAX_STARTUPS} startups.")
    known = startups.existing_ids(unique)
    if set(unique) - known:
        raise _invalid("startup_ids", "Unknown startup.")
    item.startup_links.all().delete()
    ItemStartup.objects.bulk_create(
        ItemStartup(item=item, startup_id=sid, position=pos) for pos, sid in enumerate(unique)
    )


def create_item(*, actor: Any, data: dict[str, Any], ip: str = "") -> EditorialItem:
    item = EditorialItem(
        slug=f"{slugify(data.get('title', ''))[:70] or 'item'}-{secrets.token_hex(3)}",
        created_by=actor,
        status=EditorialItem.Status.DRAFT,
    )
    _apply(item, data)
    _check_banner(item)
    with transaction.atomic():
        item.save()
        _link_startups(item, data.get("startup_ids", []))
        audit.record(
            actor=actor,
            action="editorial.created",
            target_type="editorial",
            target_id=item.pk,
            ip=ip,
        )
    return item


def update_item(
    *, actor: Any, item_id: UUID, data: dict[str, Any], if_match: str | None, ip: str = ""
) -> EditorialItem:
    with transaction.atomic():
        item = _lock(item_id)
        etag.assert_matches(if_match, item)
        _apply(item, data)
        _check_banner(item)
        item.edited_at = timezone.now()
        item.save()
        if "startup_ids" in data:
            _link_startups(item, data["startup_ids"])
        audit.record(
            actor=actor,
            action="editorial.updated",
            target_type="editorial",
            target_id=item.pk,
            ip=ip,
        )
        if item.status == EditorialItem.Status.PUBLISHED:
            transaction.on_commit(lambda: _purge_cdn(item))
    return item


def set_cover(*, actor: Any, item_id: UUID, upload_id: UUID | None) -> EditorialItem:
    """Use a finished upload (purpose ``editorial_cover``) as the cover, or clear it."""
    with transaction.atomic():
        item = _lock(item_id)
        previous = item.cover_key
        if upload_id is None:
            item.cover_key = ""
        else:
            upload = uploads.claim(
                upload_id=upload_id, owner_id=actor.pk, purpose="editorial_cover"
            )
            item.cover_key = upload.base_key
        item.save(update_fields=["cover_key", "updated_at"])
        uploads.release(previous)
        if item.status == EditorialItem.Status.PUBLISHED:
            transaction.on_commit(lambda: _purge_cdn(item))
    return item


# --- publishing ---


def _go_live(item: EditorialItem, when: datetime) -> None:
    item.status = EditorialItem.Status.PUBLISHED
    item.published_at = when
    item.publish_at = None


def publish_now(*, actor: Any, item_id: UUID, ip: str = "") -> EditorialItem:
    with transaction.atomic():
        item = _lock(item_id)
        if item.status == EditorialItem.Status.PUBLISHED:
            raise Conflict("This item is already published.")
        _go_live(item, timezone.now())
        item.save()
        audit.record(
            actor=actor,
            action="editorial.published",
            target_type="editorial",
            target_id=item.pk,
            ip=ip,
        )
        domain_events.publish(events.ItemPublished(item_id=str(item.pk)))
        transaction.on_commit(lambda: _purge_cdn(item))
    return item


def schedule(*, actor: Any, item_id: UUID, publish_at: datetime, ip: str = "") -> EditorialItem:
    if publish_at <= timezone.now():
        raise _invalid("publish_at", "Choose a time in the future.")
    with transaction.atomic():
        item = _lock(item_id)
        if item.status == EditorialItem.Status.PUBLISHED:
            raise Conflict("This item is already published.")
        item.status, item.publish_at = EditorialItem.Status.SCHEDULED, publish_at
        item.save(update_fields=["status", "publish_at", "updated_at"])
        audit.record(
            actor=actor,
            action="editorial.scheduled",
            target_type="editorial",
            target_id=item.pk,
            after={"publish_at": publish_at.isoformat()},
            ip=ip,
        )
    return item


def unpublish(*, actor: Any, item_id: UUID, ip: str = "") -> EditorialItem:
    """Take a published item down, or cancel a schedule. It goes back to draft."""
    with transaction.atomic():
        item = _lock(item_id)
        if item.status not in (EditorialItem.Status.PUBLISHED, EditorialItem.Status.SCHEDULED):
            raise Conflict("Only a published or scheduled item can be taken down.")
        was_live = item.status == EditorialItem.Status.PUBLISHED
        item.status, item.publish_at = EditorialItem.Status.DRAFT, None
        item.save(update_fields=["status", "publish_at", "updated_at"])
        audit.record(
            actor=actor,
            action="editorial.unpublished",
            target_type="editorial",
            target_id=item.pk,
            ip=ip,
        )
        if was_live:
            transaction.on_commit(lambda: _purge_cdn(item))
    return item


def remove_item(*, actor: Any, item_id: UUID, ip: str = "") -> None:
    with transaction.atomic():
        item = _lock(item_id)
        was_live = item.status == EditorialItem.Status.PUBLISHED
        item.status = EditorialItem.Status.REMOVED
        item.save(update_fields=["status", "updated_at"])
        audit.record(
            actor=actor,
            action="editorial.removed",
            target_type="editorial",
            target_id=item.pk,
            ip=ip,
        )
        if was_live:
            transaction.on_commit(lambda: _purge_cdn(item))


def publish_due() -> int:
    """Publish scheduled items whose time has come, stamped with the time they were due."""
    due = list(
        EditorialItem.objects.filter(
            status=EditorialItem.Status.SCHEDULED, publish_at__lte=timezone.now()
        ).order_by("publish_at")
    )
    count = 0
    for candidate in due:
        with transaction.atomic():
            item = (
                EditorialItem.objects.select_for_update()
                .filter(pk=candidate.pk, status=EditorialItem.Status.SCHEDULED)
                .first()
            )
            if item is None or item.publish_at is None:
                continue
            _go_live(item, item.publish_at)
            item.save()
            domain_events.publish(events.ItemPublished(item_id=str(item.pk)))
            transaction.on_commit(lambda item=item: _purge_cdn(item))  # type: ignore[misc]
            count += 1
    return count


# --- comments ---


def _open_item(item_id: UUID) -> EditorialItem:
    item = (
        EditorialItem.objects.select_for_update()
        .filter(pk=item_id, status=EditorialItem.Status.PUBLISHED)
        .first()
    )
    if item is None:
        raise NotFound()
    return item


def add_comment(*, user_id: UUID, item_id: UUID, body: str) -> ItemComment:
    html = rich_comment(body)
    text = text_of(html)
    if not text:
        raise _invalid("body", "Write something first.")
    if len(text) > MAX_COMMENT_TEXT:
        raise _invalid("body", f"Comments can be up to {MAX_COMMENT_TEXT} characters.")
    if ratelimit.hit(f"editorial:comment:{user_id}", DAY) > COMMENTS_PER_DAY:
        raise exceptions.Throttled(wait=DAY, detail="Daily limit for comments reached.")
    with transaction.atomic():
        item = _open_item(item_id)
        if not item.comments_enabled:
            raise Conflict("Comments are switched off for this item.")
        comment = ItemComment.objects.create(item=item, author_id=user_id, body=html)
        EditorialItem.objects.filter(pk=item.pk).update(comment_count=F("comment_count") + 1)
        analytics.track("comment_created", actor_id=user_id)
    return comment


def _own_comment(user_id: UUID, comment_id: UUID) -> ItemComment:
    comment = (
        ItemComment.objects.select_for_update()
        .select_related("item")
        .filter(pk=comment_id, author_id=user_id, deleted_at__isnull=True)
        .first()
    )
    if comment is None or comment.item.status != EditorialItem.Status.PUBLISHED:
        raise NotFound()
    return comment


def update_comment(*, user_id: UUID, comment_id: UUID, body: str) -> ItemComment:
    html = rich_comment(body)
    text = text_of(html)
    if not text or len(text) > MAX_COMMENT_TEXT:
        raise _invalid("body", f"Write between 1 and {MAX_COMMENT_TEXT} characters.")
    with transaction.atomic():
        comment = _own_comment(user_id, comment_id)
        if comment.hidden_at is not None:
            raise Conflict("A moderator hid this comment, so it cannot be edited.")
        comment.body, comment.edited_at = html, timezone.now()
        comment.save()
    return comment


def recount_comments(item_id: UUID) -> None:
    visible = ItemComment.objects.filter(
        item_id=item_id, deleted_at__isnull=True, hidden_at__isnull=True
    ).count()
    EditorialItem.objects.filter(pk=item_id).update(comment_count=visible)


def delete_comment(*, user_id: UUID, comment_id: UUID) -> None:
    with transaction.atomic():
        comment = _own_comment(user_id, comment_id)
        comment.deleted_at = timezone.now()
        comment.save(update_fields=["deleted_at", "updated_at"])
        recount_comments(comment.item_id)


def moderate_comment(
    *, actor: Any, comment_id: UUID, action: str, reason: str = "", ip: str = ""
) -> ItemComment:
    """Hide, unhide or remove any comment, and say so in the audit log."""
    with transaction.atomic():
        comment = (
            ItemComment.objects.select_for_update()
            .filter(pk=comment_id, deleted_at__isnull=True)
            .first()
        )
        if comment is None:
            raise NotFound()
        now = timezone.now()
        if action == "hide":
            comment.hidden_at = now
        elif action == "unhide":
            comment.hidden_at = None
        elif action == "remove":
            comment.deleted_at = now
        else:
            raise ValueError(action)
        comment.save()
        recount_comments(comment.item_id)
        audit.record(
            actor=actor,
            action=f"editorial.comment_{action}",
            target_type="editorial_comment",
            target_id=comment.pk,
            reason=plain(reason),
            ip=ip,
        )
    return comment


# --- reactions ---


def react(*, user_id: UUID, item_id: UUID, kind: str) -> bool:
    if kind not in REACTION_KINDS:
        raise _invalid("kind", "Choose like, celebrate or insightful.")
    with transaction.atomic():
        item = _open_item(item_id)
        _, created = ItemReaction.objects.get_or_create(item=item, user_id=user_id, kind=kind)
        if created:
            _recount_reactions(item)
            analytics.track("post_reacted", actor_id=user_id, properties={"kind": kind})
    return created


def unreact(*, user_id: UUID, item_id: UUID, kind: str) -> bool:
    if kind not in REACTION_KINDS:
        raise _invalid("kind", "Choose like, celebrate or insightful.")
    with transaction.atomic():
        item = _open_item(item_id)
        removed, _ = ItemReaction.objects.filter(item=item, user_id=user_id, kind=kind).delete()
        if removed:
            _recount_reactions(item)
    return bool(removed)


def _recount_reactions(item: EditorialItem) -> None:
    counts: dict[str, int] = {}
    for kind in ItemReaction.objects.filter(item=item).values_list("kind", flat=True):
        counts[kind] = counts.get(kind, 0) + 1
    EditorialItem.objects.filter(pk=item.pk).update(
        reaction_counts=counts, reaction_count=sum(counts.values())
    )


# --- win submissions ---


def submit_win(*, user_id: UUID, data: dict[str, Any]) -> WinSubmission:
    try:
        evidence = clean_url(data["evidence_url"])
    except exceptions.ValidationError as exc:
        raise _invalid("evidence_url", " ".join(str(m) for m in exc.detail)) from exc
    if not evidence:
        raise _invalid("evidence_url", "Link to evidence of the win.")
    startup_id = data.get("startup_id")
    if startup_id is not None and startup_id not in startups.startup_ids_of_member(user_id):
        raise _invalid("startup_id", "You can only submit a win for a startup you belong to.")
    title = plain(data["title"])
    if not title:
        raise _invalid("title", "This field may not be blank.")
    with transaction.atomic():
        pending = WinSubmission.objects.select_for_update().filter(
            submitter_id=user_id, status=WinSubmission.Status.PENDING
        )
        if pending.count() >= MAX_PENDING_WINS:
            raise _invalid("title", "Wait for your earlier submissions to be reviewed first.")
        if ratelimit.hit(f"editorial:win:{user_id}", DAY) > WINS_PER_DAY:
            raise exceptions.Throttled(wait=DAY, detail="Daily limit for submissions reached.")
        win = WinSubmission.objects.create(
            submitter_id=user_id,
            startup_id=startup_id,
            kind=data["kind"],
            title=title,
            evidence_url=evidence,
            details=plain(data.get("details", "")),
        )
        analytics.track("win_submitted", actor_id=user_id, properties={"kind": win.kind})
    return win


def review_win(
    *, actor: Any, win_id: UUID, decision: str, note: str = "", ip: str = ""
) -> WinSubmission:
    """Approve (creating a draft story for an editor) or reject (with a reason) a win."""
    clean_note = plain(note)
    with transaction.atomic():
        win = WinSubmission.objects.select_for_update().filter(pk=win_id).first()
        if win is None:
            raise NotFound()
        if win.status != WinSubmission.Status.PENDING:
            raise Conflict("This submission has already been reviewed.")
        if decision == "reject" and not clean_note:
            raise _invalid("reason", "Say why the submission was not accepted.")
        win.reviewed_by, win.reviewed_at, win.review_note = actor, timezone.now(), clean_note
        if decision == "approve":
            win.status = WinSubmission.Status.APPROVED
            win.item = _draft_from_win(actor, win)
        else:
            win.status = WinSubmission.Status.REJECTED
        win.save()
        audit.record(
            actor=actor,
            action=f"editorial.win_{decision}",
            target_type="win_submission",
            target_id=win.pk,
            reason=clean_note,
            ip=ip,
        )
        domain_events.publish(
            events.WinReviewed(win_id=str(win.pk), approved=decision == "approve", note=clean_note)
        )
    return win


def _draft_from_win(actor: Any, win: WinSubmission) -> EditorialItem:
    details = win.details or win.title
    item = EditorialItem.objects.create(
        type=win.kind,
        slug=f"{slugify(win.title)[:70] or 'win'}-{secrets.token_hex(3)}",
        title=win.title,
        body=rich_post(f"<p>{plain(details)}</p>"),
        body_text=plain(details),
        external_url=win.evidence_url,
        created_by=actor,
        status=EditorialItem.Status.DRAFT,
    )
    if win.startup_id:
        ItemStartup.objects.create(item=item, startup_id=win.startup_id, position=0)
    return item
