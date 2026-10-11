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
    outbox.register_handler(
        events.MentorRevoked.topic, "mentorship.cancel_revoked_sessions", "default"
    )
    outbox.register_handler(
        events.SessionRequested.topic, "mentorship.notify_session_requested", "default"
    )
    outbox.register_handler(
        events.SessionConfirmed.topic, "mentorship.notify_session_confirmed", "default"
    )
    outbox.register_handler(events.SessionConfirmed.topic, "mentorship.create_meeting", "default")
    outbox.register_handler(
        events.SessionDeclined.topic, "mentorship.notify_session_declined", "default"
    )
    outbox.register_handler(
        events.SessionCancelled.topic, "mentorship.notify_session_cancelled", "default"
    )
    outbox.register_handler(events.SessionCancelled.topic, "mentorship.cancel_meeting", "default")
    outbox.register_handler(
        events.SessionExpired.topic, "mentorship.notify_session_expired", "default"
    )
    outbox.register_handler(
        events.SessionCompleted.topic, "mentorship.notify_session_completed", "default"
    )
    outbox.register_handler(
        events.RescheduleProposed.topic, "mentorship.notify_reschedule_proposed", "default"
    )
    outbox.register_handler(
        events.RescheduleAccepted.topic, "mentorship.notify_reschedule_accepted", "default"
    )
    outbox.register_handler(
        events.RescheduleAccepted.topic, "mentorship.reschedule_meeting", "default"
    )
    outbox.register_handler(
        events.RescheduleClosed.topic, "mentorship.notify_reschedule_closed", "default"
    )
    outbox.register_handler(
        events.MeetingLinkAdded.topic, "mentorship.notify_meeting_link", "default"
    )
