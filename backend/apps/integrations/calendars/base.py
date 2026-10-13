from abc import ABC, abstractmethod


class FeedRejected(Exception):
    """The address or the response is not acceptable. Retrying the same address will not help."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class FeedUnavailable(Exception):
    """The calendar could not be reached in time or answered badly. A later attempt may work."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class FeedReader(ABC):
    """Downloads a mentor private calendar feed. Never called from inside a request that a
    visitor can trigger without limits: connecting and refreshing are rate limited."""

    @abstractmethod
    def read(self, url: str) -> str:
        """The feed text. Raises ``FeedRejected`` or ``FeedUnavailable``."""
