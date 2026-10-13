"""Reading the audit log: filters, groups of actions and the before and after diff."""

from datetime import datetime
from typing import Any

from django.db.models import Q, QuerySet

from apps.accounts.models import User
from apps.audit.models import AuditLog

# The filter groups on the page: a group matches every action that starts with one of its prefixes.
ACTION_GROUPS: dict[str, tuple[str, ...]] = {
    "members": ("member.", "members.", "role.", "invitation.", "referral."),
    "content": ("feed.", "editorial.", "news.", "announcement.", "post."),
    "jobs": ("jobs.", "job."),
    "events": ("events.",),
    "courses": ("courses.", "learning."),
    "certificates": ("certificates.",),
    "settings": ("settings.", "reference.", "email.", "campaigns."),
    "security": ("auth.", "mfa.", "audit.", "login", "consent."),
}


def _group_filter(groups: list[str], actions: list[str]) -> Q:
    q = Q()
    for name in groups:
        for prefix in ACTION_GROUPS.get(name, ()):
            q |= Q(action__startswith=prefix)
    if actions:
        q |= Q(action__in=actions)
    return q


def entries(
    *,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    actor: str = "",
    groups: list[str] | None = None,
    actions: list[str] | None = None,
    outcome: str = "",
    q: str = "",
    target_type: str = "",
    target_id: str = "",
) -> QuerySet[AuditLog]:
    rows = AuditLog.objects.all()
    if date_from:
        rows = rows.filter(created_at__gte=date_from)
    if date_to:
        rows = rows.filter(created_at__lt=date_to)
    if outcome:
        rows = rows.filter(outcome=outcome)
    if target_type:
        rows = rows.filter(target_type=target_type)
    if target_id:
        rows = rows.filter(target_id=target_id)
    if actor:
        ids = User.objects.filter(
            Q(email__icontains=actor) | Q(founder_profile__full_name__icontains=actor)
        ).values_list("pk", flat=True)[:200]
        rows = rows.filter(actor_id__in=list(ids))
    if groups or actions:
        rows = rows.filter(_group_filter(groups or [], actions or []))
    if q:
        rows = rows.filter(
            Q(target_label__icontains=q) | Q(action__icontains=q) | Q(target_id__icontains=q)
        )
    return rows


def changes(before: Any, after: Any) -> list[dict[str, Any]]:
    """A readable list of ``{field, before, after}`` for the fields that differ."""
    old = before if isinstance(before, dict) else {}
    new = after if isinstance(after, dict) else {}
    if not old and not new and (before is not None or after is not None):
        return [{"field": "value", "before": before, "after": after}]
    return [
        {"field": key, "before": old.get(key), "after": new.get(key)}
        for key in sorted(set(old) | set(new))
        if old.get(key) != new.get(key)
    ]
