from abc import ABC, abstractmethod
from typing import Any


class AnalyticsSink(ABC):
    """Where events go once recorded: the product analytics tool.

    Delivery is at least once, so a tool must treat each event's ``id`` as its
    unique key and ignore repeats.
    """

    @abstractmethod
    def send_events(self, events: list[dict[str, Any]]) -> None:
        """Send events in order. Raise to have the same batch offered again later."""

    @abstractmethod
    def send_identities(self, links: list[dict[str, str]]) -> None:
        """Tell the tool which anonymous ids belong to which members."""
