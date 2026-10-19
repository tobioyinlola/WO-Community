"""Joining group chats, talking in them, and the admin's hand on them."""

import re
from typing import Any
from uuid import UUID

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import exceptions

from apps.audit import services as audit
from apps.core.text import plain
from apps.groups.models import MAX_MESSAGE, ChatGroup, GroupMember, GroupMessage, MessageReaction

# An emoji is one short run of symbols: no letters, digits, spaces or markup characters. This lets
# through skin tones, flags and joined emoji (👩🏾‍💻) and keeps out words passed off as reactions.
_EMOJI = re.compile(r"[^\w\s<>&\"'`]{1,16}")


class Conflict(exceptions.APIException):
    status_code = 409
    default_code = "conflict"


def _invalid(field: str, message: str) -> exceptions.ValidationError:
    return exceptions.ValidationError({field: [message]})


def clean_emoji(value: str, field: str = "emoji") -> str:
    value = value.strip()
    if not _EMOJI.fullmatch(value) or not any(ord(c) >= 0x2190 for c in value):
        raise _invalid(field, "Choose an emoji.")
    return value


def _open_group(group_id: UUID) -> ChatGroup:
    group = ChatGroup.objects.filter(pk=group_id, archived_at__isnull=True).first()
    if group is None:
        raise exceptions.NotFound()
    return group


def _membership(user_id: UUID, group_id: UUID) -> GroupMember:
    member = GroupMember.objects.filter(user_id=user_id, group_id=group_id).first()
    if member is None:
        raise exceptions.PermissionDenied("Join the group to take part.")
    return member


# --- members ---


def join(*, user_id: UUID, group_id: UUID) -> bool:
    """Join a group. Joining twice is fine; returns whether this call joined."""
    group = _open_group(group_id)
    _, created = GroupMember.objects.get_or_create(
        group=group, user_id=user_id, defaults={"last_read_at": timezone.now()}
    )
    return created


def leave(*, user_id: UUID, group_id: UUID) -> None:
    GroupMember.objects.filter(user_id=user_id, group_id=group_id).delete()


def mark_read(*, user_id: UUID, group_id: UUID) -> None:
    GroupMember.objects.filter(user_id=user_id, group_id=group_id).update(
        last_read_at=timezone.now()
    )


def send(*, user_id: UUID, group_id: UUID, body: str, reply_to: UUID | None = None) -> GroupMessage:
    group = _open_group(group_id)
    _membership(user_id, group.pk)
    text = plain(body)
    if not text:
        raise _invalid("body", "Write a message.")
    if len(text) > MAX_MESSAGE:
        raise _invalid("body", f"Up to {MAX_MESSAGE} characters.")
    parent = None
    if reply_to is not None:
        parent = GroupMessage.objects.filter(
            pk=reply_to, group=group, deleted_at__isnull=True
        ).first()
        if parent is None:
            raise _invalid("reply_to", "That message is not in this group any more.")
    message = GroupMessage.objects.create(
        group=group, author_id=user_id, body=text, reply_to=parent
    )
    mark_read(user_id=user_id, group_id=group.pk)
    return message


def _live_message(message_id: UUID) -> GroupMessage:
    message = (
        GroupMessage.objects.select_related("group")
        .filter(pk=message_id, deleted_at__isnull=True, group__archived_at__isnull=True)
        .first()
    )
    if message is None:
        raise exceptions.NotFound()
    return message


def delete_own(*, user_id: UUID, message_id: UUID) -> None:
    message = _live_message(message_id)
    if message.author_id != user_id:
        raise exceptions.PermissionDenied("You can only delete your own messages.")
    message.soft_delete()


def toggle_reaction(*, user_id: UUID, message_id: UUID, emoji: str) -> bool:
    """React with an emoji, or take the same reaction back. Returns whether it is now on."""
    message = _live_message(message_id)
    _membership(user_id, message.group_id)
    emoji = clean_emoji(emoji)
    existing = MessageReaction.objects.filter(message=message, user_id=user_id, emoji=emoji)
    if existing.exists():
        existing.delete()
        return False
    if MessageReaction.objects.filter(message=message, user_id=user_id).count() >= 12:
        raise _invalid("emoji", "That is enough reactions on one message.")
    try:
        with transaction.atomic():
            MessageReaction.objects.create(message=message, user_id=user_id, emoji=emoji)
    except IntegrityError:  # the same tap arrived twice
        pass
    return True


# --- admins ---


def _group_fields(data: dict[str, Any], group: ChatGroup) -> None:
    if "name" in data:
        name = plain(data["name"])[:60]
        if not name:
            raise _invalid("name", "Give the group a name.")
        clash = ChatGroup.objects.filter(name__iexact=name).exclude(pk=group.pk)
        if clash.exists():
            raise _invalid("name", "There is already a group with that name.")
        group.name = name
    if "description" in data:
        group.description = plain(data["description"])[:300]
    if "emoji" in data:
        group.emoji = clean_emoji(data["emoji"]) if str(data["emoji"]).strip() else ""
    if "sort" in data:
        group.sort = max(0, int(data["sort"]))
    if "archived" in data:
        if data["archived"] and group.archived_at is None:
            group.archived_at = timezone.now()
        elif not data["archived"]:
            group.archived_at = None


def create_group(*, actor: Any, data: dict[str, Any], ip: str = "") -> ChatGroup:
    group = ChatGroup(created_by=actor)
    if not str(data.get("name", "")).strip():
        raise _invalid("name", "Give the group a name.")
    _group_fields(data, group)
    if "sort" not in data:
        last = ChatGroup.objects.order_by("-sort").values_list("sort", flat=True).first()
        group.sort = (last or 0) + 1
    group.save()
    audit.record(
        actor=actor,
        action="groups.created",
        target_type="chat_group",
        target_id=group.pk,
        after={"name": group.name},
        ip=ip,
    )
    return group


def update_group(*, actor: Any, group_id: UUID, data: dict[str, Any], ip: str = "") -> ChatGroup:
    with transaction.atomic():
        group = ChatGroup.objects.select_for_update().filter(pk=group_id).first()
        if group is None:
            raise exceptions.NotFound()
        before = {"name": group.name, "archived": group.archived_at is not None}
        _group_fields(data, group)
        group.save()
        audit.record(
            actor=actor,
            action="groups.updated",
            target_type="chat_group",
            target_id=group.pk,
            before=before,
            after={"name": group.name, "archived": group.archived_at is not None},
            ip=ip,
        )
    return group


def remove_message(*, actor: Any, message_id: UUID, ip: str = "") -> None:
    """Take down a message that breaks the Code of Conduct. Kept, hidden, for the record."""
    message = GroupMessage.objects.filter(pk=message_id, deleted_at__isnull=True).first()
    if message is None:
        raise exceptions.NotFound()
    message.removed_by = actor
    message.deleted_at = timezone.now()
    message.save(update_fields=["removed_by", "deleted_at", "updated_at"])
    audit.record(
        actor=actor,
        action="groups.message_removed",
        target_type="group_message",
        target_id=message.pk,
        before={"group": str(message.group_id), "author": str(message.author_id)},
        ip=ip,
    )
