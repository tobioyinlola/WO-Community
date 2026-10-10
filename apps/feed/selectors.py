"""Read side of the feed. Who may see what is decided here."""

from typing import Any
from uuid import UUID

from django.db.models import Q, QuerySet
from rest_framework import exceptions

from apps.accounts import services as accounts
from apps.core.keyset import paginate
from apps.feed import follows
from apps.feed.models import Comment, Follow, Post, Reaction
from apps.profiles import selectors as profiles
from apps.startups import selectors as startups
from apps.uploads import services as uploads

SORTS: dict[str, tuple[str, ...]] = {
    "newest": ("created_at", "id"),
    "engaged": ("engagement", "created_at", "id"),
}


def visible_posts(viewer: Any) -> QuerySet[Post]:
    """Posts the viewer may open: not removed, author still active, not hidden (own ones aside)."""
    return (
        Post.objects.filter(deleted_at__isnull=True, author_id__in=accounts.active_user_ids())
        .filter(Q(hidden_at__isnull=True) | Q(author_id=viewer.pk))
        .select_related()
        .prefetch_related("images", "links__preview")
    )


def _my_reactions(viewer: Any, target_type: str, ids: list[UUID]) -> dict[UUID, list[str]]:
    mine: dict[UUID, list[str]] = {}
    rows = Reaction.objects.filter(user_id=viewer.pk, target_type=target_type, target_id__in=ids)
    for target_id, kind in rows.order_by("kind").values_list("target_id", "kind"):
        mine.setdefault(target_id, []).append(kind)
    return mine


def _post_views(viewer: Any, posts: list[Post]) -> list[dict[str, Any]]:
    cards = profiles.cards_for(viewer, list({p.author_id for p in posts}))
    startup_cards = startups.cards_for(viewer, [p.startup_id for p in posts if p.startup_id])
    mine = _my_reactions(viewer, "post", [p.pk for p in posts])
    followed_members = follows.is_following(viewer.pk, Follow.Kind.MEMBER, list(cards))
    followed_startups = follows.is_following(viewer.pk, Follow.Kind.STARTUP, list(startup_cards))
    for uid, card in cards.items():
        card["following"] = uid in followed_members
    for sid, startup_card in startup_cards.items():
        startup_card["following"] = sid in followed_startups
    views = []
    for post in posts:
        is_mine = post.author_id == viewer.pk
        views.append(
            {
                "id": post.pk,
                "category": post.category,
                "body": post.body,
                "country": post.country,
                "author": cards[post.author_id],
                "startup": startup_cards.get(post.startup_id) if post.startup_id else None,
                "images": [
                    {"id": i.pk, "urls": uploads.image_urls(i.base_key), "alt": i.alt_text}
                    for i in post.images.all()
                ],
                "previews": [
                    {
                        "url": link.preview.url,
                        "title": link.preview.title,
                        "description": link.preview.description,
                        "site_name": link.preview.site_name,
                        "image": uploads.image_urls(link.preview.image_key),
                    }
                    for link in post.links.all()
                    if link.preview.status == "ready"
                ],
                "created_at": post.created_at,
                "edited_at": post.edited_at,
                "pinned": post.pinned_at is not None,
                "featured": post.featured_at is not None,
                "hidden": post.hidden_at is not None,
                "comment_count": post.comment_count,
                "reaction_count": post.reaction_count,
                "reactions": post.reaction_counts,
                "my_reactions": mine.get(post.pk, []),
                "mine": is_mine,
            }
        )
    return views


def feed(
    viewer: Any,
    *,
    sort: str,
    scope: str,
    category: str,
    country: str,
    cursor: str,
    limit: int,
) -> dict[str, Any]:
    """One page of the feed, plus the pinned posts on the first page of the shared feed."""
    queryset = visible_posts(viewer)
    if scope == "mine":
        queryset = queryset.filter(author_id=viewer.pk)
    else:
        queryset = queryset.filter(hidden_at__isnull=True)
    if scope == "following":
        queryset = queryset.filter(
            Q(author_id__in=follows.followed_ids(viewer.pk, Follow.Kind.MEMBER))
            | Q(startup_id__in=follows.followed_ids(viewer.pk, Follow.Kind.STARTUP))
        )
    if category:
        queryset = queryset.filter(category=category)
    if country:
        queryset = queryset.filter(country=country)
    pinned: list[Post] = []
    if scope == "all":
        if not cursor:
            pinned = list(queryset.filter(pinned_at__isnull=False).order_by("-pinned_at", "-id"))
        queryset = queryset.filter(pinned_at__isnull=True)
    rows, next_cursor = paginate(
        queryset, fields=SORTS[sort], sort=f"{scope}:{sort}", cursor=cursor, limit=limit
    )
    views = _post_views(viewer, pinned + rows)
    result: dict[str, Any] = {"results": views[len(pinned) :], "next_cursor": next_cursor}
    if scope == "all":
        result["pinned"] = views[: len(pinned)]
    return result


def get_post(viewer: Any, post_id: UUID) -> tuple[Post, dict[str, Any]]:
    post = visible_posts(viewer).filter(pk=post_id).first()
    if post is None:
        raise exceptions.NotFound()
    return post, _post_views(viewer, [post])[0]


def _live_comments(post: Post) -> QuerySet[Comment]:
    return Comment.objects.filter(
        post=post,
        deleted_at__isnull=True,
        hidden_at__isnull=True,
        author_id__in=accounts.active_user_ids(),
    )


def _comment_views(viewer: Any, comments: list[Comment]) -> dict[UUID, dict[str, Any]]:
    cards = profiles.cards_for(viewer, list({c.author_id for c in comments}))
    followed = follows.is_following(viewer.pk, Follow.Kind.MEMBER, list(cards))
    for uid, card in cards.items():
        card["following"] = uid in followed
    mine = _my_reactions(viewer, "comment", [c.pk for c in comments])
    return {
        c.pk: {
            "id": c.pk,
            "post_id": c.post_id,
            "parent_id": c.parent_id,
            "body": c.body,
            "author": cards[c.author_id],
            "created_at": c.created_at,
            "edited_at": c.edited_at,
            "reaction_count": c.reaction_count,
            "reactions": c.reaction_counts,
            "my_reactions": mine.get(c.pk, []),
            "mine": c.author_id == viewer.pk,
            "replies": [],
        }
        for c in comments
    }


def comments(viewer: Any, post_id: UUID, *, cursor: str, limit: int) -> dict[str, Any]:
    """Top-level comments oldest first, each with its replies."""
    post, _ = get_post(viewer, post_id)
    top, next_cursor = paginate(
        _live_comments(post).filter(parent__isnull=True),
        fields=("created_at", "id"),
        sort="comments",
        cursor=cursor,
        limit=limit,
        descending=False,
    )
    replies = list(
        _live_comments(post).filter(parent_id__in=[c.pk for c in top]).order_by("created_at", "id")
    )
    views = _comment_views(viewer, top + replies)
    for reply in replies:
        views[reply.parent_id]["replies"].append(views[reply.pk])  # type: ignore[index]
    return {"results": [views[c.pk] for c in top], "next_cursor": next_cursor}


def get_comment(viewer: Any, comment_id: UUID) -> dict[str, Any]:
    comment = (
        Comment.objects.filter(
            pk=comment_id,
            deleted_at__isnull=True,
            hidden_at__isnull=True,
            author_id__in=accounts.active_user_ids(),
        )
        .filter(
            Q(parent__isnull=True)
            | Q(parent__deleted_at__isnull=True, parent__hidden_at__isnull=True)
        )
        .select_related("post")
        .first()
    )
    if comment is None or not visible_posts(viewer).filter(pk=comment.post_id).exists():
        raise exceptions.NotFound()
    return _comment_views(viewer, [comment])[comment.pk]


def active_author_ids(since: Any) -> Any:
    """Members who posted or commented since the given moment."""
    posters = set(
        Post.objects.filter(created_at__gte=since, deleted_at__isnull=True).values_list(
            "author_id", flat=True
        )
    )
    commenters = set(
        Comment.objects.filter(created_at__gte=since, deleted_at__isnull=True).values_list(
            "author_id", flat=True
        )
    )
    return posters | commenters
