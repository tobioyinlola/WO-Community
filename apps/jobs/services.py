"""Public commands of the jobs board: posting, review, lifecycle, saving and alerts."""

import secrets
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from uuid import UUID

import structlog
from django.contrib.postgres.search import SearchVector
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.text import slugify
from rest_framework import exceptions

from apps.accounts import services as accounts
from apps.analytics import services as analytics
from apps.audit import services as audit
from apps.core import etag, ratelimit
from apps.core import events as domain_events
from apps.core.text import clean_url, plain, rich_post, text_of
from apps.integrations.cdn import get_cache_purger
from apps.jobs import events
from apps.jobs.models import (
    JOB_TYPES,
    Job,
    JobAlert,
    JobSettings,
    SavedJob,
)
from apps.startups import selectors as startups

logger = structlog.get_logger(__name__)

MAX_DESCRIPTION_TEXT = 5000
MAX_REQUIREMENTS_TEXT = 3000
MAX_SAVED = 200
MAX_ALERTS = 5
MAX_DEADLINE_DAYS = 365
JOBS_PER_DAY = 5
WARN_BEFORE = timedelta(days=3)
PUBLIC_API = "/api/v1/public/jobs"
ALERT_FILTERS = ("q", "type", "remote", "startup_id", "location")


class NotFound(exceptions.NotFound):
    default_detail = "Not found."


class Conflict(exceptions.APIException):
    status_code = 409
    default_code = "conflict"


class Forbidden(exceptions.PermissionDenied):
    default_detail = "You cannot change this."


# --- helpers ---


def _invalid(field: str, message: str) -> exceptions.ValidationError:
    return exceptions.ValidationError({field: [message]})


def _slug(title: str) -> str:
    return f"{slugify(title)[:60] or 'job'}-{secrets.token_hex(3)}"


def _clean_rich(value: str, field: str, limit: int, *, required: bool) -> tuple[str, str]:
    html = rich_post(value)
    text = text_of(html)
    if required and not text:
        raise _invalid(field, "This field may not be blank.")
    if len(text) > limit:
        raise _invalid(field, f"Up to {limit} characters.")
    return html, text


def _clean_apply(method: str, target: str) -> str:
    target = target.strip()
    if method == "url":
        try:
            cleaned = clean_url(target)
        except exceptions.ValidationError as exc:
            raise _invalid("apply_target", " ".join(str(m) for m in exc.detail)) from exc
        if not cleaned:
            raise _invalid("apply_target", "Enter a full https:// link.")
        return cleaned
    try:
        validate_email(target)
    except Exception as exc:
        raise _invalid("apply_target", "Enter a valid email address.") from exc
    return target.lower()


def _check_deadline(deadline: date | None) -> None:
    if deadline is None:
        return
    today = timezone.now().date()
    if deadline < today:
        raise _invalid("deadline", "The deadline cannot be in the past.")
    if deadline > today + timedelta(days=MAX_DEADLINE_DAYS):
        raise _invalid("deadline", "The deadline is too far away.")


def _expiry(deadline: date | None, now: datetime) -> datetime:
    """When a job lapses: the end of its deadline day, or the default duration from now."""
    if deadline is not None:
        return datetime.combine(deadline, time.max, tzinfo=UTC)
    return now + timedelta(days=JobSettings.load().default_duration_days)


def _index(job: Job) -> None:
    Job.objects.filter(pk=job.pk).update(
        search_vector=SearchVector("title", weight="A", config="simple")
        + SearchVector("organisation", "location", weight="B", config="simple")
        + SearchVector("description_text", weight="C", config="simple")
    )


def _purge_cdn(job: Job) -> None:
    try:
        get_cache_purger().purge([PUBLIC_API, f"{PUBLIC_API}/{job.slug}", f"{PUBLIC_API}/sitemap"])
    except Exception:  # the public pages expire by themselves
        logger.warning("cdn_purge_failed", job_id=str(job.pk))


def _lock(job_id: UUID) -> Job:
    job = Job.objects.select_for_update().filter(pk=job_id).first()
    if job is None:
        raise NotFound()
    return job


def _lock_own(user_id: UUID, job_id: UUID) -> Job:
    job = _lock(job_id)
    if job.poster_id != user_id or job.status == Job.Status.REMOVED:
        raise NotFound()  # someone else's job is not even confirmed to exist
    return job


def _publish(job: Job, now: datetime) -> None:
    job.status = Job.Status.PUBLISHED
    job.published_at = job.published_at or now
    job.expires_at = _expiry(job.deadline, now)
    job.expiry_warned_at = None
    job.closed_at = None


def _announce_published(job: Job) -> None:
    domain_events.publish(events.JobPublished(job_id=str(job.pk)))
    transaction.on_commit(lambda: _purge_cdn(job))


# --- creating and editing ---


def _apply_fields(job: Job, data: dict[str, Any], user_id: UUID, *, is_admin: bool) -> None:
    """Copy validated fields onto the job. Raises ``ValidationError`` for anything wrong."""
    if "title" in data:
        job.title = plain(data["title"])
        if not job.title:
            raise _invalid("title", "This field may not be blank.")
    if "type" in data:
        if data["type"] not in JOB_TYPES:
            raise _invalid("type", "Choose a type from the list.")
        job.type = data["type"]
    for field in ("location", "compensation"):
        if field in data:
            setattr(job, field, plain(data[field]))
    if "remote" in data:
        job.remote = bool(data["remote"])
    if "description" in data:
        job.description, job.description_text = _clean_rich(
            data["description"], "description", MAX_DESCRIPTION_TEXT, required=True
        )
    if "requirements" in data:
        job.requirements, _ = _clean_rich(
            data["requirements"], "requirements", MAX_REQUIREMENTS_TEXT, required=False
        )
    if "organisation" in data:
        job.organisation = plain(data["organisation"])
    if "startup_id" in data:
        startup_id = data["startup_id"]
        if startup_id is not None and not is_admin:
            if startup_id not in startups.startup_ids_of_member(user_id):
                raise _invalid("startup_id", "You can only post for a startup you belong to.")
        job.startup_id = startup_id
    if "apply_method" in data or "apply_target" in data:
        method = data.get("apply_method", job.apply_method)
        target = data.get("apply_target", job.apply_target)
        if is_admin and method != "url":
            raise _invalid("apply_method", "Jobs added by admins need an external link.")
        job.apply_method, job.apply_target = method, _clean_apply(method, target)
    if "deadline" in data:
        _check_deadline(data["deadline"])
        job.deadline = data["deadline"]


def _check_complete(job: Job) -> None:
    if not job.startup_id and not job.organisation:
        raise _invalid("organisation", "Name the startup or the organisation that is hiring.")


def create_job(*, user_id: UUID, data: dict[str, Any], admin: bool = False) -> Job:
    """Post a job. Members' jobs wait for review unless the board is set to auto publish."""
    if not admin and ratelimit.hit(f"jobs:post:{user_id}", 86400) > JOBS_PER_DAY:
        raise exceptions.Throttled(wait=86400, detail="Daily limit for new jobs reached.")
    job = Job(
        poster_id=user_id,
        slug=_slug(data.get("title", "")),
        source=Job.Source.ADMIN if admin else Job.Source.MEMBER,
        status=Job.Status.PENDING,
    )
    _apply_fields(job, data, user_id, is_admin=admin)
    _check_complete(job)
    with transaction.atomic():
        now = timezone.now()
        if admin or not JobSettings.load().require_approval:
            _publish(job, now)
        job.save()
        _index(job)
        analytics.track("job_created", actor_id=user_id, properties={"job_type": job.type})
        if job.status == Job.Status.PUBLISHED:
            _announce_published(job)
    return job


def update_job(
    *, user_id: UUID, job_id: UUID, data: dict[str, Any], if_match: str | None, admin: bool = False
) -> Job:
    with transaction.atomic():
        job = _lock(job_id) if admin else _lock_own(user_id, job_id)
        if job.status in (Job.Status.CLOSED, Job.Status.EXPIRED, Job.Status.REJECTED):
            raise Conflict("Renew or repost this job before editing it.")
        if job.status == Job.Status.REMOVED:
            raise NotFound()
        etag.assert_matches(if_match, job)
        _apply_fields(job, data, user_id, is_admin=admin and job.source == Job.Source.ADMIN)
        _check_complete(job)
        if "deadline" in data and job.status == Job.Status.PUBLISHED:
            job.expires_at = _expiry(job.deadline, timezone.now())
            job.expiry_warned_at = None
        job.edited_at = timezone.now()
        job.save()
        _index(job)
        if job.status == Job.Status.PUBLISHED:
            transaction.on_commit(lambda: _purge_cdn(job))
    return job


# --- lifecycle ---


def close_job(*, user_id: UUID, job_id: UUID, admin: bool = False) -> Job:
    with transaction.atomic():
        job = _lock(job_id) if admin else _lock_own(user_id, job_id)
        if job.status not in (Job.Status.PUBLISHED, Job.Status.PENDING):
            raise Conflict("Only a pending or published job can be closed.")
        job.status = Job.Status.CLOSED
        job.closed_at = timezone.now()
        job.save(update_fields=["status", "closed_at", "updated_at"])
        transaction.on_commit(lambda: _purge_cdn(job))
    return job


def renew_job(*, user_id: UUID, job_id: UUID, deadline: date | None = None) -> Job:
    """Put a published, expired or closed job back on the board for another term."""
    with transaction.atomic():
        job = _lock_own(user_id, job_id)
        if job.status not in (Job.Status.PUBLISHED, Job.Status.EXPIRED, Job.Status.CLOSED):
            raise Conflict("This job cannot be renewed.")
        _check_deadline(deadline)
        job.deadline = deadline
        was_live = job.status == Job.Status.PUBLISHED
        _publish(job, timezone.now())
        job.save()
        if not was_live:
            _announce_published(job)
        else:
            transaction.on_commit(lambda: _purge_cdn(job))
    return job


# --- admin review ---


def review_job(*, actor: Any, job_id: UUID, decision: str, note: str = "", ip: str = "") -> Job:
    """Approve or reject a pending job; remove or unpublish a live one."""
    with transaction.atomic():
        job = _lock(job_id)
        now = timezone.now()
        clean_note = plain(note)
        if decision in ("approve", "reject"):
            if job.status != Job.Status.PENDING:
                raise Conflict("Only a pending job can be approved or rejected.")
            if decision == "reject" and not clean_note:
                raise _invalid("reason", "Say why the job was rejected.")
        elif decision == "unpublish":
            if job.status != Job.Status.PUBLISHED:
                raise Conflict("Only a published job can be unpublished.")
        elif decision == "remove":
            if job.status == Job.Status.REMOVED:
                raise Conflict("This job is already removed.")
        else:
            raise ValueError(decision)
        was_published = job.status == Job.Status.PUBLISHED
        job.reviewed_by, job.reviewed_at, job.review_note = actor, now, clean_note
        if decision == "approve":
            _publish(job, now)
        elif decision == "reject":
            job.status = Job.Status.REJECTED
        elif decision == "unpublish":
            job.status, job.closed_at = Job.Status.CLOSED, now
        else:
            job.status, job.closed_at = Job.Status.REMOVED, now
        job.save()
        audit.record(
            actor=actor,
            action=f"jobs.{decision}",
            target_type="job",
            target_id=job.pk,
            reason=clean_note,
            ip=ip,
        )
        if decision == "approve":
            _announce_published(job)
            domain_events.publish(events.JobReviewed(job_id=str(job.pk), approved=True, note=""))
        elif decision == "reject":
            domain_events.publish(
                events.JobReviewed(job_id=str(job.pk), approved=False, note=clean_note)
            )
        elif was_published:
            transaction.on_commit(lambda: _purge_cdn(job))
    return job


# --- scheduled work ---


def expire_due() -> int:
    """Close the books on jobs whose time is up."""
    now = timezone.now()
    due = list(Job.objects.filter(status=Job.Status.PUBLISHED, expires_at__lte=now))
    for job in due:
        Job.objects.filter(pk=job.pk, status=Job.Status.PUBLISHED).update(
            status=Job.Status.EXPIRED, closed_at=now, updated_at=now
        )
        _purge_cdn(job)
    return len(due)


def warn_expiring() -> int:
    """Tell posters their job lapses within three days, once per term."""
    now = timezone.now()
    soon = Job.objects.filter(
        status=Job.Status.PUBLISHED,
        expires_at__gt=now,
        expires_at__lte=now + WARN_BEFORE,
        expiry_warned_at__isnull=True,
    )
    count = 0
    for job in soon:
        with transaction.atomic():
            claimed = Job.objects.filter(pk=job.pk, expiry_warned_at__isnull=True).update(
                expiry_warned_at=now
            )
            if claimed:
                domain_events.publish(events.JobExpiring(job_id=str(job.pk)))
                count += 1
    return count


# --- saving ---


def save_job(*, user_id: UUID, job_id: UUID) -> bool:
    """Save a job to come back to. Returns False if it was already saved."""
    from apps.jobs import selectors

    selectors.get_visible(user_id, job_id)  # raises NotFound for anything the member cannot see
    if SavedJob.objects.filter(user_id=user_id).count() >= MAX_SAVED:
        raise _invalid("job", f"You can save up to {MAX_SAVED} jobs.")
    _, created = SavedJob.objects.get_or_create(user_id=user_id, job_id=job_id)
    return created


def unsave_job(*, user_id: UUID, job_id: UUID) -> None:
    SavedJob.objects.filter(user_id=user_id, job_id=job_id).delete()


# --- alerts ---


def clean_filters(raw: dict[str, Any], user_id: UUID) -> dict[str, Any]:
    filters = {k: v for k, v in raw.items() if k in ALERT_FILTERS and v not in (None, "")}
    if "type" in filters and filters["type"] not in JOB_TYPES:
        raise _invalid("filters", "Unknown job type.")
    if "q" in filters:
        filters["q"] = plain(str(filters["q"]))[:100]
    if "location" in filters:
        filters["location"] = plain(str(filters["location"]))[:120]
    if "startup_id" in filters:
        filters["startup_id"] = str(filters["startup_id"])
    return filters


def create_alert(*, user_id: UUID, filters: dict[str, Any], frequency: str) -> JobAlert:
    cleaned = clean_filters(filters, user_id)
    with transaction.atomic():
        if JobAlert.objects.select_for_update().filter(user_id=user_id).count() >= MAX_ALERTS:
            raise _invalid("filters", f"You can have up to {MAX_ALERTS} job alerts.")
        return JobAlert.objects.create(user_id=user_id, filters=cleaned, frequency=frequency)


def delete_alert(*, user_id: UUID, alert_id: UUID) -> None:
    deleted, _ = JobAlert.objects.filter(pk=alert_id, user_id=user_id).delete()
    if not deleted:
        raise NotFound()


def matches(job: Job, filters: dict[str, Any]) -> bool:
    """Whether a job fits an alert's filters (the same rules as the board's, in memory)."""
    if "type" in filters and job.type != filters["type"]:
        return False
    if "remote" in filters and job.remote != bool(filters["remote"]):
        return False
    if "startup_id" in filters and str(job.startup_id) != filters["startup_id"]:
        return False
    if "location" in filters and filters["location"].lower() not in job.location.lower():
        return False
    if "q" in filters:
        haystack = f"{job.title} {job.organisation} {job.location} {job.description_text}".lower()
        return all(word in haystack for word in filters["q"].lower().split())
    return True


def alert_instantly(job_id: UUID) -> int:
    """Tell members with a matching instant alert about a new job. One notice per member."""
    from apps.notifications import notify

    job = Job.objects.filter(pk=job_id, status=Job.Status.PUBLISHED).first()
    if job is None:
        return 0
    told: set[UUID] = set()
    for alert in JobAlert.objects.filter(frequency=JobAlert.Frequency.INSTANT).iterator():
        if alert.user_id in told or alert.user_id == job.poster_id:
            continue
        if matches(job, alert.filters):
            told.add(alert.user_id)
            notify.notify(
                alert.user_id,
                "job_alert",
                {"job_id": str(job.pk), "title": job.title},
                dedupe_key=f"job-alert:{job.pk}",
            )
    return len(told)


def send_digests() -> int:
    """One notice per daily alert that has new matching jobs since it last fired."""
    from apps.jobs import selectors
    from apps.notifications import notify

    now = timezone.now()
    due = JobAlert.objects.filter(frequency=JobAlert.Frequency.DAILY).filter(
        Q(last_sent_at__isnull=True, created_at__lte=now - timedelta(days=1))
        | Q(last_sent_at__lte=now - timedelta(days=1))
    )
    sent = 0
    for alert in due:
        since = alert.last_sent_at or alert.created_at
        count = selectors.alert_matches(alert.filters, since=since).count()
        JobAlert.objects.filter(pk=alert.pk).update(last_sent_at=now)
        if count and accounts.is_active(alert.user_id):
            notify.notify(
                alert.user_id,
                "job_digest",
                {"count": count, "alert_id": str(alert.pk)},
                dedupe_key=f"job-digest:{alert.pk}:{now:%Y%m%d}",
            )
            sent += 1
    return sent
