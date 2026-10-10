"""Subscriptions from editorial events to the tasks that notify members."""

from apps.core import outbox
from apps.editorial import events


def register() -> None:
    outbox.register_handler(events.WinReviewed.topic, "editorial.notify_win_review", "default")
