"""Read side of startups. All visibility decisions happen here."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from django.db.models import Count, Q, QuerySet

from apps.accounts import services as accounts
from apps.core.visibility import Audience, audience_for, can_see, effective_levels, project
from apps.startups import domain
from apps.startups.models import Startup, StartupMember, TractionMetric
from apps.startups.services import values_of
from apps.uploads import services as uploads


def _queryset() -> QuerySet[Startup]:
    return Startup.objects.select_related("sector", "stage").prefetch_related("members", "traction")


def levels_of(startup: Startup) -> dict[str, str]:
    return effective_levels(startup.visibility, domain.DEFAULT_LEVELS)


def team_ids(startup: Startup) -> frozenset[Any]:
    """Everyone with a seat on the team, plus the owner, reads the startup as its owner."""
    ids = {m.user_id for m in startup.members.all() if m.user_id is not None}
    ids.add(startup.owner_id)
    return frozenset(ids)


def _traction_value(metric: TractionMetric) -> int | str | None:
    return metric.value_int if metric.kind == "users" else metric.value_text


def _traction(startup: Startup, audience: Audience) -> list[dict[str, Any]]:
    """Each metric has its own level, independent of the startup's groups."""
    return [
        {
            "id": metric.pk,
            "kind": metric.kind,
            "value": _traction_value(metric),
            "as_of_date": metric.as_of_date,
            "visibility": metric.visibility,
        }
        for metric in startup.traction.all()
        if can_see(metric.visibility, audience)
    ]


def _team(startup: Startup, audience: Audience) -> list[dict[str, Any]]:
    if audience == Audience.OWNER:
        # Addresses as the owner typed them; nothing shows whether the person has an account.
        return [
            {
                "id": m.pk,
                "email": m.invited_email or None,
                "title": m.title,
                "is_founder": m.is_founder,
            }
            for m in startup.members.all()
        ]
    return [
        {"user_id": m.user_id, "title": m.title, "is_founder": m.is_founder}
        for m in startup.members.all()
        if m.user_id is not None
    ]


def _groups(startup: Startup, audience: Audience) -> dict[str, dict[str, Any]]:
    return {
        "basics": {
            "name": startup.name,
            "pitch": startup.pitch,
            "logo": uploads.image_urls(startup.logo_key),
            "sector": {"slug": startup.sector.slug, "name": startup.sector.name},
            "stage": {"slug": startup.stage.slug, "name": startup.stage.name},
            "country": startup.country,
            "city": startup.city,
            "year_founded": startup.year_founded,
        },
        "description": {"description": startup.description},
        "website": {"website_url": startup.website_url},
        "team": {"team": _team(startup, audience)},
    }


def project_startup(startup: Startup, audience: Audience) -> dict[str, Any] | None:
    """What ``audience`` may see, or None if not even the basics (answer 404)."""
    levels = levels_of(startup)
    visible = project(_groups(startup, audience), levels, audience)
    if "name" not in visible:
        return None
    visible.update(
        id=startup.pk,
        slug=startup.slug,
        featured=startup.featured_at is not None,
        traction=_traction(startup, audience),
    )
    if audience == Audience.OWNER:
        score, next_missing = domain.completeness(values_of(startup))
        visible.update(
            owner_id=startup.owner_id,
            directory_opt_in=startup.directory_opt_in,
            visibility=levels,
            completeness={"score": score, "next_missing_field": next_missing},
        )
    return visible


def get_startup(startup_id: UUID) -> Startup | None:
    return _queryset().filter(pk=startup_id).first()


def startup_for_viewer(viewer: Any, startup_id: UUID) -> tuple[Startup, dict[str, Any]] | None:
    startup = get_startup(startup_id)
    if startup is None:
        return None
    view = project_startup(startup, audience_for(viewer, team_ids(startup)))
    return (startup, view) if view is not None else None


def my_startups(user_id: UUID) -> list[tuple[Startup, dict[str, Any]]]:
    """Startups the user owns or sits on the team of, as their owner view."""
    startups = (
        _queryset()
        .filter(Q(owner_id=user_id) | Q(members__user_id=user_id))
        .distinct()
        .order_by("-created_at")
    )
    views = []
    for startup in startups:
        view = project_startup(startup, Audience.OWNER)
        if view is not None:
            views.append((startup, view))
    return views


def membership(user_id: UUID, startup_id: UUID) -> StartupMember | None:
    return StartupMember.objects.filter(startup_id=startup_id, user_id=user_id).first()


@dataclass(frozen=True)
class PublicStartupSource:
    """A startup as the public may see it, for the directory's read model."""

    startup_id: UUID
    owner_id: UUID
    slug: str
    view: dict[str, Any]
    created_at: datetime
    featured_at: datetime | None
    founder_ids: list[UUID]


def public_source(startup_id: UUID) -> PublicStartupSource | None:
    """None unless the startup is listed, its owner is active and its basics are public."""
    startup = get_startup(startup_id)
    if startup is None or not startup.directory_opt_in:
        return None
    if not accounts.is_active(startup.owner_id):
        return None
    view = project_startup(startup, Audience.PUBLIC)
    if view is None:
        return None
    founder_ids = [m["user_id"] for m in view.get("team", []) if m["is_founder"]]
    return PublicStartupSource(
        startup.pk,
        startup.owner_id,
        startup.slug,
        view,
        startup.created_at,
        startup.featured_at,
        founder_ids,
    )


def startup_ids_of_member(user_id: UUID) -> list[UUID]:
    """Every startup the user owns or sits on the team of, listed or not."""
    ids = set(Startup.objects.filter(owner_id=user_id).values_list("pk", flat=True))
    ids |= set(StartupMember.objects.filter(user_id=user_id).values_list("startup_id", flat=True))
    return sorted(ids)


def listed_startup_ids() -> list[UUID]:
    """Startups that asked to appear in the public directory."""
    return list(Startup.objects.filter(directory_opt_in=True).values_list("pk", flat=True))


def count_by_sector(slugs: list[str]) -> dict[str, int]:
    rows = (
        Startup.objects.filter(sector__slug__in=slugs)
        .values("sector__slug")
        .annotate(n=Count("id"))
    )
    return {row["sector__slug"]: row["n"] for row in rows}


def count_by_stage(slugs: list[str]) -> dict[str, int]:
    rows = (
        Startup.objects.filter(stage__slug__in=slugs).values("stage__slug").annotate(n=Count("id"))
    )
    return {row["stage__slug"]: row["n"] for row in rows}
