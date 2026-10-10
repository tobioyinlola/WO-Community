from typing import Any

import structlog
from celery import Task
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)


class BaseTask(Task):
    """Bounded retries with jittered backoff and a dead letter record.

    Tasks receive identifiers, not objects, and must be idempotent: the broker
    may deliver a message more than once.
    """

    autoretry_for = (Exception,)
    max_retries = 5
    retry_backoff = True
    retry_backoff_max = 600
    retry_jitter = True

    def before_start(self, task_id: str, args: tuple, kwargs: dict) -> None:
        structlog.contextvars.bind_contextvars(task_id=task_id, task_name=self.name)

    def on_failure(
        self, exc: Exception, task_id: str, args: tuple, kwargs: dict, einfo: Any
    ) -> None:
        from apps.core.models import FailedTask

        FailedTask.objects.create(
            task_name=self.name,
            task_id=task_id,
            queue=(getattr(self.request, "delivery_info", None) or {}).get("routing_key", ""),
            args=list(args),
            kwargs=dict(kwargs),
            exception=str(exc)[:4000],
        )
        logger.error("task_failed", extra={"task": self.name, "task_id": task_id})
