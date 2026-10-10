from uuid import UUID

import structlog
from celery import shared_task

from apps.core.models import OutboxEvent
from apps.learning import learn
from apps.learning.models import Course
from apps.notifications import notify

logger = structlog.get_logger(__name__)


@shared_task(name="learning.issue_certificate")
def issue_certificate(event_id: str) -> None:
    """Make the certificate after a course is completed (the 'async job' of the design)."""
    event = OutboxEvent.objects.filter(pk=event_id).first()
    if event is None:
        logger.warning("outbox_event_missing", event_id=event_id)
        return
    learn.issue_certificate(UUID(event.payload["enrolment_id"]))


@shared_task(name="learning.notify_granted")
def notify_granted(event_id: str) -> None:
    event = OutboxEvent.objects.filter(pk=event_id).first()
    course = Course.objects.filter(pk=event.payload["course_id"]).first() if event else None
    if event is None or course is None:
        return
    notify.notify(
        UUID(event.payload["user_id"]),
        "course_granted",
        {"course_id": str(course.pk), "title": course.title},
        dedupe_key=f"{event_id}:granted",
    )
