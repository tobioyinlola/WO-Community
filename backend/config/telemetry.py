"""Distributed tracing, switched on by an OTLP endpoint and otherwise absent.

With ``OTEL_EXPORTER_OTLP_ENDPOINT`` unset nothing is imported or patched, so local runs and tests
pay nothing. Set it (for example to an OpenTelemetry collector) and requests, database calls,
Celery tasks and outbound HTTP are traced, sampled by ``OTEL_TRACE_SAMPLE_RATIO``.

Query strings are redacted from spans: tokens for email links and similar secrets travel in them.
"""

from typing import Any

import structlog
from django.conf import settings

logger = structlog.get_logger(__name__)
_started = False


def _redact(span: Any, request: Any) -> None:
    if span is None or not span.is_recording():
        return
    path = request.path
    span.set_attribute("url.query", "")
    span.set_attribute("http.target", path)
    span.set_attribute("http.url", request.build_absolute_uri(path))


def setup(service_name: str) -> bool:
    """Start tracing for this process. Returns whether it was started."""
    global _started  # noqa: PLW0603
    endpoint = settings.OTEL_EXPORTER_OTLP_ENDPOINT
    if _started or not endpoint:
        return False
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.celery import CeleryInstrumentor
    from opentelemetry.instrumentation.django import DjangoInstrumentor
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased

    provider = TracerProvider(
        resource=Resource.create(
            {"service.name": service_name, "deployment.environment": settings.ENVIRONMENT}
        ),
        sampler=ParentBased(TraceIdRatioBased(settings.OTEL_TRACE_SAMPLE_RATIO)),
    )
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    trace.set_tracer_provider(provider)
    DjangoInstrumentor().instrument(
        request_hook=_redact, excluded_urls="health/live,health/ready,metrics"
    )
    PsycopgInstrumentor().instrument(enable_commenter=False)
    HTTPXClientInstrumentor().instrument()
    CeleryInstrumentor().instrument()
    _started = True
    logger.info("tracing_started", service=service_name, ratio=settings.OTEL_TRACE_SAMPLE_RATIO)
    return True
