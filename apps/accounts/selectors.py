"""Read side of the accounts module for admin screens."""

from datetime import date
from typing import Any

from django.db.models import Q, QuerySet
from django.utils import timezone

from apps.accounts.models import Invitation, User, UserStatus

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
