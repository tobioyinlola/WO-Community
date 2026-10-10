from typing import Any
from uuid import UUID

import structlog
from celery import shared_task

from apps.core.models import OutboxEvent
from apps.jobs import services
from apps.jobs.models import Job
from apps.notifications import notify

logger = structlog.get_logger(__name__)


def _payload(event_id: str) -> dict[str, Any] | None:
    event = OutboxEvent.objects.filter(pk=event_id).first()
    if event is None:
        logger.warning("outbox_event_missing", event_id=event_id)
        return None
    return dict(event.payload)


@shared_task(name="jobs.send_instant_alerts")
def send_instant_alerts(event_id: str) -> None:
    data = _payload(event_id)
    if data is not None:
        services.alert_instantly(UUID(data["job_id"]))


@shared_task(name="jobs.notify_review")
def notify_review(event_id: str) -> None:
    data = _payload(event_id)
    job = Job.objects.filter(pk=data["job_id"]).first() if data else None
    if data is None or job is None:
        return
    if data["approved"]:
        notify.notify(
            job.poster_id,
            "job_approved",
            {"job_id": str(job.pk), "title": job.title},
            dedupe_key=f"{event_id}:approved",
        )
    else:
        notify.notify(
            job.poster_id,
            "job_rejected",
            {"job_id": str(job.pk), "title": job.title, "reason": data["note"]},
            dedupe_key=f"{event_id}:rejected",
        )


@shared_task(name="jobs.notify_expiring")
def notify_expiring(event_id: str) -> None:
    data = _payload(event_id)
    job = Job.objects.filter(pk=data["job_id"]).first() if data else None
    if job is None or job.status != Job.Status.PUBLISHED or job.expires_at is None:
        return
    notify.notify(
        job.poster_id,
        "job_expiring",
        {"job_id": str(job.pk), "title": job.title, "expires_at": job.expires_at.isoformat()},
        dedupe_key=f"{event_id}:expiring",
    )


@shared_task(name="jobs.expire_due")
def expire_due() -> int:
    return services.expire_due()


@shared_task(name="jobs.warn_expiring")
def warn_expiring() -> int:
    return services.warn_expiring()


@shared_task(name="jobs.send_digests")
def send_digests() -> int:
    return services.send_digests()
