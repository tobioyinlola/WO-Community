"""Reads a calendar feed over the web through the same guarded client as link previews.

The address is typed by a member, so it gets every server-side request forgery control the
preview fetcher has: public hosts only, the connection pinned to the checked address, redirects
re-checked, size and time capped.
"""

from apps.integrations.calendars.base import FeedReader, FeedRejected, FeedUnavailable
from apps.integrations.linkpreview.base import FetchFailed, FetchRejected
from apps.integrations.linkpreview.safe_http import SafeClient

FEED_BYTES = 5 * 1024 * 1024
FEED_TYPES = {
    "text/calendar",
    "application/ics",
    "application/calendar",
    "text/plain",
    "application/octet-stream",
}


class WebFeedReader(FeedReader):
    def __init__(self, client: SafeClient | None = None) -> None:
        self.client = client or SafeClient()

    def read(self, url: str) -> str:
        try:
            fetched = self.client.get(
                url,
                accept="text/calendar, text/plain;q=0.5",
                content_types=FEED_TYPES,
                max_bytes=FEED_BYTES,
                truncate=False,
            )
        except FetchRejected as exc:
            raise FeedRejected(exc.code) from exc
        except FetchFailed as exc:
            raise FeedUnavailable(exc.code) from exc
        return fetched.body.decode("utf-8", errors="replace")
