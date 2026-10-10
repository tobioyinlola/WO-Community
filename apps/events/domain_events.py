"""Domain events published by the events module."""

from dataclasses import dataclass
from typing import ClassVar

from apps.core.events import DomainEvent


@dataclass(frozen=True)
class RegistrationConfirmed(DomainEvent):
    topic: ClassVar[str] = "events.registration_confirmed"
    event_id: str
    user_id: str


@dataclass(frozen=True)
class EventCancelled(DomainEvent):
    topic: ClassVar[str] = "events.cancelled"
    event_id: str


@dataclass(frozen=True)
class EventRescheduled(DomainEvent):
    topic: ClassVar[str] = "events.rescheduled"
    event_id: str
