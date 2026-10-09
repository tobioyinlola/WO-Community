"""Subscriptions: which changes elsewhere should refresh the directory."""

from apps.accounts import events as account_events
from apps.core import outbox
from apps.profiles import events as profile_events
from apps.startups import events as startup_events


def register() -> None:
    queue = "default"
    outbox.register_handler(startup_events.StartupUpdated.topic, "directory.refresh_startup", queue)
    outbox.register_handler(profile_events.ProfileUpdated.topic, "directory.refresh_member", queue)
    for topic in (account_events.MemberApproved.topic, account_events.MemberReinstated.topic):
        outbox.register_handler(topic, "directory.refresh_member", queue)
    for topic in (account_events.MemberSuspended.topic, account_events.MemberRemoved.topic):
        outbox.register_handler(topic, "directory.take_down_member", queue)
