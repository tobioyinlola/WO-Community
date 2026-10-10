"""Read side of the editorial module."""

from typing import Any
from uuid import UUID

from django.conf import settings
from django.db.models import Q, QuerySet
from django.utils import timezone
from rest_framework import exceptions

from apps.accounts import services as accounts
from apps.core.keyset import paginate
from apps.editorial.models import (
    EditorialItem,
    ItemComment,
    ItemReaction,
    WinSubmission,
)
from apps.profiles import selectors as profiles
from apps.startups import selectors as startups
from apps.uploads import services as uploads

EXCERPT = 200


def published() -> QuerySet[EditorialItem]:
    return EditorialItem.objects.filter(status=EditorialItem.Status.PUBLISHED)


def _excerpt(item: EditorialItem) -> str:
    text = item.body_text
    return text if len(text) <= EXCERPT else text[: EXCERPT - 1] + "…"


def _my_reactions(user_id: UUID, ids: list[UUID]) -> dict[UUID, list[str]]:
    mine: dict[UUID, list[str]] = {}
    rows = ItemReaction.objects.filter(user_id=user_id, item_id__in=ids).order_by("kind")
    for item_id, kind in rows.values_list("item_id", "kind"):
        mine.setdefault(item_id, []).append(kind)
    return mine


def _views(viewer: Any, items: list[EditorialItem]) -> list[dict[str, Any]]:
    links = {i.pk: list(i.startup_links.all()) for i in items}
    ids = [link.startup_id for row in links.values() for link in row]
    cards = startups.cards_for(viewer, ids)
    mine = _my_reactions(viewer.pk, [i.pk for i in items]) if viewer is not None else {}
    views = []
    for item in items:
        views.append(
            {
                "id": item.pk,
                "slug": item.slug,
                "type": item.type,
                "title": item.title,
                "excerpt": _excerpt(item),
                "body": item.body,
                "cover": uploads.image_urls(item.cover_key),
                "startups": [
                    cards[link.startup_id] for link in links[item.pk] if link.startup_id in cards
                ],
                "external_url": item.external_url,
                "comments_enabled": item.comments_enabled,
                "published_at": item.published_at,
                "comment_count": item.comment_count,
                "reaction_count": item.reaction_count,
                "reactions": item.reaction_counts,
                "my_reactions": mine.get(item.pk, []),
            }
        )
    return views


def feed(viewer: Any, *, type: str, cursor: str, limit: int) -> dict[str, Any]:  # noqa: A002
    queryset = published().prefetch_related("startup_links")
    if type:
        queryset = queryset.filter(type=type)
    rows, next_cursor = paginate(
        queryset,
        fields=("published_at", "id"),
        sort=f"editorial:{type}",
        cursor=cursor,
        limit=limit,
    )
    return {"results": _views(viewer, rows), "next_cursor": next_cursor}


def get_item(viewer: Any, item_id: UUID) -> tuple[EditorialItem, dict[str, Any]]:
    item = published().prefetch_related("startup_links").filter(pk=item_id).first()
    if item is None:
        raise exceptions.NotFound()
    return item, _views(viewer, [item])[0]


def banners() -> list[dict[str, Any]]:
    """Announcements whose banner window is open now, soonest to end first."""
    now = timezone.now()
    rows = (
        published()
        .filter(type="announcement", banner_ends_at__gt=now)
        .filter(Q(banner_starts_at__isnull=True) | Q(banner_starts_at__lte=now))
        .order_by("banner_ends_at", "id")[:5]
    )
    return [
        {
            "id": i.pk,
            "slug": i.slug,
            "title": i.title,
            "excerpt": _excerpt(i),
            "external_url": i.external_url,
            "ends_at": i.banner_ends_at,
        }
        for i in rows
    ]


# --- comments ---


def _comment_views(viewer: Any, comments: list[ItemComment]) -> list[dict[str, Any]]:
    cards = profiles.cards_for(viewer, list({c.author_id for c in comments}))
    return [
        {
            "id": c.pk,
            "item_id": c.item_id,
            "body": c.body,
            "author": cards[c.author_id],
            "created_at": c.created_at,
            "edited_at": c.edited_at,
            "mine": c.author_id == viewer.pk,
        }
        for c in comments
    ]


def comments(viewer: Any, item_id: UUID, *, cursor: str, limit: int) -> dict[str, Any]:
    get_item(viewer, item_id)
    queryset = ItemComment.objects.filter(
        item_id=item_id,
        deleted_at__isnull=True,
        hidden_at__isnull=True,
        author_id__in=accounts.active_user_ids(),
    )
    rows, next_cursor = paginate(
        queryset,
        fields=("created_at", "id"),
        sort="editorial-comments",
        cursor=cursor,
        limit=limit,
        descending=False,
    )
    return {"results": _comment_views(viewer, rows), "next_cursor": next_cursor}


def get_comment(viewer: Any, comment_id: UUID) -> dict[str, Any]:
    comment = ItemComment.objects.filter(
        pk=comment_id,
        deleted_at__isnull=True,
        hidden_at__isnull=True,
        item__status=EditorialItem.Status.PUBLISHED,
    ).first()
    if comment is None:
        raise exceptions.NotFound()
    return _comment_views(viewer, [comment])[0]


# --- wins ---


def win_view(win: WinSubmission) -> dict[str, Any]:
    return {
        "id": win.pk,
        "kind": win.kind,
        "title": win.title,
        "evidence_url": win.evidence_url,
        "details": win.details,
        "startup_id": win.startup_id,
        "status": win.status,
        "review_note": win.review_note,
        "created_at": win.created_at,
        "reviewed_at": win.reviewed_at,
    }


def my_wins(user_id: UUID, *, cursor: str, limit: int) -> dict[str, Any]:
    rows, next_cursor = paginate(
        WinSubmission.objects.filter(submitter_id=user_id),
        fields=("created_at", "id"),
        sort="wins-mine",
        cursor=cursor,
        limit=limit,
    )
    return {"results": [win_view(w) for w in rows], "next_cursor": next_cursor}


# --- public ---


def _public_queryset() -> QuerySet[EditorialItem]:
    return published().filter(public=True)


def _public_summary(view: dict[str, Any]) -> dict[str, Any]:
    return {k: view[k] for k in ("slug", "type", "title", "excerpt", "cover", "published_at")}


def public_feed(*, type: str, cursor: str, limit: int) -> dict[str, Any]:  # noqa: A002
    queryset = _public_queryset().prefetch_related("startup_links")
    if type:
        queryset = queryset.filter(type=type)
    rows, next_cursor = paginate(
        queryset,
        fields=("published_at", "id"),
        sort=f"public-news:{type}",
        cursor=cursor,
        limit=limit,
    )
    return {"results": [_public_summary(v) for v in _views(None, rows)], "next_cursor": next_cursor}


def public_detail(slug: str) -> dict[str, Any]:
    item = _public_queryset().prefetch_related("startup_links").filter(slug=slug).first()
    if item is None:
        raise exceptions.NotFound()
    view = _views(None, [item])[0]
    cover = view["cover"]
    url = f"{settings.FRONTEND_BASE_URL}/news/{item.slug}"
    return {
        **_public_summary(view),
        "body": view["body"],
        "startups": view["startups"],
        "external_url": view["external_url"],
        "share_url": url,
        "open_graph": {
            "title": item.title,
            "description": view["excerpt"],
            "url": url,
            "type": "article",
            "image": cover["large"] if cover else None,
        },
    }


# --- admin ---


def pending_wins() -> int:
    return WinSubmission.objects.filter(status=WinSubmission.Status.PENDING).count()


def admin_queryset(*, status: str, type: str, q: str) -> QuerySet[EditorialItem]:  # noqa: A002
    queryset = EditorialItem.objects.exclude(status=EditorialItem.Status.REMOVED)
    if status:
        queryset = queryset.filter(status=status)
    if type:
        queryset = queryset.filter(type=type)
    if q:
        queryset = queryset.filter(title__icontains=q)
    return queryset.order_by("-created_at", "-id")


def admin_views(actor: Any, items: list[EditorialItem]) -> list[dict[str, Any]]:
    views = _views(actor, items)
    for item, view in zip(items, views, strict=True):
        view.update(
            status=item.status,
            public=item.public,
            publish_at=item.publish_at,
            banner_starts_at=item.banner_starts_at,
            banner_ends_at=item.banner_ends_at,
            created_by=item.created_by_id,
            created_at=item.created_at,
            edited_at=item.edited_at,
        )
    return views


def admin_win_queryset(*, status: str) -> QuerySet[WinSubmission]:
    queryset = WinSubmission.objects.all()
    if status:
        queryset = queryset.filter(status=status)
    return queryset.order_by("created_at", "id")


def admin_win_views(wins: list[WinSubmission]) -> list[dict[str, Any]]:
    return [
        {
            **win_view(w),
            "submitter_id": w.submitter_id,
            "item_id": w.item_id,
            "reviewed_by": w.reviewed_by_id,
        }
        for w in wins
    ]
