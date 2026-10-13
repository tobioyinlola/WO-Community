"""Domain events published by the editorial module."""

from dataclasses import dataclass
from typing import ClassVar

from apps.core.events import DomainEvent


@dataclass(frozen=True)
class ItemPublished(DomainEvent):
    topic: ClassVar[str] = "editorial.item_published"
    item_id: str


@dataclass(frozen=True)
class WinReviewed(DomainEvent):
    topic: ClassVar[str] = "editorial.win_reviewed"
    win_id: str
    approved: bool
    note: str


@dataclass(frozen=True)
class CommentReportHandled(DomainEvent):
    """A moderator dealt with a report on a comment; the reporter is told."""

    topic: ClassVar[str] = "editorial.comment_report_handled"
    reporter_id: str
    outcome: str  # "reviewed" or "actioned"
    target_type: str
