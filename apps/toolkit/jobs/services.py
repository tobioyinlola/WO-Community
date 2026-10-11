"""Starting, running, cancelling and reading jobs.

A job is created inside the request, handed to a worker after the transaction commits, and
polled by the client. Handlers are registered by the module that owns the kind of work; they
receive a ``JobContext`` and return a small reference to what they made.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import structlog
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import exceptions

from apps.toolkit.jobs.models import AIJob
from apps.toolkit.ventures.models import Venture

logger = structlog.get_logger(__name__)

MAX_ATTEMPTS = 3
STUCK_AFTER = timedelta(minutes=30)


class JobFailed(Exception):
    """A step failed in a way that retrying will not fix. ``detail`` is shown to the member."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(code)
        self.code = code
        self.detail = detail[:300]


class JobCancelled(Exception):
    pass


class TransientError(Exception):
    """Something that may work if tried again shortly (a provider timeout, say)."""


@dataclass
class Handler:
    fn: Callable[["JobContext"], dict[str, Any]]
    queue: str


_handlers: dict[str, Handler] = {}


def register(kind: str, fn: Callable[["JobContext"], dict[str, Any]], *, queue: str = "ai") -> None:
    _handlers[kind] = Handler(fn, queue)


def registered_kinds() -> list[str]:
    return sorted(_handlers)


class JobContext:
    def __init__(self, job: AIJob) -> None:
        self.job = job
        self.payload: dict[str, Any] = dict(job.payload)
        self.owner_id: UUID = job.owner_id
        self.venture: Venture | None = job.venture

    def progress(self, percent: int, label: str = "") -> None:
        """Report where the job is, and stop it here if the member cancelled."""
        AIJob.objects.filter(pk=self.job.pk).update(
            progress=max(0, min(100, percent)),
            step_label=label[:120],
            updated_at=timezone.now(),
        )
        self.check_cancel()

    def check_cancel(self) -> None:
        if AIJob.objects.filter(pk=self.job.pk, cancel_requested=True).exists():
            raise JobCancelled()


# --- starting ---


def start(
    *,
    owner_id: UUID,
    kind: str,
    venture: Venture | None = None,
    payload: dict[str, Any] | None = None,
    idempotency_key: str = "",
    group_id: UUID | None = None,
) -> tuple[AIJob, bool]:
    """Queue a job. Returns it and whether it is new: a repeated key returns the same job."""
    if kind not in _handlers:
        raise exceptions.ValidationError({"kind": ["Unknown kind of job."]})
    key = idempotency_key.strip()[:80]
    if key:
        existing = AIJob.objects.filter(owner_id=owner_id, kind=kind, idempotency_key=key).first()
        if existing is not None:
            return existing, False
    try:
        with transaction.atomic():
            job = AIJob.objects.create(
                owner_id=owner_id,
                venture=venture,
                kind=kind,
                payload=payload or {},
                idempotency_key=key,
                group_id=group_id,
            )
    except IntegrityError:  # the same key arrived twice at once
        return AIJob.objects.get(owner_id=owner_id, kind=kind, idempotency_key=key), False
    transaction.on_commit(lambda: dispatch(job.pk))
    return job, True


def dispatch(job_id: UUID) -> None:
    from apps.toolkit.jobs import tasks

    job = AIJob.objects.filter(pk=job_id).only("kind").first()
    if job is None:
        return
    queue = _handlers[job.kind].queue
    task = tasks.run_export_job if queue == "exports" else tasks.run_ai_job
    task.apply_async(args=[str(job_id)], queue=queue)


def new_group() -> UUID:
    return uuid4()


# --- running (in a worker) ---


def run(job_id: UUID, *, final_attempt: bool = True) -> None:
    """Run one job. Safe to call twice: only a queued job is picked up."""
    with transaction.atomic():
        job = (
            AIJob.objects.select_for_update(of=("self",))
            .select_related("venture")
            .filter(pk=job_id, status=AIJob.Status.QUEUED)
            .first()
        )
        if job is None:
            return
        if job.cancel_requested:
            _finish(job, AIJob.Status.CANCELLED)
            return
        job.status = AIJob.Status.RUNNING
        job.started_at = job.started_at or timezone.now()
        job.attempts += 1
        job.save(update_fields=["status", "started_at", "attempts", "updated_at"])
    handler = _handlers[job.kind]
    try:
        result = handler.fn(JobContext(job))
    except JobCancelled:
        _finish(job, AIJob.Status.CANCELLED)
    except JobFailed as exc:
        _finish(job, AIJob.Status.FAILED, code=exc.code, detail=exc.detail)
    except TransientError:
        if final_attempt or job.attempts >= MAX_ATTEMPTS:
            _finish(
                job,
                AIJob.Status.FAILED,
                code="temporarily_unavailable",
                detail="The service is busy. Please try again in a few minutes.",
            )
        else:
            AIJob.objects.filter(pk=job.pk).update(status=AIJob.Status.QUEUED)
            raise
    except Exception:  # noqa: BLE001  # a job must always end in a state the member can see
        logger.exception("toolkit_job_crashed", job_id=str(job.pk), kind=job.kind)
        _finish(
            job,
            AIJob.Status.FAILED,
            code="internal_error",
            detail="Something went wrong on our side. Please try again.",
        )
    else:
        _finish(job, AIJob.Status.SUCCEEDED, result=result or {})


def _finish(
    job: AIJob,
    status: str,
    *,
    code: str = "",
    detail: str = "",
    result: dict[str, Any] | None = None,
) -> None:
    updates: dict[str, Any] = {
        "status": status,
        "finished_at": timezone.now(),
        "error_code": code,
        "error_detail": detail,
        "updated_at": timezone.now(),
    }
    if status == AIJob.Status.SUCCEEDED:
        updates.update(progress=100, result_ref=result or {}, step_label="")
    AIJob.objects.filter(pk=job.pk).update(**updates)
    for hook in _on_finish:
        try:
            hook(AIJob.objects.get(pk=job.pk))
        except Exception:  # noqa: BLE001  # a hook must never change how a job ended
            logger.exception("toolkit_job_hook_failed", job_id=str(job.pk))


_on_finish: list[Callable[[AIJob], None]] = []


def on_finish(hook: Callable[[AIJob], None]) -> None:
    """Called after any job ends, for modules that keep output states in step with jobs."""
    _on_finish.append(hook)


# --- controlling and reading ---


def cancel(job: AIJob) -> AIJob:
    with transaction.atomic():
        job = AIJob.objects.select_for_update().get(pk=job.pk)
        if job.status == AIJob.Status.QUEUED:
            job.cancel_requested = True
            job.save(update_fields=["cancel_requested", "updated_at"])
            _finish(job, AIJob.Status.CANCELLED)
        elif job.status == AIJob.Status.RUNNING:
            job.cancel_requested = True
            job.save(update_fields=["cancel_requested", "updated_at"])
    job.refresh_from_db()
    return job


def reap_stuck() -> int:
    """Fail jobs a worker abandoned (it died mid run), so nobody waits for ever."""
    cutoff = timezone.now() - STUCK_AFTER
    stuck = AIJob.objects.filter(status=AIJob.Status.RUNNING, updated_at__lt=cutoff)
    count = 0
    for job in stuck:
        _finish(
            job,
            AIJob.Status.FAILED,
            code="timed_out",
            detail="This took too long and was stopped. Please try again.",
        )
        count += 1
    return count


def view(job: AIJob) -> dict[str, Any]:
    return {
        "id": job.pk,
        "kind": job.kind,
        "venture_id": job.venture_id,
        "status": job.status,
        "progress": job.progress,
        "step_label": job.step_label,
        "result": job.result_ref,
        "error_code": job.error_code,
        "error_detail": job.error_detail,
        "group_id": job.group_id,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
    }


def owned(owner_id: UUID, job_id: UUID) -> AIJob | None:
    return AIJob.objects.filter(pk=job_id, owner_id=owner_id).first()
