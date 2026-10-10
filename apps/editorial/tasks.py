import structlog
from celery import shared_task

from apps.core.models import OutboxEvent
from apps.editorial import services
from apps.editorial.models import WinSubmission
from apps.notifications import notify

logger = structlog.get_logger(__name__)


@shared_task(name="editorial.notify_win_review")
def notify_win_review(event_id: str) -> None:
    event = OutboxEvent.objects.filter(pk=event_id).first()
    if event is None:
        logger.warning("outbox_event_missing", event_id=event_id)
        return
    win = WinSubmission.objects.filter(pk=event.payload["win_id"]).first()
    if win is None:
        return
    if event.payload["approved"]:
        notify.notify(
            win.submitter_id,
            "win_approved",
            {"title": win.title},
            dedupe_key=f"{event_id}:approved",
        )
    else:
        notify.notify(
            win.submitter_id,
            "win_rejected",
            {"title": win.title, "reason": event.payload["note"]},
            dedupe_key=f"{event_id}:rejected",
        )


@shared_task(name="editorial.publish_due")
def publish_due() -> int:
    return services.publish_due()
