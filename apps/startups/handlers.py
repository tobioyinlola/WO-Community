from apps.accounts import events as account_events
from apps.core import outbox


def register() -> None:
    outbox.register_handler(
        account_events.SignupDetailsSubmitted.topic, "startups.create_from_signup", "default"
    )
    outbox.register_handler(
        account_events.MemberApproved.topic, "startups.link_invited_member", "default"
    )
