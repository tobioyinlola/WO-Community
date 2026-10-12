import httpx
import pytest

from apps.integrations.calendars.base import FeedRejected, FeedUnavailable
from apps.integrations.calendars.web import WebFeedReader
from apps.integrations.linkpreview.safe_http import SafeClient

ICS = "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nEND:VCALENDAR\r\n"
PUBLIC = "93.184.216.34"


def reader(handler, resolver=None):
    client = SafeClient(
        resolver=resolver or (lambda host, port: [PUBLIC]),
        transport=httpx.MockTransport(handler),
    )
    return WebFeedReader(client)


def test_a_calendar_is_read_as_text():
    def handler(request):
        assert request.headers["accept"].startswith("text/calendar")
        return httpx.Response(
            200, text=ICS, headers={"content-type": "text/calendar; charset=utf-8"}
        )

    assert reader(handler).read("https://calendar.example.com/feed.ics") == ICS


@pytest.mark.parametrize(
    ("url", "code"),
    [
        ("http://localhost/feed.ics", "blocked_host"),
        ("https://127.0.0.1/feed.ics", None),
        ("https://user:pass@calendar.example.com/feed.ics", "credentials_in_url"),
        ("ftp://calendar.example.com/feed.ics", "bad_scheme"),
    ],
)
def test_internal_and_odd_addresses_are_never_fetched(url, code):
    def handler(request):  # pragma: no cover - must not be reached
        raise AssertionError("the network must not be touched")

    with pytest.raises(FeedRejected):
        reader(handler).read(url)


def test_a_name_that_resolves_to_a_private_address_is_refused():
    def handler(request):  # pragma: no cover
        raise AssertionError("the network must not be touched")

    with pytest.raises(FeedRejected) as caught:
        reader(handler, resolver=lambda host, port: ["10.0.0.5"]).read(
            "https://calendar.example.com/feed.ics"
        )
    assert caught.value.code == "blocked_address"


def test_a_web_page_is_not_a_calendar_and_errors_are_temporary():
    html = lambda request: httpx.Response(  # noqa: E731
        200, text="<html/>", headers={"content-type": "text/html"}
    )
    with pytest.raises(FeedRejected):
        reader(html).read("https://calendar.example.com/feed.ics")
    down = lambda request: httpx.Response(503)  # noqa: E731
    with pytest.raises(FeedUnavailable):
        reader(down).read("https://calendar.example.com/feed.ics")


def test_an_oversized_feed_is_refused():
    big = "x" * (5 * 1024 * 1024 + 10)
    handler = lambda request: httpx.Response(  # noqa: E731
        200, text=big, headers={"content-type": "text/calendar"}
    )
    with pytest.raises(FeedRejected) as caught:
        reader(handler).read("https://calendar.example.com/feed.ics")
    assert caught.value.code == "too_large"
