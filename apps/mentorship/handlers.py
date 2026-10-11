"""Subscriptions from mentorship events to the tasks that notify people."""

from apps.accounts import events as account_events
from apps.core import outbox
from apps.mentorship import events


def register() -> None:
    outbox.register_handler(
        account_events.SignupDetailsSubmitted.topic, "mentorship.record_interest", "default"
    )
    outbox.register_handler(
        events.MentorApplicationSubmitted.topic, "mentorship.notify_admins", "default"
    )
    outbox.register_handler(
        events.MentorApplicationDecided.topic, "mentorship.notify_decision", "default"
    )
    outbox.register_handler(events.MentorRevoked.topic, "mentorship.notify_revoked", "default")
