"""Subscriptions from learning events to the tasks that act on them."""

from apps.core import outbox
from apps.learning import events


def register() -> None:
    outbox.register_handler(events.CourseCompleted.topic, "learning.issue_certificate", "default")
    outbox.register_handler(events.CourseGranted.topic, "learning.notify_granted", "default")
