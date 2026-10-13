from abc import ABC, abstractmethod
from dataclasses import dataclass


class FetchRejected(Exception):
    """The address or the response is not acceptable. Retrying the same URL will not help."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class FetchFailed(Exception):
    """The site could not be reached in time or answered badly. A later attempt may work."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class Preview:
    title: str = ""
    description: str = ""
    site_name: str = ""
    image: bytes | None = None  # raw bytes of the image; the caller checks and re-encodes it
    image_type: str = ""  # the content type the site claimed


class PreviewFetcher(ABC):
    @abstractmethod
    def fetch(self, url: str) -> Preview:
        """A preview card for the page at ``url``.

        Raises ``FetchRejected`` for addresses we must never fetch and for unusable responses,
        and ``FetchFailed`` for network trouble.
        """
