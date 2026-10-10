"""Subscriptions from feed events to the tasks that notify members."""

from apps.core import outbox
from apps.feed import events


def register() -> None:
    outbox.register_handler(events.MemberMentioned.topic, "feed.notify_mention", "default")
    outbox.register_handler(events.CommentAdded.topic, "feed.notify_comment", "default")
    outbox.register_handler(events.ReportHandled.topic, "feed.notify_report_outcome", "default")
