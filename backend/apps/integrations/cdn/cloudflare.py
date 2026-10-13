"""Cloudflare cache purge, by URL, with an API token scoped to Cache Purge on one zone.

Paths are the platform's own public API paths (``/api/v1/public/events``); they are turned into
full addresses on ``CDN_ORIGIN_URL``, the public host that sits behind Cloudflare. Purge by URL
matches the exact address, so listing pages with query strings are not dropped here: they expire
on their own five minute lifetime. Cloudflare accepts 30 addresses per request.
"""

from functools import cached_property

import httpx
import structlog
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from apps.integrations.cdn.base import CachePurger

logger = structlog.get_logger(__name__)

API = "https://api.cloudflare.com/client/v4"
BATCH = 30
TIMEOUT = httpx.Timeout(10.0, connect=5.0)


class CloudflarePurger(CachePurger):
    def __init__(self, client: httpx.Client | None = None) -> None:
        if not (
            settings.CLOUDFLARE_API_TOKEN
            and settings.CLOUDFLARE_ZONE_ID
            and settings.CDN_ORIGIN_URL
        ):
            raise ImproperlyConfigured(
                "CLOUDFLARE_API_TOKEN, CLOUDFLARE_ZONE_ID and CDN_ORIGIN_URL must be set"
            )
        self._client = client

    @cached_property
    def client(self) -> httpx.Client:
        return self._client or httpx.Client(timeout=TIMEOUT)

    def purge(self, paths: list[str]) -> None:
        base = settings.CDN_ORIGIN_URL.rstrip("/")
        urls = sorted({base + (p if p.startswith("/") else "/" + p) for p in paths})
        for start in range(0, len(urls), BATCH):
            self._send(urls[start : start + BATCH])

    def _send(self, urls: list[str]) -> None:
        try:
            response = self.client.post(
                f"{API}/zones/{settings.CLOUDFLARE_ZONE_ID}/purge_cache",
                headers={"Authorization": f"Bearer {settings.CLOUDFLARE_API_TOKEN}"},
                json={"files": urls},
            )
        except httpx.HTTPError as exc:
            # Callers treat a failed purge as non fatal: pages expire by themselves.
            raise RuntimeError(f"cloudflare purge: {type(exc).__name__}") from exc
        if response.status_code != 200 or not response.json().get("success", False):
            logger.warning("cloudflare_purge_rejected", status=response.status_code)
            raise RuntimeError(f"cloudflare purge: {response.status_code}")
