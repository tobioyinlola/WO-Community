from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date


class ResearchFailed(Exception):
    """A search or fetch did not work. The step carries on without that source."""


@dataclass(frozen=True)
class SearchHit:
    url: str
    title: str
    snippet: str = ""
    published: date | None = None


@dataclass(frozen=True)
class Page:
    url: str
    title: str
    text: str
    publisher: str = ""
    published: date | None = None


class ResearchProvider(ABC):
    """Finds and reads sources. Implementations must only ever read public web pages."""

    @abstractmethod
    def search(self, query: str, *, region: str = "", limit: int = 5) -> list[SearchHit]:
        """Candidate sources for a question."""

    @abstractmethod
    def fetch(self, url: str) -> Page:
        """The readable text of one page. Raises ``ResearchFailed``."""
