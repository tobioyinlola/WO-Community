"""Domain events published by the feed. The notification centre turns them into notices."""

from dataclasses import dataclass
from typing import ClassVar

from apps.core.events import DomainEvent


@dataclass(frozen=True)
class MemberMentioned(DomainEvent):
    topic: ClassVar[str] = "feed.member_mentioned"
    user_id: str  # who was mentioned
    by_user_id: str
    target_type: str  # "post" or "comment"
    target_id: str
    post_id: str


@dataclass(frozen=True)
class CommentAdded(DomainEvent):
    topic: ClassVar[str] = "feed.comment_added"
    comment_id: str
    post_id: str
    commenter_id: str
    post_author_id: str
    parent_author_id: str  # empty unless the comment is a reply
