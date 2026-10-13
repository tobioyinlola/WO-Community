"""Letting a mentor read a venture.

Access is explicit, named, time limited if the owner wants, read only, and revocable at once. A
mentor reads what the owner's own screens show (profile, score, plan, forecast, decks); they
cannot change anything. Nothing is shared with anyone who is not a listed mentor.
"""

from datetime import timedelta
from typing import Any
from uuid import UUID

from django.db.models import Q
from django.utils import timezone
from rest_framework import exceptions

from apps.audit import services as audit
from apps.core.errors import ConflictError
from apps.mentorship.selectors import listed
from apps.toolkit.ventures.models import Venture, VentureGrant

MAX_ACTIVE_GRANTS = 10


def _live() -> Q:
    return Q(revoked_at__isnull=True) & (
        Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now())
    )


def grant(
    *,
    venture: Venture,
    owner_id: UUID,
    mentor_id: UUID,
    can_comment: bool = False,
    expires_in_days: int | None = None,
) -> VentureGrant:
    if mentor_id == owner_id:
        raise exceptions.ValidationError({"mentor_id": ["You already have access."]})
    if not listed().filter(user_id=mentor_id).exists():
        raise exceptions.ValidationError({"mentor_id": ["Choose a mentor from the directory."]})
    live = VentureGrant.objects.filter(_live(), venture=venture)
    if live.filter(grantee_id=mentor_id).exists():
        raise ConflictError("This mentor already has access.", code="exists")
    if live.count() >= MAX_ACTIVE_GRANTS:
        raise ConflictError(f"At most {MAX_ACTIVE_GRANTS} people can have access.", code="limit")
    # An expired or revoked earlier grant to the same mentor is replaced by a new row.
    row = VentureGrant.objects.create(
        venture=venture,
        grantee_id=mentor_id,
        can_comment=can_comment,
        expires_at=timezone.now() + timedelta(days=expires_in_days) if expires_in_days else None,
    )
    audit.record(
        actor=None,
        action="toolkit.venture_access_granted",
        target_type="venture",
        target_id=venture.pk,
        after={"grantee": str(mentor_id), "expires_at": str(row.expires_at)},
    )
    return row


def revoke(*, venture: Venture, grant_id: UUID) -> None:
    row = VentureGrant.objects.filter(pk=grant_id, venture=venture, revoked_at__isnull=True).first()
    if row is None:
        raise exceptions.NotFound()
    row.revoked_at = timezone.now()
    row.save(update_fields=["revoked_at", "updated_at"])
    audit.record(
        actor=None,
        action="toolkit.venture_access_revoked",
        target_type="venture",
        target_id=venture.pk,
        after={"grantee": str(row.grantee_id)},
    )


def given(venture: Venture) -> list[dict[str, Any]]:
    """Live grants on a venture with the mentor's name, for the owner."""
    from apps.profiles import selectors as profiles

    rows = list(VentureGrant.objects.filter(_live(), venture=venture).order_by("-created_at"))
    out = []
    for r in rows:
        out.append(
            {
                "id": r.pk,
                "mentor_id": r.grantee_id,
                "name": profiles.full_name_of(r.grantee_id),
                "can_comment": r.can_comment,
                "expires_at": r.expires_at,
                "created_at": r.created_at,
            }
        )
    return out


def shared_with(user_id: UUID) -> list[dict[str, Any]]:
    """Ventures someone has opened to this member, newest first."""
    rows = (
        VentureGrant.objects.filter(_live(), grantee_id=user_id, venture__deleted_at__isnull=True)
        .select_related("venture")
        .order_by("-created_at")
    )
    return [
        {
            "venture_id": r.venture_id,
            "name": r.venture.name,
            "can_comment": r.can_comment,
            "expires_at": r.expires_at,
            "shared_at": r.created_at,
        }
        for r in rows
    ]
