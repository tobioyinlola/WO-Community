"""Commands for ventures: create, edit the profile, import, delete and erase."""

from collections.abc import Callable
from typing import Any
from uuid import UUID

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import exceptions

from apps.audit import services as audit
from apps.core.errors import ConflictError
from apps.core.text import plain
from apps.reference import selectors as reference
from apps.startups import selectors as startups
from apps.toolkit.ventures import schema
from apps.toolkit.ventures.models import (
    Competitor,
    OutputState,
    TeamMember,
    Venture,
    VentureProfile,
    VentureProfileVersion,
)

MAX_COMPETITORS = 8
MAX_TEAM = 20
CORE_OUTPUTS = ("score", "plan", "forecast")

# Modules add what they hold to a venture export, and what they must erase with it.
_exporters: dict[str, Callable[[Venture], Any]] = {}
_erasers: list[Callable[[Venture], None]] = []


def register_exporter(name: str, fn: Callable[[Venture], Any]) -> None:
    _exporters[name] = fn


def register_eraser(fn: Callable[[Venture], None]) -> None:
    _erasers.append(fn)


class NotFound(exceptions.NotFound):
    default_detail = "Not found."


def _invalid(field: str, message: str) -> exceptions.ValidationError:
    return exceptions.ValidationError({field: [message]})


# --- ventures ---


def create_venture(*, owner_id: UUID, name: str, from_startup_id: UUID | None = None) -> Venture:
    title = plain(name)
    if not 2 <= len(title) <= 80:
        raise _invalid("name", "Between 2 and 80 characters.")
    with transaction.atomic():
        live = Venture.objects.filter(owner_id=owner_id, deleted_at__isnull=True)
        if live.select_for_update().count() >= settings.TOOLKIT_MAX_VENTURES_PER_MEMBER:
            raise ConflictError(
                f"You can have {settings.TOOLKIT_MAX_VENTURES_PER_MEMBER} ventures at a time.",
                code="venture_limit",
            )
        venture = Venture.objects.create(
            owner_id=owner_id,
            name=title,
            profile_completeness=schema.completeness({"name": title}, competitors=0, team=0),
        )
        VentureProfile.objects.create(
            venture=venture,
            fields={"name": title},
            field_meta={"name": {"source": "member", "updated_at": timezone.now().isoformat()}},
        )
        for output in CORE_OUTPUTS:
            OutputState.objects.create(venture=venture, output_type=output)
        _snapshot(venture, 1, ["name"], "member")
        audit.record(
            actor=None,
            action="toolkit.venture_created",
            target_type="venture",
            target_id=venture.pk,
            after={"owner": str(owner_id)},
        )
    if from_startup_id is not None:
        import_startup(venture=venture, user_id=owner_id, startup_id=from_startup_id)
        venture.refresh_from_db()
    else:
        _prefill_from_member(venture, owner_id)
        venture.refresh_from_db()
    return venture


def _prefill_from_member(venture: Venture, user_id: UUID) -> None:
    """Carry over what the member already told us at sign up, so they never type it twice."""
    from apps.profiles import selectors as profiles

    country, city = profiles.location_of(user_id)
    patch: dict[str, Any] = {}
    for name, value in (("country", country), ("city", city)):
        if not value:
            continue
        try:
            patch.update(schema.validate_patch({name: value}))
        except schema.ProfileInvalid:
            continue
    if patch:
        update_profile(venture=venture, patch=patch, actor="import", source="imported")


def update_venture(*, venture: Venture, name: str | None, archived: bool | None) -> Venture:
    changed = []
    if name is not None:
        title = plain(name)
        if not 2 <= len(title) <= 80:
            raise _invalid("name", "Between 2 and 80 characters.")
        venture.name = title
        changed.append("name")
        update_profile(venture=venture, patch={"name": title}, actor="member")
    if archived is not None:
        venture.status = "archived" if archived else "active"
        venture.archived_at = timezone.now() if archived else None
        changed += ["status", "archived_at"]
    if changed:
        venture.save(update_fields=[*dict.fromkeys(changed), "updated_at"])
    return venture


def delete_venture(*, venture: Venture) -> None:
    """Hide it now; it and everything made from it is erased after the grace period."""
    with transaction.atomic():
        venture.deleted_at = timezone.now()
        venture.save(update_fields=["deleted_at", "updated_at"])
        audit.record(
            actor=None,
            action="toolkit.venture_deleted",
            target_type="venture",
            target_id=venture.pk,
            after={"owner": str(venture.owner_id)},
        )


def restore_venture(*, venture: Venture) -> Venture:
    venture.deleted_at = None
    venture.save(update_fields=["deleted_at", "updated_at"])
    return venture


def erase_due(now: Any = None) -> int:
    """Erase ventures whose grace period is over. Files and shares go with them."""
    from datetime import timedelta

    now = now or timezone.now()
    cutoff = now - timedelta(days=settings.VENTURE_DELETE_GRACE_DAYS)
    erased = 0
    for venture in list(Venture.objects.filter(deleted_at__isnull=False, deleted_at__lte=cutoff)):
        with transaction.atomic():
            for eraser in _erasers:
                eraser(venture)
            audit.record(
                actor=None,
                action="toolkit.venture_erased",
                target_type="venture",
                target_id=venture.pk,
            )
            venture.delete()
            erased += 1
    return erased


def export_data(venture: Venture) -> dict[str, Any]:
    """Everything held about a venture, as one document the member can keep."""
    from apps.toolkit.ventures import selectors

    body: dict[str, Any] = {
        "venture": {
            "id": str(venture.pk),
            "name": venture.name,
            "created_at": venture.created_at.isoformat(),
        },
        "profile": selectors.profile_view(venture),
        "profile_versions": selectors.versions(venture),
    }
    for name, fn in sorted(_exporters.items()):
        body[name] = fn(venture)
    return body


# --- the profile ---


def _snapshot(venture: Venture, version: int, changed: list[str], actor: str) -> None:
    profile = VentureProfile.objects.get(venture=venture)
    VentureProfileVersion.objects.create(
        venture=venture,
        version=version,
        snapshot={"fields": profile.fields, "meta": profile.field_meta},
        changed_fields=changed,
        actor=actor,
    )


def _check_sector(fields: dict[str, Any]) -> None:
    slug = fields.get("sector")
    if slug and not reference.sectors().filter(slug=slug).exists():
        raise exceptions.ValidationError({"sector": ["Choose a sector from the list."]})


def update_profile(
    *,
    venture: Venture,
    patch: dict[str, Any],
    actor: str = "member",
    source: str = "member",
    base_version: int | None = None,
    accepted_fields: set[str] | None = None,
) -> tuple[VentureProfile, list[str]]:
    """Apply a partial update. Returns the profile and the fields that really changed.

    ``source`` records where each value came from (member, imported, or an accepted suggestion).
    A stale ``base_version`` is a 409 so two tabs cannot overwrite each other silently.
    """
    try:
        cleaned = schema.validate_patch(patch)
    except schema.ProfileInvalid as exc:
        raise exceptions.ValidationError(exc.errors) from exc
    with transaction.atomic():
        profile = VentureProfile.objects.select_for_update().get(venture=venture)
        if base_version is not None and base_version != profile.version:
            raise ConflictError(
                "The profile changed elsewhere. Reload and try again.", code="stale"
            )
        merged = dict(profile.fields)
        changed: list[str] = []
        for name, value in cleaned.items():
            if value is None:
                if name in merged:
                    del merged[name]
                    changed.append(name)
            elif merged.get(name) != value:
                merged[name] = value
                changed.append(name)
        errors = schema.cross_check(merged)
        if errors:
            raise exceptions.ValidationError(errors)
        _check_sector(merged)
        if not changed:
            return profile, []
        now = timezone.now().isoformat()
        meta = dict(profile.field_meta)
        for name in changed:
            kind = source if accepted_fields is None or name in accepted_fields else "member"
            if name in merged:
                meta[name] = {"source": kind, "updated_at": now}
            else:
                meta.pop(name, None)
        profile.fields, profile.field_meta = merged, meta
        profile.version += 1
        profile.save()
        _after_change(venture, profile, changed, actor)
    return profile, changed


def _after_change(
    venture: Venture, profile: VentureProfile, changed: list[str], actor: str
) -> None:
    venture.profile_completeness = schema.completeness(
        profile.fields,
        competitors=venture.competitors.count(),
        team=venture.team.count(),
    )
    updates = ["profile_completeness", "updated_at"]
    if "name" in changed and profile.fields.get("name") and venture.name != profile.fields["name"]:
        venture.name = profile.fields["name"]
        updates.append("name")
    venture.save(update_fields=updates)
    _snapshot(venture, profile.version, changed, actor)
    mark_stale(venture, changed)


def mark_stale(venture: Venture, changed: list[str]) -> None:
    """Flag the outputs that were made from fields that have since changed."""
    affected: dict[str, list[str]] = {}
    for name in changed:
        for output in schema.DEPENDENTS.get(name, ()):
            affected.setdefault(output, []).append(name)
    for output, fields in affected.items():
        for state in OutputState.objects.select_for_update().filter(
            venture=venture, output_type=output, status__in=["ready", "needs_refresh"]
        ):
            state.status = "needs_refresh"
            state.stale_fields = sorted({*state.stale_fields, *fields})
            state.save(update_fields=["status", "stale_fields", "updated_at"])


def clear_stale(venture: Venture, output_type: str, output_id: UUID | None = None) -> None:
    OutputState.objects.filter(
        venture=venture, output_type=output_type, output_id=output_id
    ).update(status="ready", stale_fields=[], last_generated_at=timezone.now())


def set_output_state(
    venture: Venture, output_type: str, status: str, output_id: UUID | None = None
) -> OutputState:
    state, _ = OutputState.objects.get_or_create(
        venture=venture, output_type=output_type, output_id=output_id
    )
    state.status = status
    if status == "ready":
        state.stale_fields = []
        state.last_generated_at = timezone.now()
    state.save()
    return state


# --- rows that sit beside the profile ---


def _recount(venture: Venture, name: str) -> None:
    profile = VentureProfile.objects.get(venture=venture)
    venture.profile_completeness = schema.completeness(
        profile.fields, competitors=venture.competitors.count(), team=venture.team.count()
    )
    venture.save(update_fields=["profile_completeness", "updated_at"])
    mark_stale(venture, [name])


def add_competitor(*, venture: Venture, data: dict[str, Any]) -> Competitor:
    with transaction.atomic():
        if venture.competitors.count() >= MAX_COMPETITORS:
            raise _invalid("name", f"Up to {MAX_COMPETITORS} competitors.")
        row = Competitor.objects.create(
            venture=venture,
            name=plain(data["name"])[:120],
            website=_url(data.get("website", ""), "website"),
            differentiator=plain(data.get("differentiator", ""))[:500],
            position=venture.competitors.count(),
        )
        _recount(venture, "competitors")
    return row


def change_competitor(*, venture: Venture, competitor_id: UUID, data: dict[str, Any]) -> Competitor:
    row = venture.competitors.filter(pk=competitor_id).first()
    if row is None:
        raise NotFound()
    if "name" in data:
        row.name = plain(data["name"])[:120]
    if "website" in data:
        row.website = _url(data["website"], "website")
    if "differentiator" in data:
        row.differentiator = plain(data["differentiator"])[:500]
    row.save()
    mark_stale(venture, ["competitors"])
    return row


def remove_competitor(*, venture: Venture, competitor_id: UUID) -> None:
    with transaction.atomic():
        deleted, _ = venture.competitors.filter(pk=competitor_id).delete()
        if not deleted:
            raise NotFound()
        _recount(venture, "competitors")


def add_team_member(*, venture: Venture, data: dict[str, Any]) -> TeamMember:
    with transaction.atomic():
        if venture.team.count() >= MAX_TEAM:
            raise _invalid("name", f"Up to {MAX_TEAM} people.")
        row = TeamMember.objects.create(
            venture=venture,
            name=plain(data["name"])[:120],
            role=plain(data["role"])[:120],
            linkedin=_url(data.get("linkedin", ""), "linkedin", host="linkedin.com"),
            is_founder=bool(data.get("is_founder", False)),
            position=venture.team.count(),
        )
        _recount(venture, "team")
    return row


def change_team_member(*, venture: Venture, member_id: UUID, data: dict[str, Any]) -> TeamMember:
    row = venture.team.filter(pk=member_id).first()
    if row is None:
        raise NotFound()
    if "name" in data:
        row.name = plain(data["name"])[:120]
    if "role" in data:
        row.role = plain(data["role"])[:120]
    if "linkedin" in data:
        row.linkedin = _url(data["linkedin"], "linkedin", host="linkedin.com")
    if "is_founder" in data:
        row.is_founder = bool(data["is_founder"])
    row.save()
    mark_stale(venture, ["team"])
    return row


def remove_team_member(*, venture: Venture, member_id: UUID) -> None:
    with transaction.atomic():
        deleted, _ = venture.team.filter(pk=member_id).delete()
        if not deleted:
            raise NotFound()
        _recount(venture, "team")


def _url(value: str, field: str, host: str = "") -> str:
    from apps.core.text import clean_url

    try:
        return clean_url(value, hosts=(host,) if host else ())
    except exceptions.ValidationError as exc:
        raise _invalid(field, " ".join(str(m) for m in exc.detail)) from exc


# --- import from a startup the member belongs to ---

_STAGE_MAP = {
    "idea": "idea",
    "pre-seed": "idea",
    "prototype": "prototype",
    "mvp": "prototype",
    "seed": "launched",
    "launched": "launched",
    "series-a": "revenue",
    "series-b": "revenue",
    "growth": "revenue",
}


def import_startup(*, venture: Venture, user_id: UUID, startup_id: UUID) -> VentureProfile:
    """Copy what the member's startup profile holds. They own it or are on its team."""
    if startup_id not in startups.startup_ids_of_member(user_id):
        raise NotFound()
    startup = startups.get_startup(startup_id)
    if startup is None:
        raise NotFound()
    patch: dict[str, Any] = {
        "name": startup.name,
        "one_liner": startup.pitch,
        "country": startup.country,
        "city": startup.city,
        "sector": startup.sector.slug,
    }
    stage = _STAGE_MAP.get(startup.stage.slug)
    if stage:
        patch["stage"] = stage
    if len((startup.description or "").strip()) >= 20:
        patch["business_concept"] = startup.description[:2000]
    users = next(
        (m.value_int for m in startup.traction.all() if m.kind == "users" and m.value_int), None
    )
    if users is not None:
        patch["traction"] = {"users": users}
    # Only what validates is imported; a field that does not fit is left for the member.
    accepted: dict[str, Any] = {}
    for name, value in patch.items():
        try:
            accepted.update(schema.validate_patch({name: value}))
        except schema.ProfileInvalid:
            continue
    with transaction.atomic():
        venture.imported_from_startup = startup
        venture.save(update_fields=["imported_from_startup", "updated_at"])
        profile, _ = update_profile(
            venture=venture, patch=accepted, actor="import", source="imported"
        )
        if not venture.team.exists():
            for position, row in enumerate(startup.members.select_related("user")[:MAX_TEAM]):
                name = _member_name(row)
                if name:
                    TeamMember.objects.create(
                        venture=venture,
                        name=name,
                        role=row.title or ("Founder" if row.is_founder else "Team"),
                        is_founder=row.is_founder,
                        position=position,
                    )
            _recount(venture, "team")
    return profile


def _member_name(row: Any) -> str:
    from apps.profiles import selectors as profiles

    if row.user_id:
        return profiles.full_name_of(row.user_id)
    return ""
