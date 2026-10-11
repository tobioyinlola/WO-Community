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
