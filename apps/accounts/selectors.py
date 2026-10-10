"""Read side of the accounts module for admin screens."""

from datetime import date, timedelta
from typing import Any

from django.db.models import Count, OuterRef, Q, QuerySet, Subquery
from django.db.models.functions import TruncDate
from django.utils import timezone

from apps.accounts.models import (
    ConsentDocument,
    ConsentRecord,
    Invitation,
    User,
    UserRole,
    UserStatus,
)

STATUSES = tuple(UserStatus.values)


def _base() -> QuerySet[User]:
    return User.objects.prefetch_related("user_roles")


def list_members(
    *,
    q: str = "",
    status: str = "",
    role: str = "",
    email_verified: bool | None = None,
    joined_after: date | None = None,
    joined_before: date | None = None,
) -> QuerySet[User]:
    """Members matching an allow-listed set of filters, newest first."""
    queryset = _base()
    if q:
        queryset = queryset.filter(Q(email__icontains=q))
    if status:
        queryset = queryset.filter(status=status)
    if role:
        queryset = queryset.filter(user_roles__role=role)
    if email_verified is True:
        queryset = queryset.filter(email_verified_at__isnull=False)
    elif email_verified is False:
        queryset = queryset.filter(email_verified_at__isnull=True)
    if joined_after:
        queryset = queryset.filter(created_at__date__gte=joined_after)
    if joined_before:
        queryset = queryset.filter(created_at__date__lte=joined_before)
    return queryset.order_by("-created_at", "-id")


def get_member(user_id: Any) -> User | None:
    return _base().filter(pk=user_id).first()


def registration_queue_counts() -> dict[str, int]:
    pending = User.objects.filter(status=UserStatus.PENDING)
    return {
        "registrations_awaiting_approval": pending.filter(email_verified_at__isnull=False).count(),
        "registrations_unverified": pending.filter(email_verified_at__isnull=True).count(),
    }


INVITATION_STATUSES = ("sent", "opened", "registered", "revoked", "expired")


def list_invitations(*, q: str = "", status: str = "") -> QuerySet[Invitation]:
    """Invitations newest first. ``expired`` means unused and past its expiry."""
    queryset = Invitation.objects.select_related("invited_by")
    if q:
        queryset = queryset.filter(email__icontains=q)
    open_states = ["sent", "opened"]
    now = timezone.now()
    if status == "expired":
        queryset = queryset.filter(status__in=open_states, expires_at__lte=now)
    elif status in open_states:
        queryset = queryset.filter(status=status, expires_at__gt=now)
    elif status:
        queryset = queryset.filter(status=status)
    return queryset.order_by("-created_at", "-id")


def get_invitation(invitation_id: Any) -> Invitation | None:
    return Invitation.objects.select_related("invited_by").filter(pk=invitation_id).first()


def active_user_ids() -> QuerySet[Any]:
    """Ids of active members, as a subquery other modules can filter on.

    Public pages check this at read time so a suspended or removed member
    disappears at once, without waiting for any background refresh.
    """
    return User.objects.filter(status=UserStatus.ACTIVE).values("id")


def marketing_audience() -> QuerySet[User]:
    """Active members with a verified address whose latest marketing consent is a yes."""
    latest = (
        ConsentRecord.objects.filter(user=OuterRef("pk"), document=ConsentDocument.MARKETING)
        .order_by("-created_at", "-id")
        .values("granted")[:1]
    )
    return User.objects.annotate(marketing_granted=Subquery(latest)).filter(
        marketing_granted=True, status=UserStatus.ACTIVE, email_verified_at__isnull=False
    )


def ids_joined(after: Any = None, before: Any = None) -> QuerySet[Any]:
    queryset = User.objects.all()
    if after is not None:
        queryset = queryset.filter(created_at__date__gte=after)
    if before is not None:
        queryset = queryset.filter(created_at__date__lte=before)
    return queryset.values_list("pk", flat=True)


def ids_with_roles(roles: list[str]) -> QuerySet[Any]:
    return UserRole.objects.filter(role__in=roles).values_list("user_id", flat=True)


def ids_last_active(after: Any = None, before: Any = None) -> QuerySet[Any]:
    queryset = User.objects.filter(last_login__isnull=False)
    if after is not None:
        queryset = queryset.filter(last_login__date__gte=after)
    if before is not None:
        queryset = queryset.filter(last_login__date__lte=before)
    return queryset.values_list("pk", flat=True)


def active_members() -> QuerySet[User]:
    return User.objects.filter(status=UserStatus.ACTIVE, email_verified_at__isnull=False)


def registrations_by_day(start: Any, end: Any) -> dict[Any, int]:
    """New accounts per day in [start, end)."""
    rows = (
        User.objects.filter(created_at__gte=start, created_at__lt=end)
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(n=Count("id"))
    )
    return {row["day"]: row["n"] for row in rows}


def member_numbers(now: Any) -> dict[str, int]:
    return {
        "active": User.objects.filter(status=UserStatus.ACTIVE).count(),
        "pending": User.objects.filter(status=UserStatus.PENDING).count(),
        "registered_30d": User.objects.filter(created_at__gte=now - timedelta(days=30)).count(),
        "registered_7d": User.objects.filter(created_at__gte=now - timedelta(days=7)).count(),
    }


def retention(now: Any, days: int) -> float | None:
    """Of members approved at least ``days`` ago, the share who logged in during the last ``days``.

    None while nobody is old enough to measure.
    """
    cohort = User.objects.filter(
        status=UserStatus.ACTIVE,
        approved_at__isnull=False,
        approved_at__lte=now - timedelta(days=days),
    )
    total = cohort.count()
    if not total:
        return None
    kept = cohort.filter(last_login__gte=now - timedelta(days=days)).count()
    return round(kept / total, 4)
