"""The member's notification centre: listing, polling support and marking as read."""

import hashlib
from datetime import timedelta
from typing import Any
from uuid import UUID

from django.db.models import Count, Max, Q
from django.utils import timezone

from apps.core.keyset import paginate
from apps.notifications import notify
from apps.notifications.models import Notification

READ_RETENTION = timedelta(days=90)
ANY_RETENTION = timedelta(days=180)


def unread_count(user_id: UUID) -> int:
    return Notification.objects.filter(user_id=user_id, read_at__isnull=True).count()


def fingerprint(user_id: UUID, *, unread_only: bool, cursor: str, limit: int) -> str:
    """Changes whenever the list a client would see could have changed.

    One cheap aggregate over the member's own rows: how many exist, how many are unread and when
    one last changed. A poll that finds the same fingerprint gets a 304 and no body.
    """
    stats = Notification.objects.filter(user_id=user_id).aggregate(
        total=Count("id"),
        unread=Count("id", filter=Q(read_at__isnull=True)),
        last=Max("updated_at"),
    )
    parts = [user_id, stats["total"], stats["unread"], stats["last"], unread_only, cursor, limit]
    raw = "|".join(str(part) for part in parts)
    return f'"{hashlib.sha256(raw.encode()).hexdigest()[:32]}"'


def page(user_id: UUID, *, unread_only: bool, cursor: str, limit: int) -> dict[str, Any]:
    queryset = Notification.objects.filter(user_id=user_id)
    if unread_only:
        queryset = queryset.filter(read_at__isnull=True)
    rows, next_cursor = paginate(
        queryset,
        fields=("created_at", "id"),
        sort=f"notifications:{unread_only}",
        cursor=cursor,
        limit=limit,
    )
    return {
        "results": notify.render(user_id, rows),
        "next_cursor": next_cursor,
        "unread_count": unread_count(user_id),
    }


def mark_read(user_id: UUID, *, ids: list[UUID] | None, everything: bool) -> int:
    """Mark some or all of the member's own notifications as read. Others' ids are ignored."""
    queryset = Notification.objects.filter(user_id=user_id, read_at__isnull=True)
    if not everything:
        queryset = queryset.filter(pk__in=ids or [])
    now = timezone.now()
    return queryset.update(read_at=now, updated_at=now)


def purge_old() -> int:
    """Delete read notifications after 90 days and any after 180."""
    now = timezone.now()
    old = Notification.objects.filter(
        Q(read_at__isnull=False, created_at__lt=now - READ_RETENTION)
        | Q(created_at__lt=now - ANY_RETENTION)
    )
    deleted, _ = old.delete()
    return deleted
