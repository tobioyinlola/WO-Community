import httpx
import pytest

from apps.integrations.linkpreview import FetchFailed, FetchRejected
from apps.integrations.linkpreview.fetcher import WebFetcher, parse_page
from apps.integrations.linkpreview.safe_http import SafeClient

PUBLIC = "93.184.216.34"
PAGE = """<!doctype html><html><head>
<title>Fallback title</title>
<meta property="og:title" content="Launch &amp; Learn">
<meta property="og:description" content="A <b>great</b> event for founders">
<meta property="og:site_name" content="Example Events">
<meta property="og:image" content="/img/cover.png">
</head><body><p>body text that must not be read</p></body></html>"""


def fetcher(routes, resolver=None):
    def handler(request: httpx.Request) -> httpx.Response:
        found = routes.get(request.headers["host"] + request.url.path)
        if isinstance(found, Exception):
            raise found
        return found if found is not None else httpx.Response(404)

    client = SafeClient(
        resolver=resolver or (lambda h, p: [PUBLIC]), transport=httpx.MockTransport(handler)
    )
    return WebFetcher(client)


def html(text):
    return httpx.Response(200, content=text.encode(), headers={"content-type": "text/html"})


def image(data=b"\x89PNG-bytes", content_type="image/png"):
    return httpx.Response(200, content=data, headers={"content-type": content_type})


# --- reading the page ---


def test_the_card_is_built_from_open_graph_tags_and_cleaned():
    preview, image_url = parse_page(PAGE.encode(), "https://example.com/events/1")
    assert preview.title == "Launch & Learn"
    assert preview.description == "A great event for founders"  # markup stripped
    assert preview.site_name == "Example Events"
    assert image_url == "https://example.com/img/cover.png"


def test_plain_title_and_description_are_the_fallback():
    page = (
        b'<head><title> Just a  page </title><meta name="description" content="Plain one"></head>'
    )
    preview, image_url = parse_page(page, "https://example.com/")
    assert (preview.title, preview.description, image_url) == ("Just a page", "Plain one", "")


def test_twitter_tags_are_used_when_open_graph_is_missing():
    page = b'<head><meta name="twitter:title" content="T"><meta name="twitter:image" content="https://cdn.example.com/a.jpg"></head>'
    preview, image_url = parse_page(page, "https://example.com/")
    assert preview.title == "T" and image_url == "https://cdn.example.com/a.jpg"


def test_long_text_is_shortened_and_scripts_never_survive():
    page = (
        '<head><meta property="og:title" content="'
        + "x" * 500
        + '"><meta property="og:description" '
        + 'content="&lt;script&gt;alert(1)&lt;/script&gt;ok"></head>'
    ).encode()
    preview, _ = parse_page(page, "https://example.com/")
    assert len(preview.title) == 200 and preview.title.endswith("…")
    assert "<" not in preview.description and "script" not in preview.description.lower().replace(
        "alert", ""
    )


def test_reading_stops_at_the_end_of_the_head():
    page = (
        b"<head><title>Real</title></head>"
        b'<body><title>Injected</title><meta property="og:title" content="Later"></body>'
    )
    assert parse_page(page, "https://example.com/")[0].title == "Real"


def test_broken_markup_does_not_raise():
    preview, _ = parse_page(b"<head><title>Ok</title><meta <<<>>> \x00\xff", "https://example.com/")
    assert preview.title == "Ok"


# --- the whole fetch ---


def test_a_page_with_a_picture_gives_text_and_image_bytes():
    routes = {"example.com/post": html(PAGE), "example.com/img/cover.png": image()}
    result = fetcher(routes).fetch("https://example.com/post")
    assert result.title == "Launch & Learn" and result.image == b"\x89PNG-bytes"
    assert result.image_type == "image/png"


def test_a_missing_or_broken_picture_only_costs_the_card_its_picture():
    for picture in (None, httpx.Response(500), image(content_type="text/html"), ConnectionError):
        routes = {"example.com/post": html(PAGE)}
        if picture is not None and picture is not ConnectionError:
            routes["example.com/img/cover.png"] = picture
        result = fetcher(routes).fetch("https://example.com/post")
        assert result.title == "Launch & Learn" and result.image is None


def test_a_picture_on_an_internal_host_is_never_fetched():
    page = '<head><title>T</title><meta property="og:image" content="http://127.0.0.1/secret.png"></head>'
    seen = []

    def handler(request):
        seen.append(request.headers["host"])
        return html(page)

    client = SafeClient(resolver=lambda h, p: [PUBLIC], transport=httpx.MockTransport(handler))
    result = WebFetcher(client).fetch("https://example.com/post")
    assert result.image is None and seen == ["example.com"]


def test_a_picture_whose_name_resolves_inside_is_never_fetched():
    page = '<head><title>T</title><meta property="og:image" content="https://cdn.evil.example/a.png"></head>'
    seen = []

    def resolver(host, port):
        seen.append(host)
        return ["10.0.0.9"] if host == "cdn.evil.example" else [PUBLIC]

    result = fetcher({"example.com/post": html(page)}, resolver).fetch("https://example.com/post")
    assert result.image is None and "cdn.evil.example" in seen


def test_a_page_with_nothing_to_show_is_rejected():
    with pytest.raises(FetchRejected) as caught:
        fetcher({"example.com/": html("<head></head><body>hi</body>")}).fetch(
            "https://example.com/"
        )
    assert caught.value.code == "nothing_to_show"


def test_a_page_that_is_not_html_is_rejected():
    routes = {
        "example.com/": httpx.Response(
            200, content=b"{}", headers={"content-type": "application/json"}
        )
    }
    with pytest.raises(FetchRejected) as caught:
        fetcher(routes).fetch("https://example.com/")
    assert caught.value.code == "unsupported_content_type"


def test_a_missing_page_and_a_dead_site_are_failures():
    with pytest.raises(FetchFailed):
        fetcher({}).fetch("https://example.com/gone")
    with pytest.raises(FetchFailed):
        fetcher({"example.com/": httpx.ConnectError("down")}).fetch("https://example.com/")


def test_internal_addresses_are_rejected_without_a_request():
    for url in ("http://127.0.0.1/", "http://localhost/x", "http://169.254.169.254/"):
        with pytest.raises(FetchRejected):
            fetcher({}).fetch(url)
