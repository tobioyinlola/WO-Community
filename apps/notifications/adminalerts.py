"""Telling admins that something needs their approval, without flooding them.

``raise_alert`` records one item that needs approval. Each admin who may approve that kind of
item gets an email at once for the first item, then at most one digest every 15 minutes for the
ones that follow. Every email has one button that opens the item. An admin can switch each kind
off in their own notification settings.

An item is recorded once however often it is raised (its ``item_key`` is unique), which is what
makes a retried event harmless.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import structlog
from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts import selectors as account_selectors
from apps.accounts import services as accounts
from apps.core import events as domain_events
from apps.core.rbac import PERMISSIONS_BY_ROLE, Role
from apps.notifications import emails, notify
from apps.notifications import events as notification_events
from apps.notifications.models import AdminAlert, AdminAlertCursor, AdminAlertPreference

logger = structlog.get_logger(__name__)

WINDOW = timedelta(minutes=15)
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


@dataclass(frozen=True)
class Kind:
    key: str
    label: str
    permission: str
    page: str  # where the whole list lives, for a digest


KINDS: dict[str, Kind] = {
    k.key: k
    for k in (
        Kind("member_signup", "New member requests", "members.approve", "/admin/approvals"),
        Kind("job_pending", "Jobs to review", "jobs.moderate", "/admin/jobs?tab=pending"),
        Kind("mentor_application", "Mentor applications", "mentors.decide", "/admin/mentors"),
        Kind("course_access", "Course access requests", "courses.manage", "/admin/courses"),
        Kind("content_report", "Reported content", "reports.handle", "/admin/reports"),
        Kind("support_ticket", "New support requests", "support.manage", "/admin/support"),
    )
}


def _roles_with(permission: str) -> list[str]:
    return [r.value for r in Role if permission in PERMISSIONS_BY_ROLE[r]]


def recipients(kind: str) -> list[UUID]:
    """Active admins who may approve this kind of item and have not switched it off."""
    spec = KINDS[kind]
    ids = list(account_selectors.ids_with_roles(_roles_with(spec.permission)).distinct())
    off = set(
        AdminAlertPreference.objects.filter(user_id__in=ids, kind=kind, enabled=False).values_list(
            "user_id", flat=True
        )
    )
    return [UUID(str(i)) for i in ids if i not in off and accounts.is_active(UUID(str(i)))]


def raise_alert(
    kind: str,
    *,
    item_key: str,
    what: str,
    who: str,
    path: str = "",
    in_app: bool = True,
) -> bool:
    """Record an item needing approval. Returns False if it was already recorded."""
    spec = KINDS[kind]
    try:
        with transaction.atomic():
            alert = AdminAlert.objects.create(
                kind=kind,
                item_key=item_key[:120],
                what=what[:200],
                who=who[:200],
                path=(path or spec.page)[:300],
                in_app=in_app,
            )
            domain_events.publish(notification_events.AdminAlertRaised(alert_id=str(alert.pk)))
    except IntegrityError:
        return False
    return True


# --- delivery (runs in a worker) ---


def _app(path: str) -> str:
    return f"{settings.FRONTEND_BASE_URL}{path}"


def settings_url() -> str:
    return _app("/admin/settings?section=notifications")


def deliver_in_app(alert_id: UUID) -> int:
    """The in-app notification for a new item, for each admin who wants this kind."""
    alert = AdminAlert.objects.filter(pk=alert_id).first()
    if alert is None or not alert.in_app:
        return 0
    sent = 0
    for user_id in recipients(alert.kind):
        made = notify.notify(
            user_id,
            "admin_attention",
            {"what": alert.what, "who": alert.who, "path": alert.path},
            dedupe_key=f"admin-alert:{alert.pk}",
        )
        sent += int(made is not None)
    return sent


def dispatch(kind: str, *, now: datetime | None = None) -> int:
    """Email the admins about items they have not been told about, within the 15 minute rule.

    Safe to run any number of times: each admin's cursor remembers what they were told, and a
    row lock stops two workers sending the same email.
    """
    now = now or timezone.now()
    sent = 0
    spec = KINDS[kind]
    for user_id in recipients(kind):
        contact = accounts.get_contact(user_id)
        if contact is None:
            continue
        with transaction.atomic():
            cursor, _ = AdminAlertCursor.objects.get_or_create(
                user_id=user_id, kind=kind, defaults={"covered_until": EPOCH}
            )
            cursor = AdminAlertCursor.objects.select_for_update().get(pk=cursor.pk)
            unsent = list(
                AdminAlert.objects.filter(kind=kind, created_at__gt=cursor.covered_until).order_by(
                    "created_at"
                )[:50]
            )
            if not unsent:
                continue
            if cursor.last_sent_at and now - cursor.last_sent_at < WINDOW:
                continue  # inside the window: wait for the digest
            if len(unsent) == 1:
                item = unsent[0]
                emails.send_templated(
                    contact.email,
                    "admin_approval_needed",
                    {
                        "what": item.what,
                        "who": item.who,
                        "review_url": _app(item.path),
                        "settings_url": settings_url(),
                    },
                    category="admin_approval",
                )
            else:
                emails.send_templated(
                    contact.email,
                    "admin_approval_digest",
                    {
                        "count": len(unsent),
                        "kind": spec.label,
                        "items": "\n".join(f"{a.what} ({a.who})" for a in unsent[:20]),
                        "review_url": _app(spec.page),
                        "settings_url": settings_url(),
                    },
                    category="admin_approval_digest",
                )
            cursor.last_sent_at = now
            cursor.covered_until = unsent[-1].created_at
            cursor.save(update_fields=["last_sent_at", "covered_until", "updated_at"])
            sent += 1
    return sent


def dispatch_all() -> int:
    """The scheduled sweep that sends digests whose 15 minutes are up."""
    return sum(dispatch(kind) for kind in KINDS)


# --- each admin's own switches ---


def preferences_for(user: Any) -> list[dict[str, Any]]:
    """The kinds this admin may receive, each with whether it is on."""
    allowed = set(user.role_names())
    from apps.core.rbac import permissions_for

    codes = permissions_for(allowed)
    off = set(
        AdminAlertPreference.objects.filter(user_id=user.pk, enabled=False).values_list(
            "kind", flat=True
        )
    )
    return [
        {"kind": k.key, "label": k.label, "enabled": k.key not in off}
        for k in KINDS.values()
        if k.permission in codes
    ]


def set_preference(user: Any, kind: str, enabled: bool) -> None:
    from apps.core.rbac import permissions_for

    spec = KINDS.get(kind)
    if spec is None or spec.permission not in permissions_for(set(user.role_names())):
        raise KeyError(kind)
    AdminAlertPreference.objects.update_or_create(
        user_id=user.pk, kind=kind, defaults={"enabled": enabled}
    )
