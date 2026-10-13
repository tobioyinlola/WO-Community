import json

import httpx
import pytest
from django.core.exceptions import ImproperlyConfigured

from apps.integrations.cdn.cloudflare import CloudflarePurger


@pytest.fixture
def configured(settings):
    settings.CLOUDFLARE_API_TOKEN = "token-123"
    settings.CLOUDFLARE_ZONE_ID = "zone-abc"
    settings.CDN_ORIGIN_URL = "https://api.example.com/"


def purger(handler):
    return CloudflarePurger(httpx.Client(transport=httpx.MockTransport(handler)))


def test_it_posts_full_urls_with_the_scoped_token(configured):
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"success": True})

    purger(handler).purge(
        ["/api/v1/public/events", "api/v1/public/events/demo", "/api/v1/public/events"]
    )
    assert len(seen) == 1
    request = seen[0]
    assert str(request.url) == "https://api.cloudflare.com/client/v4/zones/zone-abc/purge_cache"
    assert request.headers["authorization"] == "Bearer token-123"
    assert json.loads(request.content) == {
        "files": [
            "https://api.example.com/api/v1/public/events",
            "https://api.example.com/api/v1/public/events/demo",
        ]
    }


def test_large_purges_are_sent_in_batches_of_thirty(configured):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(len(json.loads(request.content)["files"]))
        return httpx.Response(200, json={"success": True})

    purger(handler).purge([f"/api/v1/public/p/{i}" for i in range(65)])
    assert calls == [30, 30, 5]


@pytest.mark.parametrize("status", [400, 403, 429, 500])
def test_a_rejected_purge_raises_so_the_caller_can_log_it(configured, status):
    with pytest.raises(RuntimeError):
        purger(lambda r: httpx.Response(status, json={"success": False})).purge(["/x"])


def test_a_network_failure_raises_without_the_token_in_the_message(configured):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    with pytest.raises(RuntimeError) as caught:
        purger(handler).purge(["/x"])
    assert "token-123" not in str(caught.value)


def test_it_refuses_to_start_without_credentials(settings):
    settings.CLOUDFLARE_API_TOKEN = ""
    with pytest.raises(ImproperlyConfigured):
        CloudflarePurger()
