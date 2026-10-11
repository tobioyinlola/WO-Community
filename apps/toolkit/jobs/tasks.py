from typing import Any
from uuid import UUID

from celery import shared_task

from apps.toolkit.jobs import services

MAX_RETRIES = 3


def _run(task: Any, job_id: str) -> None:
    try:
        services.run(UUID(job_id), final_attempt=task.request.retries >= MAX_RETRIES - 1)
    except services.TransientError as exc:
        raise task.retry(countdown=min(2 ** (task.request.retries + 1) * 10, 120)) from exc


@shared_task(
    bind=True,
    name="toolkit.run_ai_job",
    max_retries=MAX_RETRIES,
    soft_time_limit=1800,
    time_limit=1860,
)
def run_ai_job(self: Any, job_id: str) -> None:
    _run(self, job_id)


@shared_task(
    bind=True,
    name="toolkit.run_export_job",
    max_retries=MAX_RETRIES,
    soft_time_limit=600,
    time_limit=660,
)
def run_export_job(self: Any, job_id: str) -> None:
    _run(self, job_id)


@shared_task(name="toolkit.reap_stuck_jobs")
def reap_stuck_jobs() -> int:
    return services.reap_stuck()
