from uuid import UUID

import structlog
from celery import shared_task
from django.conf import settings

from apps.campaigns import services
from apps.core.models import OutboxEvent

logger = structlog.get_logger(__name__)


@shared_task(name="campaigns.continue_sending")
def continue_sending(campaign_id: str) -> None:
    """Send one batch, then line up the next after a pause so the provider is never flooded."""
    if services.send_batch(UUID(campaign_id)):
        continue_sending.apply_async(
            args=[campaign_id], countdown=settings.CAMPAIGN_BATCH_DELAY_SECONDS, queue="email"
        )


@shared_task(name="campaigns.begin_sending")
def begin_sending(event_id: str) -> None:
    event = OutboxEvent.objects.filter(pk=event_id).first()
    if event is None:
        logger.warning("outbox_event_missing", event_id=event_id)
        return
    continue_sending(event.payload["campaign_id"])


@shared_task(name="campaigns.start_due")
def start_due() -> int:
    """Begin scheduled campaigns, and re-kick any sending campaign whose worker was lost."""
    started = services.start_due()
    for campaign_id in services.sending_ids():
        continue_sending.apply_async(args=[str(campaign_id)], queue="email")
    return started
