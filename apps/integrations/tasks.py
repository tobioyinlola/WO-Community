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
