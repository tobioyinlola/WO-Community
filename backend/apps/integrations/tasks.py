from celery import shared_task
from django.conf import settings

from apps.analytics import services
from apps.integrations.analytics import get_sink

MAX_BATCHES_PER_RUN = 20


@shared_task(name="analytics.forward")
def forward() -> dict[str, int]:
    """Send new events, then new identity links, to the analytics tool."""
    sink = get_sink()
    events = 0
    for _ in range(MAX_BATCHES_PER_RUN):
        sent = services.forward_events(sink.send_events)
        events += sent
        if sent < settings.ANALYTICS_FORWARD_BATCH:
            break
    links = services.forward_links(sink.send_identities)
    return {"events": events, "links": links}


@shared_task(name="audit.anchor_previous_day")
def anchor_previous_day() -> dict[str, object]:
    """Anchor yesterday's audit head hash in write-once storage and re-check recent anchors."""
    from apps.integrations import anchoring

    return anchoring.anchor_previous_day()


@shared_task(name="analytics.archive_expired")
def archive_expired() -> list[str]:
    """Copy partitions that are past retention to Parquet before they are dropped."""
    from apps.integrations import archival

    return archival.archive_expired()
