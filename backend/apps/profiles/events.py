from dataclasses import dataclass
from typing import ClassVar

from apps.core.events import DomainEvent


@dataclass(frozen=True)
class ProfileUpdated(DomainEvent):
    """A profile changed; the public directory refreshes from this."""

    topic: ClassVar[str] = "profiles.profile_updated"
    user_id: str
