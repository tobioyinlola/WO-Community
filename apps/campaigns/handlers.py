"""Subscriptions from campaign events to the tasks that send them."""

from apps.campaigns import events
from apps.core import outbox


def register() -> None:
    outbox.register_handler(events.CampaignStarted.topic, "campaigns.begin_sending", "email")
