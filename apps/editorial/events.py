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
