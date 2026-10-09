from abc import ABC, abstractmethod


class CachePurger(ABC):
    """Asks the CDN to drop cached copies of public pages."""

    @abstractmethod
    def purge(self, paths: list[str]) -> None:
        """Purge the given URL paths. Must not raise for a path that was never cached."""
