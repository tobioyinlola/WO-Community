from typing import ClassVar

import structlog

from apps.integrations.cdn.base import CachePurger

logger = structlog.get_logger(__name__)


class LoggingPurger(CachePurger):
    """Default until a CDN is chosen: pages expire on their own five minute lifetime."""

    def purge(self, paths: list[str]) -> None:
        logger.info("cdn_purge_skipped", paths=paths)


class FakePurger(CachePurger):
    """Records purge requests for tests."""

    purged: ClassVar[list[str]] = []

    @classmethod
    def reset(cls) -> None:
        cls.purged.clear()

    def purge(self, paths: list[str]) -> None:
        self.purged.extend(paths)
