"""Subscriptions from mentorship events to the tasks that notify people."""

from apps.core import outbox
from apps.mentorship import events


def register() -> None:
    outbox.register_handler(
        events.MentorApplicationSubmitted.topic, "mentorship.notify_admins", "default"
    )
    outbox.register_handler(
        events.MentorApplicationDecided.topic, "mentorship.notify_decision", "default"
    )
    outbox.register_handler(events.MentorRevoked.topic, "mentorship.notify_revoked", "default")
