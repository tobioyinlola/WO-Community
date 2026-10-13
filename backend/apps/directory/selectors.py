"""Read side of the public directory. Only the read model is touched."""

from typing import Any

from django.contrib.postgres.search import SearchQuery, SearchRank, TrigramSimilarity
from django.db.models import F, Q, QuerySet

from apps.accounts import services as accounts
from apps.directory.models import PublicFounder, PublicStartup
from apps.directory.pagination import paginate

STARTUP_ORDERS = {
    "newest": ("featured_rank", "newest_key", "id"),
    "alphabetical": ("featured_rank", "name_key", "id"),
}
FOUNDER_ORDERS = {
    "newest": ("newest_key", "id"),
    "alphabetical": ("name_key", "id"),
}
MAX_SITEMAP_ENTRIES = 50_000


def _startups() -> QuerySet[PublicStartup]:
    # The owner's status is checked now, not only when the row was built, so a
    # suspended or removed member's startup disappears at once.
    return PublicStartup.objects.filter(owner_id__in=accounts.active_user_ids())


def _founders() -> QuerySet[PublicFounder]:
    return PublicFounder.objects.filter(user_id__in=accounts.active_user_ids())


def _matching(queryset: QuerySet[Any], q: str, name_field: str) -> QuerySet[Any]:
    """Rows matching the text, best first. Names also match partial words and typos."""
    query = SearchQuery(q, search_type="websearch", config="simple")
    advanced = '"' in q or any(term.startswith("-") for term in q.split())
    # Quotes and exclusions mean the person wants exact full-text rules, so the forgiving
    # name matching (partial words, typos) would only undo them.
    condition = Q(search_vector=query)
    if not advanced:
        condition |= Q(**{f"{name_field}__icontains": q})
        condition |= Q(**{f"{name_field}__trigram_similar": q})
    return (
        queryset.filter(condition)
        .annotate(rank=SearchRank(F("search_vector"), query) + TrigramSimilarity(name_field, q))
        .order_by("-rank", "id")
    )


def search_startups(
    *,
    q: str = "",
    country: str = "",
    sector: str = "",
    stage: str = "",
    skills: list[str] | None = None,
    featured: bool = False,
    sort: str = "newest",
    cursor: str = "",
    limit: int = 20,
) -> tuple[list[dict[str, Any]], str | None]:
    queryset = _startups()
    if country:
        queryset = queryset.filter(country=country.upper())
    if sector:
        queryset = queryset.filter(sector_slug=sector)
    if stage:
        queryset = queryset.filter(stage_slug=stage)
    for skill in skills or []:
        queryset = queryset.filter(skill_slugs__contains=[skill])
    if featured:
        queryset = queryset.filter(featured_rank=0)
    if q:
        # Relevance order has no stable cursor, so a search returns its best matches only.
        return [row.card for row in _matching(queryset, q, "name")[:limit]], None
    rows, next_cursor = paginate(
        queryset, fields=STARTUP_ORDERS[sort], sort=sort, cursor=cursor, limit=limit
    )
    return [row.card for row in rows], next_cursor


def search_founders(
    *,
    q: str = "",
    country: str = "",
    skills: list[str] | None = None,
    sort: str = "newest",
    cursor: str = "",
    limit: int = 20,
) -> tuple[list[dict[str, Any]], str | None]:
    queryset = _founders()
    if country:
        queryset = queryset.filter(country=country.upper())
    for skill in skills or []:
        queryset = queryset.filter(skill_slugs__contains=[skill])
    if q:
        return [row.card for row in _matching(queryset, q, "full_name")[:limit]], None
    rows, next_cursor = paginate(
        queryset, fields=FOUNDER_ORDERS[sort], sort=sort, cursor=cursor, limit=limit
    )
    return [row.card for row in rows], next_cursor


def startup_detail(slug: str) -> dict[str, Any] | None:
    row = _startups().filter(slug=slug).first()
    return row.detail if row else None


def founder_detail(slug: str) -> dict[str, Any] | None:
    row = _founders().filter(slug=slug).first()
    return row.detail if row else None


def sitemap() -> dict[str, list[dict[str, Any]]]:
    """Every public page with its last change, for search engines."""
    startups = _startups().order_by("slug").values_list("slug", "source_updated_at")
    founders = _founders().order_by("slug").values_list("slug", "source_updated_at")
    return {
        "startups": [
            {"slug": slug, "path": f"/startups/{slug}", "lastmod": stamp}
            for slug, stamp in startups[:MAX_SITEMAP_ENTRIES]
        ],
        "founders": [
            {"slug": slug, "path": f"/founders/{slug}", "lastmod": stamp}
            for slug, stamp in founders[:MAX_SITEMAP_ENTRIES]
        ],
    }
