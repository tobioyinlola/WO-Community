"""Applying to a job inside the community, and the poster's and admins' handling of it."""

from typing import Any
from uuid import UUID

from django.db import IntegrityError, transaction
from django.db.models import Q, QuerySet
from django.utils import timezone
from rest_framework import exceptions

from apps.audit import services as audit
from apps.core.errors import ConflictError
from apps.jobs import selectors
from apps.jobs.models import APPLICATION_STATUSES, Job, JobApplication

DECISIONS = ("reviewing", "shortlisted", "rejected", "hired")
NOTE_MAX = 2000


def _clean_link(link: str) -> str:
    link = link.strip()
    if link and not link.lower().startswith(("https://", "http://")):
        raise exceptions.ValidationError({"link": ["Use a full link that starts with https://."]})
    return link


def apply(*, user_id: UUID, job_id: UUID, note: str, link: str = "") -> JobApplication:
    """Apply to a job on the board. One application per member per job."""
    job = selectors.get_visible(user_id, job_id)
    if job.poster_id == user_id:
        raise exceptions.PermissionDenied("You cannot apply to your own job.")
    if not selectors.live_jobs().filter(pk=job.pk).exists():
        raise ConflictError("This job is no longer taking applications.", code="job_closed")
    note = note.strip()
    if not note:
        raise exceptions.ValidationError({"note": ["Tell them a little about yourself."]})
    if len(note) > NOTE_MAX:
        raise exceptions.ValidationError({"note": [f"Keep it under {NOTE_MAX} characters."]})
    link = _clean_link(link)
    try:
        with transaction.atomic():
            return JobApplication.objects.create(
                job=job, applicant_id=user_id, note=note, link=link
            )
    except IntegrityError as exc:
        raise ConflictError("You have already applied.", code="already_applied") from exc


def mine(user_id: UUID, job_id: UUID) -> JobApplication | None:
    return JobApplication.objects.filter(job_id=job_id, applicant_id=user_id).first()


def withdraw(*, user_id: UUID, application_id: UUID) -> JobApplication:
    application = JobApplication.objects.filter(pk=application_id, applicant_id=user_id).first()
    if application is None:
        raise exceptions.NotFound()
    if application.status in ("hired", "rejected"):
        raise ConflictError("This application has already been decided.", code="decided")
    application.status = JobApplication.Status.WITHDRAWN
    application.save(update_fields=["status", "updated_at"])
    return application


def for_job(job_id: UUID) -> QuerySet[JobApplication]:
    return JobApplication.objects.filter(job_id=job_id).order_by("-created_at", "-id")


def admin_queryset(*, status: str, job_id: UUID | None, q: str) -> QuerySet[JobApplication]:
    queryset = JobApplication.objects.select_related("job")
    if status:
        queryset = queryset.filter(status=status)
    if job_id:
        queryset = queryset.filter(job_id=job_id)
    if q:
        queryset = queryset.filter(
            Q(job__title__icontains=q)
            | Q(job__organisation__icontains=q)
            | Q(applicant__email__icontains=q)
            | Q(applicant__founder_profile__full_name__icontains=q)
        )
    return queryset.order_by("-created_at", "-id")


def decide(
    *, actor: Any, application_id: UUID, status: str, note: str = "", ip: str = ""
) -> JobApplication:
    """The poster, or an admin, moves an application along."""
    if status not in DECISIONS:
        raise exceptions.ValidationError({"status": ["Choose a valid status."]})
    application = JobApplication.objects.select_related("job").filter(pk=application_id).first()
    if application is None:
        raise exceptions.NotFound()
    is_poster = application.job.poster_id == actor.pk
    if not is_poster and not can_moderate(actor):
        raise exceptions.NotFound()
    if application.status == JobApplication.Status.WITHDRAWN:
        raise ConflictError("The applicant withdrew this application.", code="withdrawn")
    application.status = status
    application.decided_by = actor
    application.decided_at = timezone.now()
    application.decision_note = note.strip()[:500]
    application.save(
        update_fields=["status", "decided_by", "decided_at", "decision_note", "updated_at"]
    )
    audit.record(
        actor=actor,
        action=f"job_application.{status}",
        target_type="job_application",
        target_id=application.pk,
        reason=note.strip()[:500],
        ip=ip,
    )
    return application


def can_moderate(actor: Any) -> bool:
    from apps.core.rbac import permissions_for

    return "jobs.moderate" in permissions_for(actor.role_names())


def counts() -> dict[str, int]:
    out = dict.fromkeys(APPLICATION_STATUSES, 0)
    for (status,) in JobApplication.objects.values_list("status").order_by():
        out[status] += 1
    return out


def job_titles(ids: set[UUID]) -> dict[UUID, Job]:
    return {j.pk: j for j in Job.objects.filter(pk__in=ids)}
