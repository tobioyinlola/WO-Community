"""Subscriptions from job events to the tasks that notify members."""

from apps.core import outbox
from apps.jobs import events


def register() -> None:
    outbox.register_handler(events.JobPublished.topic, "jobs.send_instant_alerts", "default")
    outbox.register_handler(events.JobReviewed.topic, "jobs.notify_review", "default")
    outbox.register_handler(events.JobExpiring.topic, "jobs.notify_expiring", "default")
