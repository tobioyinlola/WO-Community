"""Subscriptions from domain events to notification tasks."""

from apps.accounts import events as account_events
from apps.core import outbox
from apps.notifications import events as notification_events


def register() -> None:
    outbox.register_handler(
        notification_events.WebhookReceived.topic, "notifications.process_webhook", "default"
    )
    outbox.register_handler(
        account_events.UserRegistered.topic, "notifications.send_verification_email", "critical"
    )
    outbox.register_handler(
        account_events.RegistrationRepeated.topic,
        "notifications.send_already_registered_email",
        "critical",
    )
    outbox.register_handler(
        account_events.InvitationRequested.topic,
        "notifications.send_invitation_email",
        "critical",
    )
    outbox.register_handler(
        account_events.MemberApproved.topic, "notifications.send_approved_email", "critical"
    )
    outbox.register_handler(
        account_events.MemberRejected.topic, "notifications.send_rejected_email", "critical"
    )
    outbox.register_handler(
        account_events.PasswordResetRequested.topic,
        "notifications.send_password_reset_email",
        "critical",
    )
