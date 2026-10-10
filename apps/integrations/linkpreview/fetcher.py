"""Builds a preview card (title, description, site, image) from a public web page."""

from html.parser import HTMLParser
from urllib.parse import urljoin

import structlog

from apps.core.text import plain
from apps.integrations.linkpreview.base import (
    FetchFailed,
    FetchRejected,
    Preview,
    PreviewFetcher,
)
from apps.integrations.linkpreview.safe_http import SafeClient

logger = structlog.get_logger(__name__)

PAGE_BYTES = 512 * 1024
IMAGE_BYTES = 3 * 1024 * 1024
PAGE_TYPES = {"text/html", "application/xhtml+xml"}
IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
TITLE_MAX, DESCRIPTION_MAX, SITE_MAX = 200, 300, 100


class _HeadReader(HTMLParser):
    """Collects the few tags a preview needs and stops at the end of the head."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.title = ""
        self._in_title = False
        self.done = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.done:
            return  # nothing after the head counts, whatever it claims to be
        if tag == "title":
            self._in_title = True
        elif tag == "body":
            self.done = True
        elif tag == "meta":
            values = {k.lower(): (v or "") for k, v in attrs}
            key = (values.get("property") or values.get("name") or "").lower()
            if key and "content" in values:
                self.meta.setdefault(key, values["content"])

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        elif tag == "head":
            self.done = True

    def handle_data(self, data: str) -> None:
        if not self.done and self._in_title and len(self.title) < 500:
            self.title += data


def _clean(value: str, limit: int) -> str:
    text = " ".join(plain(value).split())
    return text[: limit - 1] + "…" if len(text) > limit else text


def parse_page(body: bytes, base_url: str) -> tuple[Preview, str]:
    """The text fields of a preview and the address of its image (blank if none)."""
    reader = _HeadReader()
    text = body.decode("utf-8", errors="replace")
    try:
        # Feed in slices so we can stop once the head is over, however large the page is.
        for start in range(0, len(text), 8192):
            reader.feed(text[start : start + 8192])
            if reader.done:
                break
    except Exception:  # noqa: BLE001  # broken markup must never fail a post
        logger.info("link_preview_parse_error")
    meta = reader.meta
    title = meta.get("og:title") or meta.get("twitter:title") or reader.title
    description = (
        meta.get("og:description") or meta.get("twitter:description") or meta.get("description", "")
    )
    site = meta.get("og:site_name", "")
    image = meta.get("og:image") or meta.get("twitter:image") or ""
    return (
        Preview(
            title=_clean(title, TITLE_MAX),
            description=_clean(description, DESCRIPTION_MAX),
            site_name=_clean(site, SITE_MAX),
        ),
        urljoin(base_url, image.strip()) if image.strip() else "",
    )


class WebFetcher(PreviewFetcher):
    def __init__(self, client: SafeClient | None = None) -> None:
        self._client = client or SafeClient()

    def fetch(self, url: str) -> Preview:
        page = self._client.get(
            url,
            accept="text/html,application/xhtml+xml",
            content_types=PAGE_TYPES,
            max_bytes=PAGE_BYTES,
            truncate=True,
        )
        preview, image_url = parse_page(page.body, page.final_url)
        if not (preview.title or preview.description):
            raise FetchRejected("nothing_to_show")
        if not image_url:
            return preview
        try:
            image = self._client.get(
                image_url,
                accept="image/jpeg,image/png,image/webp",
                content_types=IMAGE_TYPES,
                max_bytes=IMAGE_BYTES,
                truncate=False,
            )
        except (FetchRejected, FetchFailed) as exc:
            # A broken or blocked image only costs the card its picture.
            logger.info("link_preview_image_skipped", code=exc.code)
            return preview
        return Preview(
            title=preview.title,
            description=preview.description,
            site_name=preview.site_name,
            image=image.body,
            image_type=image.content_type,
        )
