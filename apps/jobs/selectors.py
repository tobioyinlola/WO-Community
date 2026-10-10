"""Read side of the jobs board: who may see which job, filters, and view shapes."""

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from django.conf import settings
from django.contrib.postgres.search import SearchQuery, TrigramWordSimilarity
from django.db.models import Q, QuerySet
from django.db.models.functions import Greatest
from django.utils import timezone
from rest_framework import exceptions

from apps.accounts import services as accounts
from apps.core.keyset import paginate
from apps.jobs.models import Job, SavedJob
from apps.profiles import selectors as profiles
from apps.startups import selectors as startups

MIN_SIMILARITY = 0.35  # job titles are short phrases, so a typo costs more similarity


def live_jobs() -> QuerySet[Job]:
    """Jobs on the board right now: published, not lapsed, poster still an active member."""
    return Job.objects.filter(
        status=Job.Status.PUBLISHED,
        expires_at__gt=timezone.now(),
        poster_id__in=accounts.active_user_ids(),
    )


def filter_jobs(
    queryset: QuerySet[Job],
    *,
    q: str = "",
    type: str = "",  # noqa: A002  # the public filter name
    remote: bool | None = None,
    startup_id: UUID | None = None,
    location: str = "",
    posted_within_days: int | None = None,
) -> QuerySet[Job]:
    if type:
        queryset = queryset.filter(type=type)
    if remote is not None:
        queryset = queryset.filter(remote=remote)
    if startup_id:
        queryset = queryset.filter(startup_id=startup_id)
    if location:
        queryset = queryset.filter(location__icontains=location)
    if posted_within_days:
        queryset = queryset.filter(
            published_at__gte=timezone.now() - timedelta(days=posted_within_days)
        )
    if q:
        query = SearchQuery(q, search_type="websearch", config="simple")
        condition = Q(search_vector=query) | Q(title__icontains=q) | Q(organisation__icontains=q)
        # Quotes and exclusions mean exact full-text rules, so typo tolerance would undo them.
        if not ('"' in q or any(term.startswith("-") for term in q.split())):
            queryset = queryset.annotate(
                similarity=Greatest(
                    TrigramWordSimilarity(q, "title"), TrigramWordSimilarity(q, "organisation")
                )
            )
            condition |= Q(similarity__gte=MIN_SIMILARITY)
        queryset = queryset.filter(condition)
    return queryset


def alert_matches(filters: dict[str, Any], *, since: datetime) -> QuerySet[Job]:
    """Live jobs published after ``since`` that fit an alert's filters."""
    return filter_jobs(
        live_jobs().filter(published_at__gt=since),
        q=filters.get("q", ""),
        type=filters.get("type", ""),
        remote=filters.get("remote"),
        startup_id=UUID(filters["startup_id"]) if filters.get("startup_id") else None,
        location=filters.get("location", ""),
    )


# --- views ---


def _views(viewer: Any, jobs: list[Job], *, public: bool = False) -> list[dict[str, Any]]:
    member_posters = [j.poster_id for j in jobs if j.source == Job.Source.MEMBER]
    cards = {} if public else profiles.cards_for(viewer, member_posters)
    startup_cards = startups.cards_for(viewer, [j.startup_id for j in jobs if j.startup_id])
    saved: set[UUID] = set()
    if not public:
        saved = set(
            SavedJob.objects.filter(user_id=viewer.pk, job_id__in=[j.pk for j in jobs]).values_list(
                "job_id", flat=True
            )
        )
    views = []
    for job in jobs:
        apply: dict[str, Any] = {"method": job.apply_method}
        if not public or job.apply_method == "url":
            apply["target"] = job.apply_target
        view: dict[str, Any] = {
            "id": job.pk,
            "slug": job.slug,
            "title": job.title,
            "type": job.type,
            "organisation": job.organisation,
            "startup": startup_cards.get(job.startup_id) if job.startup_id else None,
            "location": job.location,
            "remote": job.remote,
            "description": job.description,
            "requirements": job.requirements,
            "compensation": job.compensation,
            "apply": apply,
            "deadline": job.deadline,
            "status": job.status,
            "origin": job.source,
            "published_at": job.published_at,
            "expires_at": job.expires_at,
            "created_at": job.created_at,
            "edited_at": job.edited_at,
            "share_url": f"{settings.FRONTEND_BASE_URL}/jobs/{job.slug}",
        }
        if not public:
            mine = job.poster_id == viewer.pk
            view.update(
                poster=cards.get(job.poster_id) if job.source == Job.Source.MEMBER else None,
                mine=mine,
                saved=job.pk in saved,
                review_note=job.review_note if mine else "",
            )
        views.append(view)
    return views


def board(viewer: Any, *, cursor: str, limit: int, **filters: Any) -> dict[str, Any]:
    queryset = filter_jobs(live_jobs(), **filters)
    rows, next_cursor = paginate(
        queryset, fields=("published_at", "id"), sort="jobs", cursor=cursor, limit=limit
    )
    return {"results": _views(viewer, rows), "next_cursor": next_cursor}


def get_visible(viewer_id: UUID, job_id: UUID) -> Job:
    """A job the member may open: live ones, and the poster's own in any state but removed."""
    job = Job.objects.filter(pk=job_id).first()
    if job is None:
        raise exceptions.NotFound()
    if job.poster_id == viewer_id and job.status != Job.Status.REMOVED:
        return job
    if not live_jobs().filter(pk=job_id).exists():
        raise exceptions.NotFound()
    return job


def detail(viewer: Any, job_id: UUID) -> tuple[Job, dict[str, Any]]:
    job = get_visible(viewer.pk, job_id)
    return job, _views(viewer, [job])[0]


def mine(viewer: Any, *, cursor: str, limit: int) -> dict[str, Any]:
    queryset = Job.objects.filter(poster_id=viewer.pk).exclude(status=Job.Status.REMOVED)
    rows, next_cursor = paginate(
        queryset, fields=("created_at", "id"), sort="jobs-mine", cursor=cursor, limit=limit
    )
    return {"results": _views(viewer, rows), "next_cursor": next_cursor}


def saved(viewer: Any, *, cursor: str, limit: int) -> dict[str, Any]:
    """Saved jobs newest save first, including ones that have since ended (flagged by status)."""
    queryset = SavedJob.objects.filter(
        user_id=viewer.pk,
        job__poster_id__in=accounts.active_user_ids(),
    ).exclude(job__status__in=[Job.Status.REMOVED, Job.Status.PENDING, Job.Status.REJECTED])
    rows, next_cursor = paginate(
        queryset.select_related("job"),
        fields=("created_at", "id"),
        sort="jobs-saved",
        cursor=cursor,
        limit=limit,
    )
    return {"results": _views(viewer, [r.job for r in rows]), "next_cursor": next_cursor}


# --- public ---


def public_board(*, cursor: str, limit: int, **filters: Any) -> dict[str, Any]:
    queryset = filter_jobs(live_jobs(), **filters)
    rows, next_cursor = paginate(
        queryset, fields=("published_at", "id"), sort="public-jobs", cursor=cursor, limit=limit
    )
    return {"results": _public_summaries(rows), "next_cursor": next_cursor}


def _public_summaries(jobs: list[Job]) -> list[dict[str, Any]]:
    return [
        {
            "slug": v["slug"],
            "title": v["title"],
            "type": v["type"],
            "organisation": v["organisation"],
            "startup": v["startup"],
            "location": v["location"],
            "remote": v["remote"],
            "published_at": v["published_at"],
            "expires_at": v["expires_at"],
        }
        for v in _views(None, jobs, public=True)
    ]


def public_detail(slug: str) -> dict[str, Any]:
    job = live_jobs().filter(slug=slug).first()
    if job is None:
        raise exceptions.NotFound()
    view = _views(None, [job], public=True)[0]
    text = job.description_text
    logo = (view["startup"] or {}).get("logo")
    view["open_graph"] = {
        "title": job.title,
        "description": text if len(text) <= 200 else text[:199] + "…",
        "url": view["share_url"],
        "type": "article",
        "image": logo["large"] if logo else None,
    }
    return view


def public_sitemap() -> list[dict[str, Any]]:
    rows = live_jobs().order_by("-published_at", "-id").values("slug", "updated_at")[:5000]
    return [dict(row) for row in rows]


# --- admin ---


def pending_count() -> int:
    return Job.objects.filter(status=Job.Status.PENDING).count()


def admin_queryset(*, status: str, origin: str, q: str) -> QuerySet[Job]:
    queryset = Job.objects.all()
    if status:
        queryset = queryset.filter(status=status)
    if origin:
        queryset = queryset.filter(source=origin)
    if q:
        queryset = queryset.filter(Q(title__icontains=q) | Q(organisation__icontains=q))
    return queryset.order_by("created_at", "id")


def admin_views(actor: Any, jobs: list[Job]) -> list[dict[str, Any]]:
    views = _views(actor, jobs)
    for job, view in zip(jobs, views, strict=True):
        view.update(
            poster_id=job.poster_id,
            reviewed_by=job.reviewed_by_id,
            reviewed_at=job.reviewed_at,
            review_note=job.review_note,
        )
    return views
