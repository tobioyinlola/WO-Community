"""Browse the member directory: startups and people, filtered and paged.

Search (``search.py``) finds a name across everything. This is the other way in: look through
the listings with filters. Every row goes through the same projection as the profile and startup
pages, so nobody sees a field its owner kept from members.
"""

from typing import Any

from django.db.models import Exists, F, OuterRef, Q, QuerySet

from apps.accounts import services as accounts
from apps.core.visibility import audience_for
from apps.jobs import selectors as jobs
from apps.jobs.models import Job
from apps.profiles import selectors as profiles
from apps.profiles.models import FounderProfile
from apps.startups import selectors as startups
from apps.startups.models import Startup

SNIPPET = 220
JOBS_PER_CARD = 3
SORTS = {
    "newest": ("-created_at", "id"),
    "name": ("name", "id"),
}
PEOPLE_SORTS = {
    "newest": ("-created_at", "id"),
    "name": ("full_name", "id"),
}


def _not_private(group: str) -> Q:
    """A group is shown unless it was set to private; a group never set counts as not private."""
    key = f"visibility__{group}"
    return Q(**{f"{key}__isnull": True}) | ~Q(**{key: "private"})


def _snippet(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= SNIPPET else text[: SNIPPET - 1].rstrip() + "…"


def _page(queryset: QuerySet[Any], page: int, size: int) -> tuple[list[Any], dict[str, int]]:
    count = queryset.count()
    pages = max(1, -(-count // size))
    page = min(max(page, 1), pages)
    rows = list(queryset[(page - 1) * size : page * size])
    return rows, {"count": count, "page": page, "page_size": size, "pages": pages}


def browse_startups(
    viewer: Any,
    *,
    q: str = "",
    country: str = "",
    city: str = "",
    sector: str = "",
    stage: str = "",
    hiring: bool = False,
    sort: str = "newest",
    page: int = 1,
    page_size: int = 12,
) -> dict[str, Any]:
    live = jobs.live_jobs().filter(startup_id=OuterRef("pk"))
    queryset = (
        Startup.objects.filter(owner_id__in=accounts.active_user_ids())
        # Startups that keep even their basics private stay out, except from their owner.
        .filter(Q(owner_id=viewer.pk) | _not_private("basics"))
        .select_related("sector", "stage")
        .prefetch_related("members", "traction")
    )
    if country:
        queryset = queryset.filter(country=country.upper())
    if city:
        queryset = queryset.filter(city__icontains=city)
    if sector:
        queryset = queryset.filter(sector__slug=sector)
    if stage:
        queryset = queryset.filter(stage__slug=stage)
    if hiring:
        queryset = queryset.filter(Exists(live))
    if q:
        queryset = queryset.filter(
            Q(name__icontains=q)
            | Q(pitch__icontains=q)
            | Q(city__icontains=q)
            | Q(sector__name__icontains=q)
            | (Q(description__icontains=q) & _not_private("description"))
        )
    queryset = queryset.order_by(F("featured_at").desc(nulls_last=True), *SORTS[sort])
    rows, meta = _page(queryset, page, page_size)

    open_jobs: dict[Any, list[Job]] = {}
    for job in (
        jobs.live_jobs().filter(startup_id__in=[s.pk for s in rows]).order_by("-published_at")
    ):
        open_jobs.setdefault(job.startup_id, []).append(job)

    results = []
    for startup in rows:
        view = startups.project_startup(startup, audience_for(viewer, startups.team_ids(startup)))
        if view is None:
            continue
        listed = open_jobs.get(startup.pk, [])
        results.append(
            {
                "id": startup.pk,
                "slug": startup.slug,
                "name": view["name"],
                "pitch": view.get("pitch", ""),
                "logo": view.get("logo"),
                "sector": view.get("sector"),
                "stage": view.get("stage"),
                "country": view.get("country", ""),
                "city": view.get("city", ""),
                "year_founded": view.get("year_founded"),
                "description": _snippet(view.get("description", "")),
                "website_url": view.get("website_url", ""),
                "pitch_deck_url": view.get("pitch_deck_url", ""),
                "featured": view["featured"],
                "traction": view["traction"],
                "open_jobs_count": len(listed),
                "open_jobs": [{"id": j.pk, "title": j.title} for j in listed[:JOBS_PER_CARD]],
            }
        )
    return {"results": results, **meta}


def browse_people(
    viewer: Any,
    *,
    q: str = "",
    country: str = "",
    skill: str = "",
    sort: str = "newest",
    page: int = 1,
    page_size: int = 12,
) -> dict[str, Any]:
    queryset = FounderProfile.objects.filter(user_id__in=accounts.active_user_ids())
    if country:
        queryset = queryset.filter(country=country.upper())
    if skill:
        queryset = queryset.filter(skills__slug=skill)
    if q:
        queryset = queryset.filter(
            Q(full_name__icontains=q) | Q(headline__icontains=q) | Q(city__icontains=q)
        )
    queryset = queryset.distinct().prefetch_related("skills").order_by(*PEOPLE_SORTS[sort])
    rows, meta = _page(queryset, page, page_size)

    results = []
    for profile in rows:
        view = profiles.project_profile(profile, audience_for(viewer, {profile.user_id}))
        if view is None:
            continue
        results.append(
            {
                "id": profile.user_id,
                "slug": profile.slug,
                "name": view["full_name"],
                "headline": view.get("headline", ""),
                "photo": view.get("photo"),
                "city": view.get("city", ""),
                "country": view.get("country", ""),
                "skills": view.get("skills", []),
            }
        )
    return {"results": results, **meta}
