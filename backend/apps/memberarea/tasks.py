from uuid import UUID

import structlog
from celery import shared_task

from apps.core.models import OutboxEvent
from apps.memberarea import news

logger = structlog.get_logger(__name__)


@shared_task(name="memberarea.notify_news_followers")
def notify_news_followers(event_id: str) -> int:
    event = OutboxEvent.objects.filter(pk=event_id).first()
    if event is None:
        logger.warning("outbox_event_missing", event_id=event_id)
        return 0
    return news.notify_followers_of_item(UUID(event.payload["item_id"]))


@shared_task(name="memberarea.send_news_digest")
def send_news_digest() -> int:
    return news.send_digest()
