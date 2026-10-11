"""Search for people and startups, as a member sees them.

Matching uses only fields in each item's ``basics`` group, and every hit goes through the same
projection as the profile and startup pages, so someone who hides their basics from members
cannot be found and nothing is matched on a field the searcher may not see. Typos are tolerated
through trigram word similarity. Jobs, courses, posts, mentors and events join the registry as
their modules arrive; events, news and courses are matched on title and text.
"""

from collections.abc import Callable
from typing import Any

from django.contrib.postgres.search import TrigramWordSimilarity
from django.db.models import Case, Q, When
from django.db.models.functions import Greatest
from django.utils import timezone

from apps.accounts import services as accounts
from apps.core.visibility import audience_for
from apps.editorial import selectors as editorial
from apps.events.models import Event
from apps.jobs import selectors as jobs
from apps.learning import selectors as learning
from apps.mentorship import selectors as mentorship
from apps.profiles import selectors as profiles
from apps.profiles.models import FounderProfile
from apps.startups import selectors as startups
from apps.startups.models import Startup
from apps.uploads import services as uploads

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


def _jobs(viewer: Any, query: str, limit: int) -> list[dict[str, Any]]:
    """Live jobs only; the board's own text matching, newest first."""
    rows = jobs.filter_jobs(jobs.live_jobs(), q=query).order_by("-published_at", "-id")[:limit]
    return [
        {
            "type": "job",
            "id": job.pk,
            "slug": job.slug,
            "title": job.title,
            "subtitle": job.organisation or job.location,
            "image": None,
        }
        for job in rows
    ]


def _mentors(viewer: Any, query: str, limit: int) -> list[dict[str, Any]]:
    """Listed mentors. A mentor who hides their name is found only by role, company or expertise."""
    needle = " ".join(query.lower().split())
    rows = list(
        mentorship.filter_mentors(mentorship.listed(), q=query).order_by("-approved_at", "-id")[
            : limit * OVERFETCH
        ]
    )
    cards = profiles.cards_for(viewer, [r.user_id for r in rows])
    hits: list[dict[str, Any]] = []
    for row in rows:
        card = cards[row.user_id]
        by_work = (
            needle in row.current_role.lower()
            or needle in row.company.lower()
            or needle in row.expertise
        )
        if card["hidden"] and not by_work:
            continue
        hits.append(
            {
                "type": "mentor",
                "id": row.user_id,
                "slug": card["slug"] or str(row.user_id),
                "title": card["name"],
                "subtitle": f"{row.current_role}, {row.company}",
                "image": card["photo"],
            }
        )
        if len(hits) == limit:
            break
    return hits


def _events(viewer: Any, query: str, limit: int) -> list[dict[str, Any]]:
    """Published events (not cancelled ones), soonest upcoming first and then the most recent."""
    now = timezone.now()
    rows = (
        Event.objects.filter(status=Event.Status.PUBLISHED)
        .filter(Q(title__icontains=query) | Q(description_text__icontains=query))
        .annotate(upcoming=Case(When(ends_at__gt=now, then=0), default=1))
        .order_by("upcoming", "starts_at", "id")[:limit]
    )
    return [
        {
            "type": "event",
            "id": event.pk,
            "slug": event.slug,
            "title": event.title,
            "subtitle": ", ".join(
                part for part in (event.starts_at.strftime("%d %b %Y"), event.location) if part
            ),
            "image": None,
        }
        for event in rows
    ]


def _news(viewer: Any, query: str, limit: int) -> list[dict[str, Any]]:
    """Published news, awards and announcements by title or text, newest first."""
    rows = (
        editorial.published()
        .filter(Q(title__icontains=query) | Q(body_text__icontains=query))
        .order_by("-published_at", "-id")[:limit]
    )
    return [
        {
            "type": "news",
            "id": item.pk,
            "slug": item.slug,
            "title": item.title,
            "subtitle": item.type,
            "image": uploads.image_urls(item.cover_key),
        }
        for item in rows
    ]


def _courses(viewer: Any, query: str, limit: int) -> list[dict[str, Any]]:
    """Published courses by title, instructor, category or description, newest first."""
    rows = (
        learning.published()
        .filter(
            Q(title__icontains=query)
            | Q(instructor__icontains=query)
            | Q(category__icontains=query)
            | Q(description_text__icontains=query)
        )
        .order_by("-published_at", "-id")[:limit]
    )
    return [
        {
            "type": "course",
            "id": course.pk,
            "slug": course.slug,
            "title": course.title,
            "subtitle": course.instructor,
            "image": uploads.image_urls(course.cover_key),
        }
        for course in rows
    ]


SEARCHERS: dict[str, Callable[[Any, str, int], list[dict[str, Any]]]] = {
    "members": _members,
    "startups": _startups,
    "jobs": _jobs,
    "mentors": _mentors,
    "events": _events,
    "news": _news,
    "courses": _courses,
}


def search(
    viewer: Any, query: str, kinds: list[str], limit: int
) -> dict[str, list[dict[str, Any]]]:
    return {kind: SEARCHERS[kind](viewer, query, limit) for kind in kinds}
