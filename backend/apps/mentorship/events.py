"""Domain events published by mentorship."""

from dataclasses import dataclass
from typing import ClassVar

from apps.core.events import DomainEvent


@dataclass(frozen=True)
class MentorApplicationSubmitted(DomainEvent):
    topic: ClassVar[str] = "mentorship.application_submitted"
    application_id: str


@dataclass(frozen=True)
class MentorApplicationDecided(DomainEvent):
    topic: ClassVar[str] = "mentorship.application_decided"
    application_id: str
    decision: str  # approved, declined or info_requested
    reason: str


@dataclass(frozen=True)
class MentorRevoked(DomainEvent):
    topic: ClassVar[str] = "mentorship.mentor_revoked"
    user_id: str
    reason: str


@dataclass(frozen=True)
class MentorSetPending(DomainEvent):
    topic: ClassVar[str] = "mentorship.mentor_set_pending"
    user_id: str
    reason: str


@dataclass(frozen=True)
class MentorReinstated(DomainEvent):
    topic: ClassVar[str] = "mentorship.mentor_reinstated"
    user_id: str


@dataclass(frozen=True)
class SessionRequested(DomainEvent):
    topic: ClassVar[str] = "mentorship.session_requested"
    session_id: str


@dataclass(frozen=True)
class SessionConfirmed(DomainEvent):
    topic: ClassVar[str] = "mentorship.session_confirmed"
    session_id: str


@dataclass(frozen=True)
class SessionDeclined(DomainEvent):
    topic: ClassVar[str] = "mentorship.session_declined"
    session_id: str
    reason: str


@dataclass(frozen=True)
class SessionCancelled(DomainEvent):
    topic: ClassVar[str] = "mentorship.session_cancelled"
    session_id: str
    by: str  # the user who cancelled, or "" when the platform did (admin, revoked mentor)
    reason: str


@dataclass(frozen=True)
class SessionExpired(DomainEvent):
    topic: ClassVar[str] = "mentorship.session_expired"
    session_id: str


@dataclass(frozen=True)
class RescheduleProposed(DomainEvent):
    topic: ClassVar[str] = "mentorship.reschedule_proposed"
    session_id: str
    by: str  # who suggested the new time


@dataclass(frozen=True)
class RescheduleAccepted(DomainEvent):
    topic: ClassVar[str] = "mentorship.reschedule_accepted"
    session_id: str
    by: str  # who accepted; the other person is told


@dataclass(frozen=True)
class RescheduleClosed(DomainEvent):
    topic: ClassVar[str] = "mentorship.reschedule_closed"
    session_id: str
    by: str
    withdrawn: bool  # the proposer took it back, rather than the other person saying no


@dataclass(frozen=True)
class MeetingLinkAdded(DomainEvent):
    topic: ClassVar[str] = "mentorship.meeting_link_added"
    session_id: str


@dataclass(frozen=True)
class SessionCompleted(DomainEvent):
    topic: ClassVar[str] = "mentorship.session_completed"
    session_id: str
