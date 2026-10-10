from typing import Any
from uuid import UUID

import structlog
from celery import shared_task

from apps.core.models import OutboxEvent
from apps.notifications import notify

logger = structlog.get_logger(__name__)


def _payload(event_id: str) -> dict[str, Any] | None:
    event = OutboxEvent.objects.filter(pk=event_id).first()
    if event is None:
        logger.warning("outbox_event_missing", event_id=event_id)
        return None
    return dict(event.payload)


@shared_task(name="feed.notify_mention")
def notify_mention(event_id: str) -> None:
    data = _payload(event_id)
    if data is None:
        return
    notify.notify(
        UUID(data["user_id"]),
        "mention",
        {
            "actor_id": data["by_user_id"],
            "target_type": data["target_type"],
            "target_id": data["target_id"],
            "post_id": data["post_id"],
        },
        dedupe_key=f"{event_id}:mention",
    )


@shared_task(name="feed.notify_comment")
def notify_comment(event_id: str) -> None:
    """Tell the post's author, or for a reply the author of the comment replied to."""
    data = _payload(event_id)
    if data is None:
        return
    payload = {
        "actor_id": data["commenter_id"],
        "post_id": data["post_id"],
        "comment_id": data["comment_id"],
    }
    parent_author = data["parent_author_id"]
    if parent_author:
        notify.notify(UUID(parent_author), "reply", payload, dedupe_key=f"{event_id}:reply")
    if data["post_author_id"] != parent_author:
        notify.notify(
            UUID(data["post_author_id"]), "comment", payload, dedupe_key=f"{event_id}:comment"
        )


@shared_task(name="feed.notify_report_outcome")
def notify_report_outcome(event_id: str) -> None:
    data = _payload(event_id)
    if data is None:
        return
    notify.notify(
        UUID(data["reporter_id"]),
        "report_outcome",
        {"outcome": data["outcome"], "target_type": data["target_type"]},
        dedupe_key=f"{event_id}:outcome",
    )
