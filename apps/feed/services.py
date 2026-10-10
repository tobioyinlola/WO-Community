"""Public commands of the feed: posting, commenting, reacting and moderating.

Reads live in ``selectors``. Everything that changes data goes through here, inside one
transaction, so a counter never disagrees with the rows it counts.
"""

from typing import Any
from uuid import UUID

import structlog
from django.conf import settings
from django.db import transaction
from django.db.models import F, Q, QuerySet
from django.utils import timezone
from rest_framework import exceptions

from apps.accounts import services as accounts
from apps.analytics import services as analytics
from apps.audit import services as audit
from apps.core import etag, ratelimit
from apps.core import events as domain_events
from apps.core.text import rich_comment, rich_post, text_of
from apps.feed import events, links
from apps.feed.models import (
    CATEGORIES,
    REACTION_KINDS,
    Comment,
    Post,
    PostImage,
    Reaction,
)
from apps.profiles import services as profiles
from apps.startups import selectors as startups
from apps.uploads import services as uploads

logger = structlog.get_logger(__name__)

MAX_POST_TEXT = 3000
MAX_COMMENT_TEXT = 1500
MAX_MENTIONS = 10
ENGAGEMENT_PER_COMMENT = 2
DAY = 24 * 3600


class NotFound(exceptions.NotFound):
    default_detail = "Not found."


class Forbidden(exceptions.PermissionDenied):
    default_detail = "You cannot change this."


# --- shared helpers ---


def spend(kind: str, user_id: UUID, limit: int) -> None:
    """Count an attempt against the member's daily allowance, or refuse it."""
    if ratelimit.hit(f"feed:{kind}:{user_id}", DAY) > limit:
        raise exceptions.Throttled(wait=DAY, detail=f"Daily limit for {kind}s reached.")


def _clean_post(body: str) -> tuple[str, str]:
    html = rich_post(body)
    text = text_of(html)
    if not text:
        raise exceptions.ValidationError({"body": ["Write something first."]})
    if len(text) > MAX_POST_TEXT:
        raise exceptions.ValidationError(
            {"body": [f"Posts can be up to {MAX_POST_TEXT} characters."]}
        )
    return html, text


def _clean_comment(body: str) -> str:
    html = rich_comment(body)
    text = text_of(html)
    if not text:
        raise exceptions.ValidationError({"body": ["Write something first."]})
    if len(text) > MAX_COMMENT_TEXT:
        raise exceptions.ValidationError(
            {"body": [f"Comments can be up to {MAX_COMMENT_TEXT} characters."]}
        )
    return html


def _live_posts() -> QuerySet[Post]:
    """Posts that exist and whose author may still post: removed members' posts vanish at once."""
    return Post.objects.filter(deleted_at__isnull=True, author_id__in=accounts.active_user_ids())


def _lock_post(post_id: UUID, *, open_to_all: bool = True) -> Post:
    """A post members can interact with: not removed, not hidden, author still active."""
    queryset = _live_posts().select_for_update()
    if open_to_all:
        queryset = queryset.filter(hidden_at__isnull=True)
    post = queryset.filter(pk=post_id).first()
    if post is None:
        raise NotFound()
    return post


def _mention(
    *, by: UUID, mentioned: list[UUID], target_type: str, target_id: UUID, post_id: UUID
) -> None:
    """Tell the people named in a post or comment. Only active members, never oneself."""
    for user_id in dict.fromkeys(accounts.filter_active(mentioned)):
        if user_id != by:
            domain_events.publish(
                events.MemberMentioned(
                    user_id=str(user_id),
                    by_user_id=str(by),
                    target_type=target_type,
                    target_id=str(target_id),
                    post_id=str(post_id),
                )
            )


def _check_mentions(mentions: list[UUID]) -> list[UUID]:
    unique = list(dict.fromkeys(mentions))
    if len(unique) > MAX_MENTIONS:
        raise exceptions.ValidationError(
            {"mentions": [f"You can mention up to {MAX_MENTIONS} people."]}
        )
    return unique


def _check_startup(user_id: UUID, startup_id: UUID | None) -> None:
    if startup_id is not None and startup_id not in startups.startup_ids_of_member(user_id):
        raise exceptions.ValidationError(
            {"startup_id": ["You can only post for a startup you belong to."]}
        )


# --- images ---


def _attach_images(post: Post, images: list[dict[str, Any]], user_id: UUID) -> list[str]:
    """Make the post's images match ``images``. Returns keys that are no longer used.

    Each entry either keeps an existing image (``image_id``) or adds a finished upload
    (``upload_id``); the list order is the display order.
    """
    if len(images) > settings.FEED_MAX_IMAGES:
        raise exceptions.ValidationError(
            {"images": [f"A post can have up to {settings.FEED_MAX_IMAGES} images."]}
        )
    existing = {img.pk: img for img in post.images.select_for_update()}
    kept = [i["image_id"] for i in images if i.get("image_id")]
    if len(set(kept)) != len(kept) or any(k not in existing for k in kept):
        raise exceptions.ValidationError({"images": ["Unknown or repeated image."]})
    uploads_used = [i["upload_id"] for i in images if i.get("upload_id")]
    if len(set(uploads_used)) != len(uploads_used):
        raise exceptions.ValidationError({"images": ["The same upload was used twice."]})

    # Move everything out of the way so positions can be reassigned without clashing.
    post.images.update(position=F("position") + 1000)
    released = [img.base_key for pk, img in existing.items() if pk not in set(kept)]
    PostImage.objects.filter(pk__in=[pk for pk in existing if pk not in set(kept)]).delete()
    for position, item in enumerate(images):
        alt = text_of(item.get("alt", ""))[:200]
        if item.get("image_id"):
            PostImage.objects.filter(pk=item["image_id"]).update(position=position, alt_text=alt)
        else:
            upload = uploads.claim(
                upload_id=item["upload_id"], owner_id=user_id, purpose="post_image"
            )
            PostImage.objects.create(
                post=post, base_key=upload.base_key, alt_text=alt, position=position
            )
    return released


# --- posts ---


def create_post(
    *,
    user_id: UUID,
    category: str,
    body: str,
    images: list[dict[str, Any]],
    startup_id: UUID | None = None,
    mentions: list[UUID] | None = None,
) -> Post:
    if category not in CATEGORIES:
        raise exceptions.ValidationError({"category": ["Choose a category from the list."]})
    html, text = _clean_post(body)
    mention_ids = _check_mentions(mentions or [])
    _check_startup(user_id, startup_id)
    spend("post", user_id, settings.FEED_POSTS_PER_DAY)
    with transaction.atomic():
        post = Post.objects.create(
            author_id=user_id,
            startup_id=startup_id,
            category=category,
            body=html,
            body_text=text,
            country=profiles.country_of(user_id),
        )
        _attach_images(post, images, user_id)
        links.sync(post, html)
        _mention(
            by=user_id,
            mentioned=mention_ids,
            target_type="post",
            target_id=post.pk,
            post_id=post.pk,
        )
        analytics.track("post_created", actor_id=user_id, properties={"category": category})
    return post


def update_post(
    *,
    user_id: UUID,
    post_id: UUID,
    if_match: str | None,
    changes: dict[str, Any],
) -> Post:
    """Edit your own post. Send only what changes; ``images`` replaces the whole list."""
    with transaction.atomic():
        post = _lock_post(post_id, open_to_all=False)
        if post.author_id != user_id:
            raise NotFound()  # someone else's post is not even confirmed to exist
        if post.hidden_at is not None:
            raise Forbidden("A moderator hid this post, so it cannot be edited.")
        etag.assert_matches(if_match, post)
        if "category" in changes:
            if changes["category"] not in CATEGORIES:
                raise exceptions.ValidationError({"category": ["Choose a category from the list."]})
            post.category = changes["category"]
        if "body" in changes:
            post.body, post.body_text = _clean_post(changes["body"])
            links.sync(post, post.body)
        released: list[str] = []
        if "images" in changes:
            released = _attach_images(post, changes["images"], user_id)
        post.edited_at = timezone.now()
        post.save()
        for key in released:
            uploads.release(key)
        if "mentions" in changes:
            _mention(
                by=user_id,
                mentioned=_check_mentions(changes["mentions"]),
                target_type="post",
                target_id=post.pk,
                post_id=post.pk,
            )
    return post


def delete_post(*, user_id: UUID, post_id: UUID) -> None:
    with transaction.atomic():
        post = _lock_post(post_id, open_to_all=False)
        if post.author_id != user_id:
            raise NotFound()
        _remove(post)


def _remove(post: Post) -> None:
    keys = list(post.images.values_list("base_key", flat=True))
    post.soft_delete()
    for key in keys:
        uploads.release(key)


# --- comments ---


def add_comment(
    *,
    user_id: UUID,
    post_id: UUID,
    body: str,
    parent_id: UUID | None = None,
    mentions: list[UUID] | None = None,
) -> Comment:
    html = _clean_comment(body)
    mention_ids = _check_mentions(mentions or [])
    spend("comment", user_id, settings.FEED_COMMENTS_PER_DAY)
    with transaction.atomic():
        post = _lock_post(post_id)
        parent = None
        if parent_id is not None:
            parent = Comment.objects.filter(
                pk=parent_id, post=post, parent__isnull=True, deleted_at__isnull=True
            ).first()
            if parent is None:
                raise exceptions.ValidationError(
                    {"parent_id": ["Reply to a comment on this post."]}
                )
        comment = Comment.objects.create(post=post, author_id=user_id, parent=parent, body=html)
        Post.objects.filter(pk=post.pk).update(
            comment_count=F("comment_count") + 1,
            engagement=F("engagement") + ENGAGEMENT_PER_COMMENT,
        )
        domain_events.publish(
            events.CommentAdded(
                comment_id=str(comment.pk),
                post_id=str(post.pk),
                commenter_id=str(user_id),
                post_author_id=str(post.author_id),
                parent_author_id=str(parent.author_id) if parent else "",
            )
        )
        _mention(
            by=user_id,
            mentioned=mention_ids,
            target_type="comment",
            target_id=comment.pk,
            post_id=post.pk,
        )
        analytics.track("comment_created", actor_id=user_id)
    return comment


def _own_comment(user_id: UUID, comment_id: UUID) -> Comment:
    comment = (
        Comment.objects.select_for_update()
        .filter(pk=comment_id, deleted_at__isnull=True, author_id=user_id)
        .select_related("post")
        .first()
    )
    if comment is None or comment.post.deleted_at is not None:
        raise NotFound()
    return comment


def update_comment(*, user_id: UUID, comment_id: UUID, body: str) -> Comment:
    html = _clean_comment(body)
    with transaction.atomic():
        comment = _own_comment(user_id, comment_id)
        if comment.hidden_at is not None:
            raise Forbidden("A moderator hid this comment, so it cannot be edited.")
        comment.body = html
        comment.edited_at = timezone.now()
        comment.save()
    return comment


def delete_comment(*, user_id: UUID, comment_id: UUID) -> None:
    with transaction.atomic():
        comment = _own_comment(user_id, comment_id)
        remove_comment(comment)
        recount(comment.post_id)


def remove_comment(comment: Comment) -> None:
    """Soft delete a comment and the replies under it. The caller then calls ``recount``."""
    ids = [
        comment.pk,
        *comment.replies.filter(deleted_at__isnull=True).values_list("pk", flat=True),
    ]
    Comment.objects.filter(pk__in=ids, deleted_at__isnull=True).update(deleted_at=timezone.now())


def recount(post_id: UUID) -> None:
    """Set the post's comment count to the comments readers can actually see.

    A reply under a hidden or removed comment is not visible, so it is not counted.
    """
    visible = (
        Comment.objects.filter(post_id=post_id, deleted_at__isnull=True, hidden_at__isnull=True)
        .filter(
            Q(parent__isnull=True)
            | Q(parent__deleted_at__isnull=True, parent__hidden_at__isnull=True)
        )
        .count()
    )
    Post.objects.filter(pk=post_id).update(
        comment_count=visible, engagement=F("reaction_count") + ENGAGEMENT_PER_COMMENT * visible
    )


# --- reactions ---


def _lock_target(target_type: str, target_id: UUID) -> Post | Comment:
    if target_type == Reaction.Target.POST:
        return _lock_post(target_id)
    comment = (
        Comment.objects.select_for_update(of=("self",))
        .select_related("post")
        .filter(
            pk=target_id,
            deleted_at__isnull=True,
            hidden_at__isnull=True,
            post__deleted_at__isnull=True,
            post__hidden_at__isnull=True,
            post__author_id__in=accounts.active_user_ids(),
            author_id__in=accounts.active_user_ids(),
        )
        .filter(
            Q(parent__isnull=True)
            | Q(parent__deleted_at__isnull=True, parent__hidden_at__isnull=True)
        )
        .first()
    )
    if comment is None:
        raise NotFound()
    return comment


def _apply_reaction(target: Post | Comment, kind: str, delta: int) -> None:
    counts = dict(target.reaction_counts)
    counts[kind] = max(counts.get(kind, 0) + delta, 0)
    if not counts[kind]:
        del counts[kind]
    target.reaction_counts = counts
    target.reaction_count = sum(counts.values())
    fields = ["reaction_counts", "reaction_count"]
    if isinstance(target, Post):
        target.engagement = target.reaction_count + ENGAGEMENT_PER_COMMENT * target.comment_count
        fields.append("engagement")
    # Counters are not an edit, so updated_at (and with it the ETag) is left alone.
    type(target).objects.filter(pk=target.pk).update(**{f: getattr(target, f) for f in fields})


def react(*, user_id: UUID, target_type: str, target_id: UUID, kind: str) -> bool:
    """Add a reaction. Returns False when the member had already reacted this way."""
    if kind not in REACTION_KINDS:
        raise exceptions.ValidationError({"kind": ["Choose like, celebrate or insightful."]})
    with transaction.atomic():
        target = _lock_target(target_type, target_id)
        _, created = Reaction.objects.get_or_create(
            target_type=target_type, target_id=target_id, user_id=user_id, kind=kind
        )
        if created:
            _apply_reaction(target, kind, +1)
            analytics.track("post_reacted", actor_id=user_id, properties={"kind": kind})
    return created


def unreact(*, user_id: UUID, target_type: str, target_id: UUID, kind: str) -> bool:
    """Take a reaction back. Returns False when there was nothing to take back."""
    if kind not in REACTION_KINDS:
        raise exceptions.ValidationError({"kind": ["Choose like, celebrate or insightful."]})
    with transaction.atomic():
        target = _lock_target(target_type, target_id)
        removed, _ = Reaction.objects.filter(
            target_type=target_type, target_id=target_id, user_id=user_id, kind=kind
        ).delete()
        if removed:
            _apply_reaction(target, kind, -1)
    return bool(removed)


# --- moderation ---


def moderate_post(
    *, actor: Any, post_id: UUID, action: str, reason: str = "", ip: str = ""
) -> Post:
    """Pin, feature, hide or remove any post, and say so in the audit log."""
    with transaction.atomic():
        post = Post.objects.select_for_update().filter(pk=post_id, deleted_at__isnull=True).first()
        if post is None:
            raise NotFound()
        now = timezone.now()
        if action in ("pin", "unpin"):
            post.pinned_at = now if action == "pin" else None
        elif action in ("feature", "unfeature"):
            post.featured_at = now if action == "feature" else None
        elif action in ("hide", "unhide"):
            post.hidden_at = now if action == "hide" else None
        elif action == "remove":
            _remove(post)
        else:
            raise ValueError(action)
        if action != "remove":
            post.save(update_fields=["pinned_at", "featured_at", "hidden_at", "updated_at"])
        audit.record(
            actor=actor,
            action=f"feed.post_{action}",
            target_type="post",
            target_id=post.pk,
            reason=reason,
            ip=ip,
        )
    return post
