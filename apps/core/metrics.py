"""Prometheus metrics: request counts and latency, and gauges for the work queues.

Request metrics are recorded by the request middleware. The queue gauges are read from the
database when Prometheus scrapes, so they are always current and cost nothing between scrapes.
With several gunicorn workers set ``PROMETHEUS_MULTIPROC_DIR`` so every worker is counted.
"""

import os
from collections.abc import Callable, Iterator

from django.utils import timezone
from prometheus_client import (
    REGISTRY,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
    multiprocess,
)
from prometheus_client.core import GaugeMetricFamily, Metric

CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"

REQUESTS = Counter("wo_http_requests_total", "HTTP requests handled", ["method", "route", "status"])
LATENCY = Histogram(
    "wo_http_request_seconds",
    "HTTP request duration",
    ["method", "route"],
    buckets=(0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)


TOOLKIT_JOBS = Counter("wo_toolkit_jobs_total", "Toolkit jobs that ended", ["kind", "status"])
TOOLKIT_JOB_SECONDS = Histogram(
    "wo_toolkit_job_seconds",
    "Time from a toolkit job being queued until it ended",
    ["kind"],
    buckets=(1, 2.5, 5, 10, 30, 60, 120, 300, 900),
)
TOOLKIT_AI_RUNS = Counter(
    "wo_toolkit_ai_runs_total", "Model calls made for the toolkit", ["prompt", "outcome"]
)
TOOLKIT_AI_TOKENS = Counter(
    "wo_toolkit_ai_tokens_total", "Tokens used by toolkit model calls", ["direction"]
)


def observe_toolkit_job(kind: str, status: str, seconds: float) -> None:
    TOOLKIT_JOBS.labels(kind, status).inc()
    TOOLKIT_JOB_SECONDS.labels(kind).observe(max(0.0, seconds))


def observe_ai_run(prompt: str, outcome: str, input_tokens: int, output_tokens: int) -> None:
    TOOLKIT_AI_RUNS.labels(prompt, outcome).inc()
    TOOLKIT_AI_TOKENS.labels("input").inc(input_tokens)
    TOOLKIT_AI_TOKENS.labels("output").inc(output_tokens)


def observe_request(method: str, route: str, status: int, seconds: float) -> None:
    # Routes are patterns (api/v1/posts/<uuid:post_id>), so cardinality stays bounded.
    REQUESTS.labels(method, route[:120], str(status)).inc()
    LATENCY.labels(method, route[:120]).observe(seconds)


_extra_collectors: list[Callable[[], Iterator[Metric]]] = []


def add_collector(collector: Callable[[], Iterator[Metric]]) -> None:
    """Let a module add gauges that are read at scrape time (the core knows nothing of it)."""
    _extra_collectors.append(collector)


class QueueCollector:
    """Gauges for the outbox and failed tasks, read at scrape time."""

    def collect(self) -> Iterator[Metric]:
        for extra in _extra_collectors:
            yield from extra()
        from apps.core.models import FailedTask, OutboxEvent

        now = timezone.now()
        pending = OutboxEvent.objects.filter(status=OutboxEvent.Status.PENDING)
        oldest = pending.order_by("created_at").values_list("created_at", flat=True).first()
        yield GaugeMetricFamily("wo_outbox_pending", "Outbox events waiting", pending.count())
        yield GaugeMetricFamily(
            "wo_outbox_oldest_pending_seconds",
            "Age of the oldest waiting outbox event",
            (now - oldest).total_seconds() if oldest else 0,
        )
        yield GaugeMetricFamily(
            "wo_outbox_failed",
            "Outbox events that exhausted their attempts",
            OutboxEvent.objects.filter(status=OutboxEvent.Status.FAILED).count(),
        )
        yield GaugeMetricFamily(
            "wo_failed_tasks",
            "Tasks that failed for good and await review",
            FailedTask.objects.count(),
        )


_registered = False


def render() -> bytes:
    """The scrape body. Queue gauges are always from this process's database connection."""
    global _registered  # noqa: PLW0603
    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        registry.register(QueueCollector())
        return generate_latest(registry)
    if not _registered:
        REGISTRY.register(QueueCollector())
        _registered = True
    return generate_latest(REGISTRY)
