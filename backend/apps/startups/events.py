from dataclasses import dataclass
from typing import ClassVar

from apps.core.events import DomainEvent


@dataclass(frozen=True)
class StartupUpdated(DomainEvent):
    """A startup changed; the public directory refreshes from this."""

    topic: ClassVar[str] = "startups.startup_updated"
    startup_id: str
