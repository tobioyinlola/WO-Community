"""Reads for ventures. Ownership is decided here: other people's ventures do not exist."""

from typing import Any
from uuid import UUID

from django.db.models import Q, QuerySet
from django.utils import timezone

from apps.toolkit.ventures import schema
from apps.toolkit.ventures.models import OutputState, Venture, VentureGrant, VentureProfile


def mine(user_id: UUID) -> QuerySet[Venture]:
    return Venture.objects.filter(owner_id=user_id, deleted_at__isnull=True)


def owned(user_id: UUID, venture_id: UUID, *, include_deleted: bool = False) -> Venture | None:
    queryset = Venture.objects.filter(pk=venture_id, owner_id=user_id)
    if not include_deleted:
        queryset = queryset.filter(deleted_at__isnull=True)
    return queryset.first()


def readable(user_id: UUID, venture_id: UUID, *, comment: bool = False) -> Venture | None:
    """The venture if the person owns it, or holds a live grant that allows what they want."""
    venture = owned(user_id, venture_id)
    if venture is not None:
        return venture
    now = timezone.now()
    grants = VentureGrant.objects.filter(
        venture_id=venture_id, grantee_id=user_id, revoked_at__isnull=True
    ).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
    if comment:
        grants = grants.filter(can_comment=True)
    grant = grants.select_related("venture").first()
    if grant is None or grant.venture.deleted_at is not None:
        return None
    return grant.venture


def profile_of(venture: Venture) -> VentureProfile:
    return VentureProfile.objects.get(venture=venture)


def profile_view(venture: Venture) -> dict[str, Any]:
    profile = profile_of(venture)
    return {
        "version": profile.version,
        "fields": profile.fields,
        "field_meta": profile.field_meta,
        "completeness": venture.profile_completeness,
        "missing_required": schema.missing_required(profile.fields),
        "competitors": [
            {
                "id": c.pk,
                "name": c.name,
                "website": c.website,
                "differentiator": c.differentiator,
            }
            for c in venture.competitors.all()
        ],
        "team": [
            {
                "id": t.pk,
                "name": t.name,
                "role": t.role,
                "linkedin": t.linkedin,
                "is_founder": t.is_founder,
            }
            for t in venture.team.all()
        ],
    }


def outputs(venture: Venture) -> list[dict[str, Any]]:
    return [
        {
            "type": o.output_type,
            "id": o.output_id,
            "status": o.status,
            "stale_fields": o.stale_fields,
            "last_generated_at": o.last_generated_at,
        }
        for o in OutputState.objects.filter(venture=venture).order_by("output_type", "created_at")
    ]


def venture_view(venture: Venture) -> dict[str, Any]:
    return {
        "id": venture.pk,
        "name": venture.name,
        "status": venture.status,
        "profile_completeness": venture.profile_completeness,
        "imported_from_startup": venture.imported_from_startup_id,
        "nudges_enabled": venture.nudges_enabled,
        "created_at": venture.created_at,
        "updated_at": venture.updated_at,
        "deleted_at": venture.deleted_at,
    }


def package(venture: Venture) -> dict[str, Any]:
    """The venture's board: how complete it is and where each output stands."""
    profile = profile_of(venture)
    missing = schema.missing_required(profile.fields)
    states = outputs(venture)
    next_steps: list[str] = []
    if missing:
        next_steps.append("complete_required_fields")
    for state in states:
        if state["status"] == "needs_refresh":
            next_steps.append(f"refresh_{state['type']}")
    return {
        "venture": venture_view(venture),
        "completeness": venture.profile_completeness,
        "missing_required": missing,
        "ready_for_score": not missing,
        "outputs": states,
        "next_steps": next_steps,
    }


def versions(venture: Venture, limit: int = 50) -> list[dict[str, Any]]:
    return [
        {
            "version": v.version,
            "changed_fields": v.changed_fields,
            "actor": v.actor,
            "created_at": v.created_at,
        }
        for v in venture.profile_versions.all()[:limit]
    ]


def version_snapshot(venture: Venture, version: int) -> dict[str, Any] | None:
    row = venture.profile_versions.filter(version=version).first()
    return row.snapshot if row else None
