from typing import ClassVar

from apps.integrations.calendars.base import FeedReader, FeedRejected, FeedUnavailable


class FakeFeedReader(FeedReader):
    """Canned feeds by address. An address with no entry is refused, like an unknown host."""

    feeds: ClassVar[dict[str, str | Exception]] = {}
    fetched: ClassVar[list[str]] = []

    @classmethod
    def reset(cls) -> None:
        cls.feeds = {}
        cls.fetched = []

    def read(self, url: str) -> str:
        self.fetched.append(url)
        result = self.feeds.get(url)
        if isinstance(result, Exception):
            raise result
        if result is None:
            if "unreachable" in url:
                raise FeedUnavailable("timeout")
            raise FeedRejected("unsupported_content_type")
        return result
