"""What members see of the group chats."""

from collections import defaultdict
from typing import Any
from uuid import UUID

from django.db.models import Count, F, Max, OuterRef, Q, Subquery
from rest_framework import exceptions

from apps.core.keyset import paginate
from apps.groups.models import ChatGroup, GroupMember, GroupMessage, MessageReaction
from apps.profiles import selectors as profiles

EXCERPT = 140


def _excerpt(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= EXCERPT else text[: EXCERPT - 1].rstrip() + "…"


def groups_for(viewer: Any) -> list[dict[str, Any]]:
    """The open groups, each with whether the viewer is in it and what they have not read."""
    mine = {m.group_id: m.last_read_at for m in GroupMember.objects.filter(user_id=viewer.pk)}
    live = Q(messages__deleted_at__isnull=True)
    groups = list(
        ChatGroup.objects.filter(archived_at__isnull=True)
        .annotate(
            member_count=Count("members", distinct=True),
            last_at=Max("messages__created_at", filter=live),
        )
        .order_by("sort", "name")
    )
    latest = {
        m.group_id: m
        for m in GroupMessage.objects.filter(
            pk__in=Subquery(
                GroupMessage.objects.filter(group_id=OuterRef("group_id"), deleted_at__isnull=True)
                .order_by("-created_at")
                .values("pk")[:1]
            ),
            group_id__in=[g.pk for g in groups],
        )
    }
    unread: dict[UUID, int] = {}
    for group_id, read_at in mine.items():
        rows = GroupMessage.objects.filter(group_id=group_id, deleted_at__isnull=True).exclude(
            author_id=viewer.pk
        )
        if read_at is not None:
            rows = rows.filter(created_at__gt=read_at)
        unread[group_id] = min(rows.count(), 99)
    cards = profiles.cards_for(viewer, list({m.author_id for m in latest.values()}))
    out = []
    for g in groups:
        last = latest.get(g.pk)
        out.append(
            {
                "id": g.pk,
                "name": g.name,
                "description": g.description,
                "emoji": g.emoji,
                "member_count": g.member_count,
                "joined": g.pk in mine,
                "unread": unread.get(g.pk, 0),
                "last_message": (
                    {
                        "author": cards[last.author_id]["name"],
                        "text": _excerpt(last.body),
                        "created_at": last.created_at,
                    }
                    if last and g.pk in mine
                    else None
                ),
                "last_activity_at": g.last_at,
            }
        )
    return out


def group_for(viewer: Any, group_id: UUID) -> dict[str, Any]:
    for group in groups_for(viewer):
        if group["id"] == group_id:
            return group
    raise exceptions.NotFound()


def _reactions(viewer: Any, ids: list[UUID]) -> dict[UUID, list[dict[str, Any]]]:
    tally: dict[UUID, dict[str, dict[str, Any]]] = defaultdict(dict)
    rows = MessageReaction.objects.filter(message_id__in=ids).order_by("created_at")
    for message_id, emoji, user_id in rows.values_list("message_id", "emoji", "user_id"):
        entry = tally[message_id].setdefault(emoji, {"emoji": emoji, "count": 0, "mine": False})
        entry["count"] += 1
        entry["mine"] = entry["mine"] or user_id == viewer.pk
    return {k: list(v.values()) for k, v in tally.items()}


def messages(
    viewer: Any, group_id: UUID, *, cursor: str = "", limit: int = 50, moderator: bool = False
) -> dict[str, Any]:
    """The latest messages, oldest first, and a cursor for the page before them.

    Members must have joined; a moderator reads any group, archived ones too, without joining."""
    groups = ChatGroup.objects.filter(pk=group_id)
    if not moderator:
        groups = groups.filter(archived_at__isnull=True)
    if not groups.exists():
        raise exceptions.NotFound()
    joined = GroupMember.objects.filter(group_id=group_id, user_id=viewer.pk).exists()
    if not moderator and not joined:
        raise exceptions.PermissionDenied("Join the group to read the conversation.")
    queryset = GroupMessage.objects.filter(group_id=group_id).select_related("reply_to")
    rows, older = paginate(
        queryset, fields=("created_at", "id"), sort="recent", cursor=cursor, limit=limit
    )
    rows.reverse()
    return {"results": _items(viewer, rows), "older": older}


def message_for(viewer: Any, message_id: UUID) -> dict[str, Any]:
    row = GroupMessage.objects.select_related("reply_to").filter(pk=message_id).first()
    if row is None:
        raise exceptions.NotFound()
    return _items(viewer, [row])[0]


def reactions_for(viewer: Any, message_id: UUID) -> list[dict[str, Any]]:
    return _reactions(viewer, [message_id]).get(message_id, [])


def _items(viewer: Any, rows: list[GroupMessage]) -> list[dict[str, Any]]:
    people = {m.author_id for m in rows} | {m.reply_to.author_id for m in rows if m.reply_to}
    cards = profiles.cards_for(viewer, list(people))
    reactions = _reactions(viewer, [m.pk for m in rows if m.deleted_at is None])
    items = []
    for m in rows:
        gone = m.deleted_at is not None
        parent = m.reply_to
        items.append(
            {
                "id": m.pk,
                "author": cards[m.author_id],
                "body": "" if gone else m.body,
                "deleted": gone,
                "removed": gone and m.removed_by_id is not None,
                "mine": m.author_id == viewer.pk,
                "created_at": m.created_at,
                "reply_to": (
                    {
                        "id": parent.pk,
                        "author": cards[parent.author_id]["name"],
                        "text": "" if parent.deleted_at else _excerpt(parent.body),
                        "deleted": parent.deleted_at is not None,
                    }
                    if parent
                    else None
                ),
                "reactions": [] if gone else reactions.get(m.pk, []),
            }
        )
    return items


def admin_groups() -> list[dict[str, Any]]:
    rows = ChatGroup.objects.annotate(
        member_count=Count("members", distinct=True),
        message_count=Count("messages", filter=Q(messages__deleted_at__isnull=True), distinct=True),
        last_at=Max("messages__created_at"),
    ).order_by(F("archived_at").asc(nulls_first=True), "sort", "name")
    return [
        {
            "id": g.pk,
            "name": g.name,
            "description": g.description,
            "emoji": g.emoji,
            "sort": g.sort,
            "archived": g.archived_at is not None,
            "member_count": g.member_count,
            "message_count": g.message_count,
            "last_activity_at": g.last_at,
            "created_at": g.created_at,
        }
        for g in rows
    ]
