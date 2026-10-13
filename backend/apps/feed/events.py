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


@dataclass(frozen=True)
class ReportHandled(DomainEvent):
    """A moderator dealt with a report; the reporter is told."""

    topic: ClassVar[str] = "feed.report_handled"
    reporter_id: str
    outcome: str  # "reviewed" or "actioned"
    target_type: str


@dataclass(frozen=True)
class LinkPreviewRequested(DomainEvent):
    topic: ClassVar[str] = "feed.link_preview_requested"
    preview_id: str


@dataclass(frozen=True)
class FollowStarted(DomainEvent):
    """Someone followed a member or a startup, for the first time."""

    topic: ClassVar[str] = "feed.follow_started"
    follower_id: str
    kind: str  # "member" or "startup"
    target_id: str


@dataclass(frozen=True)
class PostModerated(DomainEvent):
    """The team hid, removed, restored or edited a member's post."""

    topic: ClassVar[str] = "feed.post_moderated"
    post_id: str
    author_id: str
    action: str
    reason: str
