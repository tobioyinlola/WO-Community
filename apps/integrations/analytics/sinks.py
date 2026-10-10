from typing import Any, ClassVar

import structlog

from apps.integrations.analytics.base import AnalyticsSink

logger = structlog.get_logger(__name__)


class LoggingSink(AnalyticsSink):
    """Default until a tool is chosen: events stay in our own table and only counts are logged."""

    def send_events(self, events: list[dict[str, Any]]) -> None:
        logger.info("analytics_forwarded", events=len(events))

    def send_identities(self, links: list[dict[str, str]]) -> None:
        logger.info("analytics_identities_forwarded", links=len(links))


class FakeSink(AnalyticsSink):
    """Records what it was given. ``fail`` makes it raise, like an unreachable tool."""

    events: ClassVar[list[dict[str, Any]]] = []
    links: ClassVar[list[dict[str, str]]] = []
    batches: ClassVar[list[int]] = []
    fail: ClassVar[bool] = False

    @classmethod
    def reset(cls) -> None:
        cls.events.clear()
        cls.links.clear()
        cls.batches.clear()
        cls.fail = False

    def send_events(self, events: list[dict[str, Any]]) -> None:
        if self.fail:
            raise ConnectionError("analytics tool unreachable")
        self.events.extend(events)
        self.batches.append(len(events))

    def send_identities(self, links: list[dict[str, str]]) -> None:
        if self.fail:
            raise ConnectionError("analytics tool unreachable")
        self.links.extend(links)
