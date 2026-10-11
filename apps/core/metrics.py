"""Prometheus metrics: request counts and latency, and gauges for the work queues.

Request metrics are recorded by the request middleware. The queue gauges are read from the
database when Prometheus scrapes, so they are always current and cost nothing between scrapes.
With several gunicorn workers set ``PROMETHEUS_MULTIPROC_DIR`` so every worker is counted.
"""

import os
from collections.abc import Iterator

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


def observe_request(method: str, route: str, status: int, seconds: float) -> None:
    # Routes are patterns (api/v1/posts/<uuid:post_id>), so cardinality stays bounded.
    REQUESTS.labels(method, route[:120], str(status)).inc()
    LATENCY.labels(method, route[:120]).observe(seconds)


class QueueCollector:
    """Gauges for the outbox and failed tasks, read at scrape time."""

    def collect(self) -> Iterator[Metric]:
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
