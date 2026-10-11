"""Research over the open web, limited to domains an admin approved.

Reading a page on someone's behalf has the same risks as link previews, so it uses the same
guarded client: public hosts only, the connection pinned to the checked address, redirects
re-checked, size and time capped. On top of that only domains in ``RESEARCH_ALLOWED_DOMAINS``
are ever fetched (an empty list allows nothing), and pages are reduced to plain text with scripts
and styles removed before anything else sees them.
"""

from datetime import date
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlsplit

import httpx
from django.conf import settings

from apps.integrations.linkpreview.base import FetchFailed, FetchRejected
from apps.integrations.linkpreview.safe_http import SafeClient
from apps.toolkit.ai.research.base import Page, ResearchFailed, ResearchProvider, SearchHit

PAGE_BYTES = 1_000_000
MAX_TEXT = 60_000
PAGE_TYPES = {"text/html", "application/xhtml+xml", "text/plain"}
_SKIP = {"script", "style", "noscript", "template", "svg", "iframe", "head"}


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self._depth = 0
        self._in_title = False
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag == "title":
            self._in_title = True
        if tag in _SKIP:
            self._depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        if tag in _SKIP and self._depth:
            self._depth -= 1

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
        elif not self._depth and data.strip():
            self.parts.append(data.strip())


def to_text(html: str) -> tuple[str, str]:
    reader = _Text()
    reader.feed(html)
    return reader.title.strip()[:300], " ".join(reader.parts)[:MAX_TEXT]


def allowed(url: str) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    return bool(host) and any(
        host == d or host.endswith("." + d)
        for d in (x.strip().lower() for x in settings.RESEARCH_ALLOWED_DOMAINS)
        if d
    )


class WebResearchProvider(ResearchProvider):
    def __init__(self, client: SafeClient | None = None, http: httpx.Client | None = None) -> None:
        self.client = client or SafeClient()
        self._http = http

    def search(self, query: str, *, region: str = "", limit: int = 5) -> list[SearchHit]:
        if not settings.RESEARCH_SEARCH_URL:
            return []
        http = self._http or httpx.Client(timeout=httpx.Timeout(10.0, connect=5.0))
        try:
            response = http.get(
                settings.RESEARCH_SEARCH_URL,
                params={"q": query, "count": limit * 3},
                headers={"Authorization": f"Bearer {settings.RESEARCH_SEARCH_KEY}"},
            )
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ResearchFailed("search_unavailable") from exc
        rows = body.get("results") or (body.get("web") or {}).get("results") or []
        hits: list[SearchHit] = []
        for row in rows:
            url = str(row.get("url", ""))
            if not allowed(url):
                continue  # only approved domains are ever candidates
            stamp = str(row.get("date") or row.get("page_age") or "")[:10]
            try:
                published = date.fromisoformat(stamp) if stamp else None
            except ValueError:
                published = None
            hits.append(
                SearchHit(
                    url=url,
                    title=str(row.get("title", ""))[:300],
                    snippet=str(row.get("snippet") or row.get("description") or "")[:500],
                    published=published,
                )
            )
            if len(hits) == limit:
                break
        return hits

    def fetch(self, url: str) -> Page:
        if not allowed(url):
            raise ResearchFailed("domain_not_allowed")
        try:
            fetched = self.client.get(
                url,
                accept="text/html, text/plain;q=0.8",
                content_types=PAGE_TYPES,
                max_bytes=PAGE_BYTES,
                truncate=True,
            )
        except (FetchRejected, FetchFailed) as exc:
            raise ResearchFailed(exc.code) from exc
        title, text = to_text(fetched.body.decode("utf-8", errors="replace"))
        if not text:
            raise ResearchFailed("empty_page")
        return Page(
            url=url,
            title=title,
            text=text,
            publisher=(urlsplit(url).hostname or "").removeprefix("www."),
        )
