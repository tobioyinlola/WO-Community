"""The mentor's own profile, pausing, and revoking or restoring mentor status."""

from typing import Any
from uuid import UUID

from django.db import transaction
from django.utils import timezone
from rest_framework import exceptions

from apps.accounts import services as accounts
from apps.audit import services as audit
from apps.core import events as domain_events
from apps.mentorship import domain, events
from apps.mentorship.applications import Conflict, Forbidden, NotFound
from apps.mentorship.models import MentorProfile

PROFILE_REQUIRED = (
    "expertise",
    "years_experience",
    "current_role",
    "company",
    "industries",
    "stages",
    "languages",
    "timezone",
)


def _fields(data: dict[str, Any]) -> dict[str, Any]:
    out = domain.clean_fields(data)
    if "about" in data:
        out["about"] = domain.text("about", data["about"], limit=domain.MAX_ABOUT, minimum=0)
    if "capacity_per_week" in data:
        out["capacity_per_week"] = domain.capacity(data["capacity_per_week"])
    if "session_minutes" in data:
        out["session_minutes"] = domain.session_minutes(data["session_minutes"])
    if "paused" in data:
        out["paused"] = bool(data["paused"])
    return out


def save_profile(*, user_id: UUID, data: dict[str, Any]) -> MentorProfile:
    """Change your mentor section. A mentor who joined by invitation creates it the first time."""
    fields = _fields(data)
    with transaction.atomic():
        profile = MentorProfile.objects.select_for_update().filter(user_id=user_id).first()
        if profile is None:
            if not accounts.has_role(user_id, "mentor"):
                raise Forbidden("You are not a mentor.")
            missing = {f: ["This field is required."] for f in PROFILE_REQUIRED if f not in fields}
            if missing:
                raise exceptions.ValidationError(missing)
            return MentorProfile.objects.create(
                user_id=user_id, approved_at=timezone.now(), **fields
            )
        if profile.status != MentorProfile.Status.ACTIVE:
            raise Forbidden("Your mentor status was withdrawn.")
        for name, value in fields.items():
            setattr(profile, name, value)
        profile.save()
    return profile


def own(user_id: UUID) -> MentorProfile:
    profile = MentorProfile.objects.filter(user_id=user_id).first()
    if profile is None:
        raise NotFound()
    return profile


# --- admin ---


def revoke(*, actor: Any, user_id: UUID, reason: str, ip: str = "") -> MentorProfile:
    """Withdraw mentor status: the badge, the listing and the role go; history stays."""
    note = domain.text("reason", reason, limit=1000)
    with transaction.atomic():
        profile = MentorProfile.objects.select_for_update().filter(user_id=user_id).first()
        if profile is None:
            raise NotFound()
        if profile.status == MentorProfile.Status.REVOKED:
            raise Conflict("This mentor is already revoked.")
        profile.status = MentorProfile.Status.REVOKED
        profile.revoked_at, profile.revoked_by, profile.revoke_reason = timezone.now(), actor, note
        profile.save()
        accounts.revoke_role(user_id, "mentor")
        audit.record(
            actor=actor,
            action="mentors.revoke",
            target_type="mentor",
            target_id=user_id,
            reason=note,
            ip=ip,
        )
        domain_events.publish(events.MentorRevoked(user_id=str(user_id), reason=note))
    return profile


def restore(*, actor: Any, user_id: UUID, ip: str = "") -> MentorProfile:
    with transaction.atomic():
        profile = MentorProfile.objects.select_for_update().filter(user_id=user_id).first()
        if profile is None:
            raise NotFound()
        if profile.status != MentorProfile.Status.REVOKED:
            raise Conflict("This mentor is not revoked.")
        if not accounts.is_active(user_id):
            raise Conflict("The account is not active.")
        profile.status = MentorProfile.Status.ACTIVE
        profile.revoked_at = profile.revoked_by = None
        profile.revoke_reason = ""
        profile.save()
        accounts.grant_role(user_id, "mentor")
        audit.record(
            actor=actor,
            action="mentors.restore",
            target_type="mentor",
            target_id=user_id,
            ip=ip,
        )
    return profile
