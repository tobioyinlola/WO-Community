import re
from typing import ClassVar

from apps.toolkit.ai.research.base import Page, ResearchFailed, ResearchProvider, SearchHit


class FakeResearchProvider(ResearchProvider):
    """Fixtures for tests and local runs. Nothing leaves the process.

    ``pages`` maps a URL to a page; ``hits`` maps a word in the query to its results. A query
    with no scripted hits gets one generated page whose text carries a sentence about the topic.
    """

    pages: ClassVar[dict[str, Page]] = {}
    hits: ClassVar[dict[str, list[SearchHit]]] = {}
    failures: ClassVar[set[str]] = set()
    searched: ClassVar[list[str]] = []
    fetched: ClassVar[list[str]] = []

    @classmethod
    def reset(cls) -> None:
        cls.pages.clear()
        cls.hits.clear()
        cls.failures.clear()
        cls.searched.clear()
        cls.fetched.clear()

    def search(self, query: str, *, region: str = "", limit: int = 5) -> list[SearchHit]:
        self.searched.append(query)
        for word, found in self.hits.items():
            if word.lower() in query.lower():
                return found[:limit]
        slug = re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-")[:60] or "topic"
        url = f"https://research.example.org/{slug}"
        return [SearchHit(url=url, title=f"Report on {query}", snippet=f"Findings about {query}")][
            :limit
        ]

    def fetch(self, url: str) -> Page:
        self.fetched.append(url)
        if url in self.failures:
            raise ResearchFailed("unreachable")
        if url in self.pages:
            return self.pages[url]
        topic = url.rsplit("/", 1)[-1].replace("-", " ")
        return Page(
            url=url,
            title=f"Report on {topic}",
            text=f"The market for {topic} is growing at 12 percent a year, says this report.",
            publisher="Example Research",
        )
