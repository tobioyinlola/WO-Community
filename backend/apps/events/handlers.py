"""Subscriptions from event happenings to the tasks that notify members."""

from apps.core import outbox
from apps.events import domain_events as events


def register() -> None:
    outbox.register_handler(
        events.RegistrationConfirmed.topic, "events.notify_registered", "default"
    )
    outbox.register_handler(events.EventCancelled.topic, "events.notify_cancelled", "default")
    outbox.register_handler(events.EventRescheduled.topic, "events.notify_rescheduled", "default")
