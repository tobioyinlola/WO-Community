"""Reading support requests: a member's own, and the inbox admins work from."""

from datetime import date, datetime, timedelta
from statistics import median
from typing import Any
from uuid import UUID

from django.db.models import Count, Q, QuerySet
from django.utils import timezone

from apps.profiles.models import FounderProfile
from apps.support import domain, services
from apps.support.models import SupportAttachment, SupportCannedReply, SupportMessage, SupportTicket
from apps.uploads import services as uploads

ADMIN_ORDERINGS = (
    "number",
    "-number",
    "created_at",
    "-created_at",
    "last_activity_at",
    "-last_activity_at",
    "status",
    "-status",
    "category",
    "-category",
)


# --- a member's own ---


def member_tickets(user_id: UUID, status: str = "") -> QuerySet[SupportTicket]:
    rows = SupportTicket.objects.filter(member_id=user_id)
    if status == "open":
        rows = rows.exclude(status="resolved")
    elif status:
        rows = rows.filter(status=status)
    return rows.order_by("-last_activity_at", "-id")


def member_ticket(user_id: UUID, ticket_id: UUID) -> SupportTicket | None:
    return SupportTicket.objects.filter(pk=ticket_id, member_id=user_id).first()


def can_reopen(ticket: SupportTicket, now: datetime | None = None) -> bool:
    if ticket.status != "resolved" or ticket.resolved_at is None:
        return False
    return (now or timezone.now()) - ticket.resolved_at <= timedelta(days=domain.REOPEN_DAYS)


# --- the thread ---


def messages(ticket: SupportTicket, *, include_internal: bool) -> list[SupportMessage]:
    rows = ticket.messages.select_related("author", "author__founder_profile").prefetch_related(
        "attachments"
    )
    if not include_internal:
        rows = rows.filter(is_internal=False)
    return list(rows)


def author_card(message: SupportMessage) -> dict[str, Any]:
    """Who wrote a message. Support staff are shown by name with a flag, so a member knows."""
    user = message.author
    profile: FounderProfile | None = getattr(user, "founder_profile", None) if user else None
    name = (profile.full_name if profile else "") or ""
    if message.author_type == "admin":
        name = name or "WO Community support"
    elif not name:
        name = message.ticket.name
    return {
        "id": user.pk if user else None,
        "name": name,
        "is_support": message.author_type == "admin",
        "avatar": uploads.image_urls(profile.photo_key) if profile and profile.photo_key else None,
    }


def attachment(attachment_id: UUID) -> SupportAttachment | None:
    return (
        SupportAttachment.objects.select_related("message", "message__ticket")
        .filter(pk=attachment_id)
        .first()
    )


# --- the admin inbox ---


def admin_tickets(
    *,
    q: str = "",
    status: str = "",
    category: str = "",
    priority: str = "",
    assignee: str = "",
    created_after: date | None = None,
    created_before: date | None = None,
    ordering: str = "-last_activity_at",
    me: UUID | None = None,
) -> QuerySet[SupportTicket]:
    rows = SupportTicket.objects.select_related(
        "member", "member__founder_profile", "assignee", "assignee__founder_profile"
    )
    if status == "working":  # everything not resolved
        rows = rows.exclude(status="resolved")
    elif status:
        rows = rows.filter(status=status)
    if category:
        rows = rows.filter(category=category)
    if priority:
        rows = rows.filter(priority=priority)
    if assignee == "unassigned":
        rows = rows.filter(assignee__isnull=True)
    elif assignee == "me" and me:
        rows = rows.filter(assignee_id=me)
    elif assignee:
        rows = rows.filter(assignee_id=UUID(assignee))
    if created_after:
        rows = rows.filter(created_at__date__gte=created_after)
    if created_before:
        rows = rows.filter(created_at__date__lte=created_before)
    if q:
        term = q.strip().lstrip("#")
        match = Q(subject__icontains=term) | Q(name__icontains=term) | Q(email__icontains=term)
        digits = term.upper().removeprefix("SUP-")
        if digits.isdigit():
            match |= Q(number=int(digits))
        rows = rows.filter(match)
    return rows.order_by(ordering, "-id")


def counts() -> dict[str, int]:
    """For the tabs: how many requests are in each state."""
    week = timezone.now() - timedelta(days=7)
    c = SupportTicket.objects.aggregate(
        open=Count("id", filter=Q(status="open")),
        in_progress=Count("id", filter=Q(status="in_progress")),
        awaiting_member=Count("id", filter=Q(status="awaiting_member")),
        resolved=Count("id", filter=Q(status="resolved")),
        resolved_this_week=Count("id", filter=Q(status="resolved", resolved_at__gte=week)),
        total=Count("id"),
    )
    c["working"] = c["open"] + c["in_progress"] + c["awaiting_member"]
    return c


def median_first_response_seconds(days: int = 30) -> int | None:
    since = timezone.now() - timedelta(days=days)
    pairs = SupportTicket.objects.filter(first_response_at__gte=since).values_list(
        "created_at", "first_response_at"
    )
    waits = [(answered - created).total_seconds() for created, answered in pairs if answered]
    return int(median(waits)) if waits else None


def overdue_count() -> int:
    """Requests nobody has answered after the service level."""
    cutoff = timezone.now() - timedelta(hours=services.sla_hours())
    return SupportTicket.objects.filter(
        status="open", first_response_at__isnull=True, created_at__lt=cutoff
    ).count()


def unanswered_count() -> int:
    return SupportTicket.objects.filter(status="open", first_response_at__isnull=True).count()


def previous_count(ticket: SupportTicket) -> int:
    if ticket.member_id is None:
        return (
            SupportTicket.objects.filter(email__iexact=ticket.email).exclude(pk=ticket.pk).count()
        )
    return SupportTicket.objects.filter(member_id=ticket.member_id).exclude(pk=ticket.pk).count()


def canned(category: str = "", *, active_only: bool = True) -> QuerySet[SupportCannedReply]:
    rows = SupportCannedReply.objects.all()
    if active_only:
        rows = rows.filter(active=True)
    if category:
        rows = rows.filter(Q(category="") | Q(category=category))
    return rows
