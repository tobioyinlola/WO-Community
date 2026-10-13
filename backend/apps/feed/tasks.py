from typing import Any
from uuid import UUID

import structlog
from celery import shared_task

from apps.core.models import OutboxEvent
from apps.feed import links, services
from apps.notifications import notify
from apps.startups import selectors as startups

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


@shared_task(name="feed.notify_follow")
def notify_follow(event_id: str) -> None:
    data = _payload(event_id)
    if data is None:
        return
    follower_id = UUID(data["follower_id"])
    target_id = UUID(data["target_id"])
    payload: dict[str, str] = {"actor_id": str(follower_id), "kind": data["kind"]}
    if data["kind"] == "startup":
        startup = startups.get_startup(target_id)
        if startup is None:
            return
        recipient = startup.owner_id
        payload.update(startup_id=str(startup.pk), startup_name=startup.name)
    else:
        recipient = target_id
    # One notice per follower and target, ever: unfollowing and following again stays quiet.
    notify.notify(
        recipient,
        "new_follower",
        payload,
        dedupe_key=f"follow:{follower_id.hex}{target_id.hex}",  # 80 characters at most
    )


@shared_task(name="feed.fetch_link_preview", time_limit=60, soft_time_limit=45)
def fetch_link_preview(event_id: str) -> None:
    data = _payload(event_id)
    if data is not None:
        links.fetch(data["preview_id"])


@shared_task(name="feed.purge_link_previews")
def purge_link_previews() -> int:
    return links.purge_unused()


@shared_task(name="feed.publish_scheduled")
def publish_scheduled() -> int:
    return services.publish_due()


@shared_task(name="feed.notify_moderated")
def notify_moderated(event_id: str) -> None:
    event = OutboxEvent.objects.filter(pk=event_id).first()
    if event is None:
        return
    data = event.payload
    notify.notify(
        UUID(data["author_id"]),
        "post_moderated",
        {"post_id": data["post_id"], "what": data["action"], "reason": data["reason"]},
        dedupe_key=f"{event_id}:moderated",
    )
