"""Domain events: plain dataclasses published after commit through the outbox."""

from dataclasses import asdict, dataclass
from typing import Any, ClassVar

from apps.core import outbox


@dataclass(frozen=True)
class DomainEvent:
    topic: ClassVar[str]

    def payload(self) -> dict[str, Any]:
        return asdict(self)


def publish(event: DomainEvent) -> None:
    """Record the event in the caller's transaction."""
    outbox.enqueue(event.topic, event.payload())
