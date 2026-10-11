"""Subscriptions from events that concern what a member follows."""

from apps.core import outbox
from apps.editorial import events as editorial_events


def register() -> None:
    outbox.register_handler(
        editorial_events.ItemPublished.topic, "memberarea.notify_news_followers", "default"
    )
