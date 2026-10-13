"""Keeping each day's audit head hash where nobody can change it.

The audit log is a hash chain, so altering a row breaks every hash after it, but someone with
write access to the database could rewrite the whole day consistently. The daily head hash is
therefore also written to a bucket with object lock: once there it cannot be replaced or deleted
for years, even by us. A day's chain that no longer ends in its anchored head has been rewritten.
"""

import json
from datetime import date, timedelta

import structlog
from django.conf import settings
from django.utils import timezone

from apps.audit import services as audit
from apps.integrations.storage import ANCHOR, get_storage

logger = structlog.get_logger(__name__)


def key_for(day: date) -> str:
    return f"audit-anchors/{day.isoformat()}.json"


def anchor_day(day: date) -> str:
    """Write the day's head. Returns ``stored``, ``exists`` (same head already there),
    ``empty`` (nothing happened that day) or ``mismatch`` (an anchor exists with another head)."""
    head = audit.head_of(day)
    if head is None:
        return "empty"
    body = json.dumps(head, sort_keys=True).encode()
    storage = get_storage()
    if storage.write_once(
        bucket=ANCHOR,
        key=key_for(day),
        data=body,
        content_type="application/json",
        retain_days=settings.AUDIT_ANCHOR_RETENTION_DAYS,
    ):
        return "stored"
    return "exists" if verify_anchor(day) else "mismatch"


def verify_anchor(day: date) -> bool:
    """Whether the day's chain still ends where it did when it was anchored.

    A day with no anchor passes (it may predate anchoring); a missing anchor for a day that has
    entries older than the verification window is not an error here.
    """
    storage = get_storage()
    info = storage.head(bucket=ANCHOR, key=key_for(day))
    if info is None:
        return True
    anchored = json.loads(storage.read(bucket=ANCHOR, key=key_for(day), max_size=10_000))
    current = audit.head_of(day)
    # Entries may be added to a day only while it is the current day; an anchored day is closed,
    # so any difference at all means rows were added, removed or rewritten.
    return current is not None and current == anchored


def anchor_previous_day() -> dict[str, object]:
    """Verify yesterday's chain, anchor it, and re-check the recent anchors."""
    yesterday = timezone.now().date() - timedelta(days=1)
    chain_ok = audit.verify_day(yesterday)
    outcome = "chain_broken"
    if chain_ok:  # a broken chain is never anchored: the evidence would be locked in as wrong
        outcome = anchor_day(yesterday)
    mismatched = []
    for back in range(1, settings.AUDIT_ANCHOR_VERIFY_DAYS + 1):
        day = yesterday - timedelta(days=back)
        if not verify_anchor(day):
            mismatched.append(day.isoformat())
    if outcome in ("chain_broken", "mismatch") or mismatched:
        logger.error(
            "audit_anchor_problem",
            day=yesterday.isoformat(),
            outcome=outcome,
            mismatched_days=mismatched,
        )
    return {"day": yesterday.isoformat(), "outcome": outcome, "mismatched": mismatched}
