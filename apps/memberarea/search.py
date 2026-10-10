"""Search for people and startups, as a member sees them.

Matching uses only fields in each item's ``basics`` group, and every hit goes through the same
projection as the profile and startup pages, so someone who hides their basics from members
cannot be found and nothing is matched on a field the searcher may not see. Typos are tolerated
through trigram word similarity. Jobs, courses, posts, mentors and events join the registry as
their modules arrive.
"""

from collections.abc import Callable
from typing import Any

from django.contrib.postgres.search import TrigramWordSimilarity
from django.db.models import Q
from django.db.models.functions import Greatest

from apps.accounts import services as accounts
from apps.core.visibility import audience_for
from apps.profiles import selectors as profiles
from apps.profiles.models import FounderProfile
from apps.startups import selectors as startups
from apps.startups.models import Startup

MIN_SIMILARITY = 0.45
OVERFETCH = 3  # hits hidden from the searcher are dropped after the query


def _members(viewer: Any, query: str, limit: int) -> list[dict[str, Any]]:
    rows = (
        FounderProfile.objects.filter(user_id__in=accounts.active_user_ids())
        .annotate(
            rank=Greatest(
                TrigramWordSimilarity(query, "full_name"),
                TrigramWordSimilarity(query, "headline") * 0.8,
            )
        )
        .filter(
            Q(rank__gte=MIN_SIMILARITY)
            | Q(full_name__icontains=query)
            | Q(headline__icontains=query)
        )
        .prefetch_related("skills")
        .order_by("-rank", "full_name", "pk")[: limit * OVERFETCH]
    )
    hits: list[dict[str, Any]] = []
    for profile in rows:
        view = profiles.project_profile(profile, audience_for(viewer, {profile.user_id}))
        if view is None:
            continue
        hits.append(
            {
                "type": "member",
                "id": profile.user_id,
                "slug": profile.slug,
                "title": view["full_name"],
                "subtitle": view.get("headline", ""),
                "image": view.get("photo"),
            }
        )
        if len(hits) == limit:
            break
    return hits


def _startups(viewer: Any, query: str, limit: int) -> list[dict[str, Any]]:
    rows = (
        Startup.objects.filter(owner_id__in=accounts.active_user_ids())
        .annotate(
            rank=Greatest(
                TrigramWordSimilarity(query, "name"), TrigramWordSimilarity(query, "pitch") * 0.8
            )
        )
        .filter(Q(rank__gte=MIN_SIMILARITY) | Q(name__icontains=query) | Q(pitch__icontains=query))
        .select_related("sector", "stage")
        .prefetch_related("members", "traction")
        .order_by("-rank", "name", "pk")[: limit * OVERFETCH]
    )
    hits: list[dict[str, Any]] = []
    for startup in rows:
        view = startups.project_startup(startup, audience_for(viewer, startups.team_ids(startup)))
        if view is None:
            continue
        hits.append(
            {
                "type": "startup",
                "id": startup.pk,
                "slug": startup.slug,
                "title": view["name"],
                "subtitle": view.get("pitch", ""),
                "image": view.get("logo"),
            }
        )
        if len(hits) == limit:
            break
    return hits


SEARCHERS: dict[str, Callable[[Any, str, int], list[dict[str, Any]]]] = {
    "members": _members,
    "startups": _startups,
}


def search(
    viewer: Any, query: str, kinds: list[str], limit: int
) -> dict[str, list[dict[str, Any]]]:
    return {kind: SEARCHERS[kind](viewer, query, limit) for kind in kinds}
