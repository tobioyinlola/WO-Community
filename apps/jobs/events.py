"""Domain events published by the jobs board."""

from dataclasses import dataclass
from typing import ClassVar

from apps.core.events import DomainEvent


@dataclass(frozen=True)
class JobPublished(DomainEvent):
    topic: ClassVar[str] = "jobs.published"
    job_id: str


@dataclass(frozen=True)
class JobReviewed(DomainEvent):
    topic: ClassVar[str] = "jobs.reviewed"
    job_id: str
    approved: bool
    note: str


@dataclass(frozen=True)
class JobExpiring(DomainEvent):
    topic: ClassVar[str] = "jobs.expiring"
    job_id: str
