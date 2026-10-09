"""Public entry points of the audit module: ``record`` and ``verify_day``."""

import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from typing import Any

import structlog
from django.db import connection, transaction
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.core.ids import uuid7

logger = structlog.get_logger(__name__)

HASHED_FIELDS = (
    "id",
    "created_at",
    "seq",
    "actor_id",
    "actor_roles",
    "action",
    "target_type",
    "target_id",
    "before",
    "after",
    "reason",
    "ip_hash",
    "user_agent_hash",
)


def hash_value(value: str) -> str:
    """One way hash for IP addresses and user agents; raw values are never stored."""
    return hashlib.sha256(value.encode()).hexdigest() if value else ""


def _entry_hash(prev_hash: str, fields: dict[str, Any]) -> str:
    canonical = json.dumps(fields, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(f"{prev_hash}|{canonical}".encode()).hexdigest()


def _fields_of(row: AuditLog) -> dict[str, Any]:
    data = {name: getattr(row, name) for name in HASHED_FIELDS}
    data["id"] = str(row.id)
    data["actor_id"] = str(row.actor_id) if row.actor_id else None
    data["created_at"] = row.created_at.isoformat()
    return data


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime(day.year, day.month, day.day, tzinfo=UTC)
    return start, start + timedelta(days=1)


def record(
    *,
    actor: Any,
    action: str,
    target_type: str = "",
    target_id: Any = "",
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    reason: str = "",
    ip: str = "",
    user_agent: str = "",
) -> AuditLog:
    """Append an entry. Call inside the transaction that makes the change."""
    with transaction.atomic():
        now = timezone.now()
        day_key = now.date().isoformat()
        with connection.cursor() as cursor:
            # One writer per day keeps the chain linear.
            cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", [f"audit:{day_key}"])
            cursor.execute("SELECT nextval('audit_auditlog_seq')")
            seq = cursor.fetchone()[0]
        start, end = _day_bounds(now.date())
        previous = (
            AuditLog.objects.filter(created_at__gte=start, created_at__lt=end)
            .order_by("-seq")
            .values_list("hash", flat=True)
            .first()
        )
        prev_hash = previous or ""
        entry = AuditLog(
            id=uuid7(),
            created_at=now,
            seq=seq,
            actor_id=getattr(actor, "pk", None),
            actor_roles=sorted(actor.role_names()) if hasattr(actor, "role_names") else [],
            action=action,
            target_type=target_type,
            target_id=str(target_id) if target_id else "",
            before=before,
            after=after,
            reason=reason,
            ip_hash=hash_value(ip),
            user_agent_hash=hash_value(user_agent),
            prev_hash=prev_hash,
        )
        entry.hash = _entry_hash(prev_hash, _fields_of(entry))
        entry.save(force_insert=True)
        return entry


def verify_day(day: date) -> bool:
    """Recompute the day's chain. False means a row was altered, removed or reordered."""
    start, end = _day_bounds(day)
    prev_hash = ""
    for row in AuditLog.objects.filter(created_at__gte=start, created_at__lt=end).order_by("seq"):
        if row.prev_hash != prev_hash or row.hash != _entry_hash(prev_hash, _fields_of(row)):
            logger.error("audit_chain_broken", day=day.isoformat(), seq=row.seq)
            return False
        prev_hash = row.hash
    return True
