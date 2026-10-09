"""Keeps the read model in step with its sources.

Each ``refresh_*`` function re-derives one row from the current source data, or
removes it when the source no longer qualifies. They are safe to run any number
of times, in any order.
"""

from typing import Any
from uuid import UUID

import structlog
from django.contrib.postgres.search import SearchVector
from django.utils import timezone

from apps.directory import build
from apps.directory.models import PublicFounder, PublicStartup
from apps.integrations.cdn import get_cache_purger
from apps.profiles import selectors as profiles
from apps.startups import selectors as startups

logger = structlog.get_logger(__name__)

API = "/api/v1/public"


def _startup_vector() -> Any:
    cfg = "simple"
    return (
        SearchVector("name", weight="A", config=cfg)
        + SearchVector("pitch", "founder_names", weight="B", config=cfg)
        + SearchVector("sector_name", "city", "skill_names", weight="C", config=cfg)
        + SearchVector("description", weight="D", config=cfg)
    )


def _founder_vector() -> Any:
    cfg = "simple"
    return (
        SearchVector("full_name", weight="A", config=cfg)
        + SearchVector("headline", "startup_names", weight="B", config=cfg)
        + SearchVector("city", "skill_names", weight="C", config=cfg)
        + SearchVector("bio", weight="D", config=cfg)
    )


def _purge(paths: list[str]) -> None:
    try:
        get_cache_purger().purge(paths)
    except Exception:  # a CDN hiccup must not undo the refresh; pages expire on their own
        logger.warning("cdn_purge_failed", paths=paths)


# --- startups ---------------------------------------------------------------------------------


def refresh_startup(startup_id: UUID) -> None:
    """Rebuild one startup's row, and the pages of the founders linked to it."""
    existing = PublicStartup.objects.filter(startup_id=startup_id).first()
    source = startups.public_source(startup_id)
    founder_ids: set[UUID] = set()
    purge = [f"{API}/startups", f"{API}/sitemap"]

    if existing is not None:
        # Founders previously linked must be refreshed even if they just left the team.
        linked = PublicFounder.objects.filter(startup_slugs__contains=[existing.slug])
        founder_ids |= set(linked.values_list("user_id", flat=True))
        purge.append(f"{API}/startups/{existing.slug}")

    if source is None:
        PublicStartup.objects.filter(startup_id=startup_id).delete()
    else:
        founders = [s for s in (profiles.public_source(uid) for uid in source.founder_ids) if s]
        fields = build.build_startup(source, founders)
        fields["source_updated_at"] = timezone.now()
        row, _ = PublicStartup.objects.update_or_create(startup_id=startup_id, defaults=fields)
        PublicStartup.objects.filter(pk=row.pk).update(search_vector=_startup_vector())
        founder_ids |= set(source.founder_ids)
        purge.append(f"{API}/startups/{source.slug}")

    for user_id in founder_ids:
        refresh_founder(user_id)
    _purge(purge)


# --- founders ---------------------------------------------------------------------------------


def refresh_founder(user_id: UUID) -> None:
    """Rebuild one founder's row, or remove it if their basics are not public."""
    existing = PublicFounder.objects.filter(user_id=user_id).first()
    source = profiles.public_source(user_id)
    purge = [f"{API}/founders", f"{API}/sitemap"]
    if existing is not None:
        purge.append(f"{API}/founders/{existing.slug}")

    if source is None:
        PublicFounder.objects.filter(user_id=user_id).delete()
    else:
        listed = []
        for startup_id in startups.startup_ids_of_member(user_id):
            candidate = startups.public_source(startup_id)
            if candidate is not None and user_id in candidate.founder_ids:
                listed.append(candidate)
        fields = build.build_founder(source, listed)
        fields["source_updated_at"] = timezone.now()
        row, _ = PublicFounder.objects.update_or_create(user_id=user_id, defaults=fields)
        PublicFounder.objects.filter(pk=row.pk).update(search_vector=_founder_vector())
        purge.append(f"{API}/founders/{source.slug}")
    _purge(purge)


# --- reactions to changes elsewhere -------------------------------------------------------------


def refresh_member(user_id: UUID) -> None:
    """Their profile changed, or they were approved or reinstated."""
    refresh_founder(user_id)
    for startup_id in startups.startup_ids_of_member(user_id):
        refresh_startup(startup_id)


def take_down_member(user_id: UUID) -> None:
    """Suspended or removed: their pages and the startups they own come down."""
    purge = [f"{API}/startups", f"{API}/founders", f"{API}/sitemap"]
    purge += [f"{API}/startups/{slug}" for slug in _slugs(PublicStartup, owner_id=user_id)]
    purge += [f"{API}/founders/{slug}" for slug in _slugs(PublicFounder, user_id=user_id)]
    PublicStartup.objects.filter(owner_id=user_id).delete()
    PublicFounder.objects.filter(user_id=user_id).delete()
    _purge(purge)
    for startup_id in startups.startup_ids_of_member(user_id):
        refresh_startup(startup_id)  # startups they were only a team member of lose them


def _slugs(model: type[PublicStartup] | type[PublicFounder], **filters: UUID) -> list[str]:
    return list(model.objects.filter(**filters).values_list("slug", flat=True))


def reconcile() -> dict[str, int]:
    """Rebuild everything from the sources and drop rows that no longer qualify.

    Run hourly as a safety net, and by hand after a restore or a bulk change.
    """
    listed = set(startups.listed_startup_ids())
    people = set(profiles.profile_user_ids())
    stale_startups = PublicStartup.objects.exclude(startup_id__in=listed)
    stale_founders = PublicFounder.objects.exclude(user_id__in=people)
    removed = stale_startups.count() + stale_founders.count()
    stale_startups.delete()
    stale_founders.delete()
    for user_id in people:
        refresh_founder(user_id)
    for startup_id in listed:
        refresh_startup(startup_id)
    return {
        "startups": PublicStartup.objects.count(),
        "founders": PublicFounder.objects.count(),
        "removed": removed,
    }
