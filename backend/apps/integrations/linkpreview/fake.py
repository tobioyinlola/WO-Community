from typing import ClassVar

from apps.integrations.linkpreview.base import FetchFailed, FetchRejected, Preview, PreviewFetcher


class FakeFetcher(PreviewFetcher):
    """Canned previews. Never touches the network.

    ``results`` maps a URL to a ``Preview`` or to an exception to raise; any other URL gets a
    plain preview titled after its address.
    """

    results: ClassVar[dict[str, Preview | Exception]] = {}
    fetched: ClassVar[list[str]] = []

    @classmethod
    def reset(cls) -> None:
        cls.results = {}
        cls.fetched = []

    def fetch(self, url: str) -> Preview:
        self.fetched.append(url)
        result = self.results.get(url)
        if isinstance(result, Exception):
            raise result
        if result is not None:
            return result
        if "unreachable" in url:
            raise FetchFailed("unreachable")
        if "forbidden" in url:
            raise FetchRejected("blocked_address")
        return Preview(title=f"Title of {url}", description="A description", site_name="Example")
