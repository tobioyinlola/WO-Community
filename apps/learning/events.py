"""Domain events published by the learning hub."""

from dataclasses import dataclass
from typing import ClassVar

from apps.core.events import DomainEvent


@dataclass(frozen=True)
class CourseCompleted(DomainEvent):
    """A member finished every lesson; their certificate is made by a worker."""

    topic: ClassVar[str] = "learning.course_completed"
    enrolment_id: str


@dataclass(frozen=True)
class CourseGranted(DomainEvent):
    topic: ClassVar[str] = "learning.course_granted"
    course_id: str
    user_id: str
