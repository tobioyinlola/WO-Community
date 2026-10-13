"""Generated documents: stored privately, listed to their owner, handed out by short signed links.

A file is never public and never linked from content. The link lasts ``EXPORT_URL_TTL`` seconds
and the file itself is deleted after ``EXPORT_RETENTION_DAYS`` (members can generate it again).
"""

from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import structlog
from django.conf import settings
from django.utils import timezone

from apps.integrations.storage import get_storage
from apps.integrations.storage.base import PRIVATE
from apps.toolkit.jobs.models import ExportFile
from apps.toolkit.ventures.models import Venture

logger = structlog.get_logger(__name__)


def store(
    *,
    venture: Venture,
    owner_id: UUID,
    kind: str,
    filename: str,
    content_type: str,
    data: bytes,
) -> ExportFile:
    key = f"toolkit/exports/{venture.pk}/{uuid4().hex}"
    get_storage().write(
        bucket=PRIVATE,
        key=key,
        data=data,
        content_type=content_type,
        cache_control="private, no-store",
    )
    return ExportFile.objects.create(
        owner_id=owner_id,
        venture=venture,
        kind=kind,
        filename=filename[:160],
        content_type=content_type,
        storage_key=key,
        size=len(data),
        expires_at=timezone.now() + timedelta(days=settings.EXPORT_RETENTION_DAYS),
    )


def owned(owner_id: UUID, export_id: UUID) -> ExportFile | None:
    return ExportFile.objects.filter(
        pk=export_id, owner_id=owner_id, expires_at__gt=timezone.now()
    ).first()


def view(file: ExportFile) -> dict[str, Any]:
    url = get_storage().presign_get(
        bucket=PRIVATE,
        key=file.storage_key,
        expires_in=settings.EXPORT_URL_TTL,
        filename=file.filename,
        content_type=file.content_type,
    )
    return {
        "id": file.pk,
        "kind": file.kind,
        "filename": file.filename,
        "content_type": file.content_type,
        "size": file.size,
        "expires_at": file.expires_at,
        "url": url,
        "url_expires_in": settings.EXPORT_URL_TTL,
    }


def result_of(file: ExportFile) -> dict[str, Any]:
    return {"type": "export", "id": str(file.pk)}


def purge_expired(now: Any = None) -> int:
    """Delete files past retention, from storage and from the table."""
    now = now or timezone.now()
    removed = 0
    for file in list(ExportFile.objects.filter(expires_at__lte=now)[:500]):
        get_storage().delete(bucket=PRIVATE, key=file.storage_key)
        file.delete()
        removed += 1
    return removed


def erase_for(venture: Venture) -> None:
    """Remove every stored file of a venture (called when the venture is erased)."""
    storage = get_storage()
    for file in ExportFile.objects.filter(venture=venture):
        storage.delete(bucket=PRIVATE, key=file.storage_key)


def export_listing(venture: Venture) -> list[dict[str, Any]]:
    """Generated documents still held, by name (the files themselves expire)."""
    return [
        {
            "kind": f.kind,
            "filename": f.filename,
            "size": f.size,
            "expires_at": f.expires_at.isoformat(),
        }
        for f in ExportFile.objects.filter(venture=venture)
    ]


def queue_gauges() -> Any:
    """Gauges for the toolkit job queue, read when Prometheus scrapes."""
    from prometheus_client.core import GaugeMetricFamily

    from apps.toolkit.jobs.models import AIJob

    waiting = AIJob.objects.filter(status="queued")
    oldest = waiting.order_by("created_at").values_list("created_at", flat=True).first()
    yield GaugeMetricFamily(
        "wo_toolkit_jobs_queued", "Toolkit jobs waiting for a worker", waiting.count()
    )
    yield GaugeMetricFamily(
        "wo_toolkit_jobs_running",
        "Toolkit jobs being worked on",
        AIJob.objects.filter(status="running").count(),
    )
    yield GaugeMetricFamily(
        "wo_toolkit_oldest_queued_seconds",
        "Age of the oldest waiting toolkit job",
        (timezone.now() - oldest).total_seconds() if oldest else 0,
    )
