"""Commands that change startups, their teams and their traction."""

import secrets
from typing import Any
from uuid import UUID

from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.text import slugify
from rest_framework import exceptions

from apps.accounts import services as accounts
from apps.audit import services as audit
from apps.core import etag
from apps.core import events as domain_events
from apps.core.errors import ConflictError
from apps.core.visibility import LEVELS
from apps.reference import selectors as reference
from apps.startups import domain, events
from apps.startups.models import Startup, StartupMember, TractionMetric

BASIC_FIELDS = ("name", "pitch", "country", "city", "year_founded")
TEXT_FIELDS = ("description", "website_url")


def _new_slug(name: str) -> str:
    return f"{slugify(name)[:50] or 'startup'}-{secrets.token_hex(3)}"


def values_of(startup: Startup) -> dict[str, Any]:
    """Startup values in the shape the completeness rules read."""
    return {
        "name": startup.name,
        "pitch": startup.pitch,
        "sector": startup.sector_id,
        "stage": startup.stage_id,
        "country": startup.country,
        "year_founded": startup.year_founded,
        "description": startup.description,
        "website_url": startup.website_url,
        "traction_count": startup.traction.count() if startup.pk else 0,
        "team_count": startup.members.count() if startup.pk else 0,
    }


def refresh_completeness(startup: Startup) -> None:
    startup.completeness_score, _ = domain.completeness(values_of(startup))


def _publish(startup: Startup) -> None:
    domain_events.publish(events.StartupUpdated(startup_id=str(startup.pk)))


def _resolve(sector_slug: str, stage_slug: str) -> tuple[Any, Any]:
    sector = reference.get_sector(sector_slug)
    stage = reference.get_stage(stage_slug)
    errors: dict[str, list[str]] = {}
    if sector is None:
        errors["sector"] = ["Choose a sector from the list."]
    if stage is None:
        errors["stage"] = ["Choose a stage from the list."]
    if errors:
        raise exceptions.ValidationError(errors)
    return sector, stage


def create_startup(*, owner_id: UUID, data: dict[str, Any]) -> Startup:
    """A new startup owned by ``owner_id``, who is also its first founder."""
    sector, stage = _resolve(data["sector"], data["stage"])
    for _ in range(5):  # a slug clash is very unlikely, but is retried rather than failed
        try:
            with transaction.atomic():
                startup = Startup(
                    owner_id=owner_id,
                    slug=_new_slug(data["name"]),
                    sector=sector,
                    stage=stage,
                    **{k: data[k] for k in (*BASIC_FIELDS, *TEXT_FIELDS) if k in data},
                )
                startup.save()
                StartupMember.objects.create(
                    startup=startup, user_id=owner_id, title="Founder", is_founder=True
                )
                refresh_completeness(startup)
                startup.save(update_fields=["completeness_score", "updated_at"])
                _publish(startup)
                return startup
        except IntegrityError:
            continue
    raise ConflictError("Could not create the startup. Try again.", code="slug_unavailable")


def create_from_signup(user_id: UUID, details: dict[str, Any]) -> Startup | None:
    """The startup typed into the registration form. Safe to run twice."""
    if Startup.objects.filter(owner_id=user_id).exists():
        return None
    return create_startup(owner_id=user_id, data=details)


# --- who may do what ------------------------------------------------------------------


def _lock(startup_id: UUID) -> Startup:
    startup = Startup.objects.select_for_update().filter(pk=startup_id).first()
    if startup is None:
        raise exceptions.NotFound()
    return startup


def _require_editor(user_id: UUID, startup: Startup) -> None:
    """Owner or a founder on the team. Anyone else on the team is told no; outsiders get 404."""
    if startup.owner_id == user_id:
        return
    membership = StartupMember.objects.filter(startup=startup, user_id=user_id).first()
    if membership is None:
        raise exceptions.NotFound()
    if not membership.is_founder:
        raise exceptions.PermissionDenied("Only founders can change the startup.")


def _require_owner(user_id: UUID, startup: Startup) -> None:
    if startup.owner_id == user_id:
        return
    if StartupMember.objects.filter(startup=startup, user_id=user_id).exists():
        raise exceptions.PermissionDenied("Only the owner can do this.")
    raise exceptions.NotFound()


# --- profile ----------------------------------------------------------------------------


def update_startup(
    *, user_id: UUID, startup_id: UUID, data: dict[str, Any], if_match: str | None
) -> Startup:
    with transaction.atomic():
        startup = _lock(startup_id)
        _require_editor(user_id, startup)
        etag.assert_matches(if_match, startup)
        if "directory_opt_in" in data:
            _require_owner(user_id, startup)
            startup.directory_opt_in = data["directory_opt_in"]
            if startup.directory_opt_in:  # a listing is pointless unless its card is public
                startup.visibility = {**startup.visibility, "basics": "public"}
        for field in (*BASIC_FIELDS, *TEXT_FIELDS):
            if field in data:
                setattr(startup, field, data[field])
        if "sector" in data or "stage" in data:
            sector, stage = _resolve(
                data.get("sector", startup.sector.slug), data.get("stage", startup.stage.slug)
            )
            startup.sector, startup.stage = sector, stage
        refresh_completeness(startup)
        startup.save()
        _publish(startup)
    return startup


def set_visibility(
    *, user_id: UUID, startup_id: UUID, levels: dict[str, str], if_match: str | None
) -> Startup:
    unknown = sorted(set(levels) - set(domain.GROUP_FIELDS))
    if unknown:
        raise exceptions.ValidationError({name: ["Unknown field group."] for name in unknown})
    bad = sorted(name for name, level in levels.items() if level not in LEVELS)
    if bad:
        raise exceptions.ValidationError(
            {name: [f"Choose one of: {', '.join(LEVELS)}."] for name in bad}
        )
    with transaction.atomic():
        startup = _lock(startup_id)
        _require_editor(user_id, startup)
        etag.assert_matches(if_match, startup)
        merged = {**startup.visibility, **levels}
        if startup.directory_opt_in and merged.get("basics") != "public":
            raise ConflictError(
                "The basics must stay public while the startup is listed in the directory.",
                code="listed_in_directory",
            )
        startup.visibility = merged
        startup.save()
        _publish(startup)
    return startup


# --- team ---------------------------------------------------------------------------------


def add_team_member(
    *, owner_id: UUID, startup_id: UUID, email: str, title: str, is_founder: bool
) -> StartupMember:
    """Add a person by email.

    Whether or not they have an account, the owner gets the same answer; an
    address that is not an active member yet is attached when they are approved.
    """
    address = email.strip().lower()
    with transaction.atomic():
        startup = _lock(startup_id)
        _require_owner(owner_id, startup)
        if StartupMember.objects.filter(startup=startup, invited_email__iexact=address).exists():
            raise ConflictError("This address is already on the team.", code="already_on_team")
        user_id = accounts.find_active_member_id(address)
        if (
            user_id is not None
            and StartupMember.objects.filter(startup=startup, user_id=user_id).exists()
        ):
            raise ConflictError("This address is already on the team.", code="already_on_team")
        member = StartupMember.objects.create(
            startup=startup,
            user_id=user_id,
            invited_email=address,
            title=title,
            is_founder=is_founder,
        )
        refresh_completeness(startup)
        startup.save(update_fields=["completeness_score", "updated_at"])
        _publish(startup)
    return member


def remove_team_member(*, actor_id: UUID, startup_id: UUID, member_id: UUID) -> None:
    """The owner can remove anyone but themselves; members can remove themselves."""
    with transaction.atomic():
        startup = _lock(startup_id)
        member = StartupMember.objects.filter(pk=member_id, startup=startup).first()
        is_owner = startup.owner_id == actor_id
        if member is None or not (is_owner or member.user_id == actor_id):
            raise exceptions.NotFound()
        if member.user_id == startup.owner_id:
            raise ConflictError("The owner cannot be removed from their startup.", code="is_owner")
        member.delete()
        refresh_completeness(startup)
        startup.save(update_fields=["completeness_score", "updated_at"])
        _publish(startup)


def link_invited(user_id: UUID, email: str) -> int:
    """Attach a newly approved member to every team that listed their address."""
    return StartupMember.objects.filter(
        user__isnull=True, invited_email__iexact=email.strip().lower()
    ).update(user_id=user_id)


# --- traction -------------------------------------------------------------------------------


def replace_traction(
    *, user_id: UUID, startup_id: UUID, items: list[dict[str, Any]], if_match: str | None
) -> Startup:
    """Replace the whole traction list. ``items`` are validated and cleaned."""
    with transaction.atomic():
        startup = _lock(startup_id)
        _require_editor(user_id, startup)
        etag.assert_matches(if_match, startup)
        today = timezone.now().date()
        startup.traction.all().delete()
        TractionMetric.objects.bulk_create(
            TractionMetric(
                startup=startup,
                kind=item["kind"],
                value_int=item["value"] if item["kind"] == "users" else None,
                value_text="" if item["kind"] == "users" else str(item["value"]),
                as_of_date=item.get("as_of_date") or today,
                visibility=item["visibility"],
            )
            for item in items
        )
        refresh_completeness(startup)
        startup.save()
        _publish(startup)
    return startup


def set_featured(*, actor: Any, startup_id: UUID, featured: bool, ip: str = "") -> Startup:
    """Pin or unpin a listed startup. Only listed startups can be featured."""
    with transaction.atomic():
        startup = _lock(startup_id)
        if featured and not startup.directory_opt_in:
            raise ConflictError("Only listed startups can be featured.", code="not_listed")
        startup.featured_at = timezone.now() if featured else None
        startup.save(update_fields=["featured_at", "updated_at"])
        audit.record(
            actor=actor,
            action="startup.featured" if featured else "startup.unfeatured",
            target_type="startup",
            target_id=startup.pk,
            ip=ip,
        )
        _publish(startup)
    return startup
