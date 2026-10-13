"""Search across the console. Each group appears only for roles that hold its permission."""

from collections.abc import Callable
from typing import Any

from django.db.models import Q

from apps.accounts.models import User
from apps.core.rbac import permissions_for
from apps.events.models import Event
from apps.jobs.models import Job
from apps.learning.models import Course
from apps.profiles.models import FounderProfile
from apps.support.models import SupportTicket
from apps.toolkit.ventures.models import Venture


def _people(query: str, limit: int, *, pending_only: bool) -> list[dict[str, Any]]:
    """Accounts by email or by the name on their profile, pending ones included."""
    named = FounderProfile.objects.filter(full_name__icontains=query).values("user_id")
    rows = User.objects.filter(Q(email__icontains=query) | Q(pk__in=named))
    if pending_only:
        rows = rows.filter(status="pending")
    rows = rows.select_related("founder_profile").order_by("-created_at")[:limit]
    out = []
    for user in rows:
        profile = getattr(user, "founder_profile", None)
        name = (profile.full_name if profile else "") or user.email
        if pending_only:
            url = f"/admin/approvals?request={user.pk}"
        else:
            url = f"/admin/members?q={user.email}"
        out.append(
            {
                "type": "approval" if pending_only else "member",
                "id": user.pk,
                "title": name,
                "subtitle": user.email if name != user.email else user.status,
                "status": user.status,
                "url": url,
            }
        )
    return out


def _members(query: str, limit: int) -> list[dict[str, Any]]:
    return _people(query, limit, pending_only=False)


def _approvals(query: str, limit: int) -> list[dict[str, Any]]:
    return _people(query, limit, pending_only=True)


def _courses(query: str, limit: int) -> list[dict[str, Any]]:
    rows = Course.objects.exclude(status="removed").filter(
        Q(title__icontains=query) | Q(instructor__icontains=query) | Q(category__icontains=query)
    )
    return [
        {
            "type": "course",
            "id": c.pk,
            "title": c.title,
            "subtitle": f"{c.instructor}, {c.status}",
            "status": c.status,
            "url": f"/admin/courses?q={c.title}",
        }
        for c in rows.order_by("-created_at")[:limit]
    ]


def _jobs(query: str, limit: int) -> list[dict[str, Any]]:
    rows = Job.objects.filter(Q(title__icontains=query) | Q(organisation__icontains=query))
    return [
        {
            "type": "job",
            "id": j.pk,
            "title": j.title,
            "subtitle": f"{j.organisation or 'No organisation'}, {j.status}",
            "status": j.status,
            "url": f"/admin/jobs?q={j.title}",
        }
        for j in rows.order_by("-created_at")[:limit]
    ]


def _events(query: str, limit: int) -> list[dict[str, Any]]:
    rows = Event.objects.filter(title__icontains=query)
    return [
        {
            "type": "event",
            "id": e.pk,
            "title": e.title,
            "subtitle": e.status,
            "status": e.status,
            "url": f"/admin/events?q={e.title}",
        }
        for e in rows.order_by("-starts_at")[:limit]
    ]


def _tickets(query: str, limit: int) -> list[dict[str, Any]]:
    term = query.strip().lstrip("#")
    match = Q(subject__icontains=term) | Q(name__icontains=term) | Q(email__icontains=term)
    digits = term.upper().removeprefix("SUP-")
    if digits.isdigit():
        match |= Q(number=int(digits))
    return [
        {
            "type": "ticket",
            "id": t.pk,
            "title": f"{t.reference}: {t.subject}",
            "subtitle": f"{t.name}, {t.status.replace('_', ' ')}",
            "status": t.status,
            "url": f"/admin/support?ticket={t.pk}",
        }
        for t in SupportTicket.objects.filter(match).order_by("-last_activity_at")[:limit]
    ]


def _ventures(query: str, limit: int) -> list[dict[str, Any]]:
    rows = Venture.objects.filter(deleted_at__isnull=True, name__icontains=query)
    return [
        {
            "type": "venture",
            "id": v.pk,
            "title": v.name,
            "subtitle": v.status,
            "status": v.status,
            "url": "/admin/toolkit/ventures",
        }
        for v in rows.order_by("-created_at")[:limit]
    ]


# Group name, the permission that unlocks it, and how to search it.
GROUPS: dict[str, tuple[str, Callable[[str, int], list[dict[str, Any]]]]] = {
    "members": ("members.view", _members),
    "approvals": ("members.approve", _approvals),
    "courses": ("courses.manage", _courses),
    "jobs": ("jobs.moderate", _jobs),
    "events": ("events.manage", _events),
    "tickets": ("support.manage", _tickets),
    "ventures": ("toolkit.manage", _ventures),
}

# Groups added by later modules (support tickets) register themselves here.
EXTRA_GROUPS: dict[str, tuple[str, Callable[[str, int], list[dict[str, Any]]]]] = {}


def search(
    user: Any, query: str, kinds: list[str] | None, limit: int
) -> dict[str, list[dict[str, Any]]]:
    allowed = permissions_for(user.role_names())
    groups = {**GROUPS, **EXTRA_GROUPS}
    out: dict[str, list[dict[str, Any]]] = {}
    for name, (permission, find) in groups.items():
        if kinds and name not in kinds:
            continue
        if permission in allowed:
            out[name] = find(query, limit)
    return out
