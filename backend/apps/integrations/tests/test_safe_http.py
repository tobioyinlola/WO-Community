"""The request-forgery controls, tested without any network."""

import gzip
import ipaddress

import httpx
import pytest

from apps.integrations.linkpreview import FetchFailed, FetchRejected
from apps.integrations.linkpreview import safe_http as http
from apps.integrations.linkpreview.safe_http import SafeClient, parse_url, resolve_public

HTML = {"text/html"}
PUBLIC = "93.184.216.34"


def reject_code(call):
    with pytest.raises(FetchRejected) as caught:
        call()
    return caught.value.code


# --- the address itself ---


@pytest.mark.parametrize(
    "url, code",
    [
        ("file:///etc/passwd", "bad_scheme"),
        ("ftp://example.com/x", "bad_scheme"),
        ("gopher://example.com/", "bad_scheme"),
        ("javascript:alert(1)", "bad_scheme"),
        ("data:text/html,<script>", "bad_scheme"),
        ("//example.com/x", "bad_scheme"),
        ("http://127.0.0.1/", "ip_address_host"),
        ("http://10.0.0.5/admin", "ip_address_host"),
        ("http://169.254.169.254/latest/meta-data/", "ip_address_host"),
        ("http://2130706433/", "internal_host"),  # 127.0.0.1 as one number
        ("http://0x7f.0.0.1/", "ip_address_host"),
        ("http://017700000001/", "internal_host"),
        ("http://0177.0.0.1/", "ip_address_host"),
        ("http://127.1/", "ip_address_host"),
        ("http://[::1]/", "internal_host"),
        ("http://[::ffff:127.0.0.1]/", "ip_address_host"),
        ("http://localhost/", "internal_host"),
        ("http://LOCALHOST./", "internal_host"),
        ("http://app.localhost/", "internal_host"),
        ("http://printer.local/", "internal_host"),
        ("http://db.internal/", "internal_host"),
        ("http://router.lan/", "internal_host"),
        ("http://intranet/", "internal_host"),
        ("http://user:secret@example.com/", "credentials_in_url"),
        ("http://example.com@127.0.0.1/", "credentials_in_url"),
        ("http://:@example.com/", "credentials_in_url"),
        ("http://example.com:22/", "bad_port"),
        ("http://example.com:6379/", "bad_port"),
        ("http://example.com:99999/", "invalid_url"),
        ("http://exa mple.com/", "invalid_url"),
        ("http://example.com/a\nb", "invalid_url"),
        ("http://example.com\\@evil.com/", "invalid_url"),
        ("http:///path", "invalid_url"),
        ("", "invalid_url"),
        ("http://example.com/" + "a" * 2100, "invalid_url"),
    ],
)
def test_addresses_that_must_never_be_fetched(url, code):
    assert reject_code(lambda: parse_url(url)) == code


@pytest.mark.parametrize(
    "url, host, port, path",
    [
        ("https://example.com", "example.com", 443, "/"),
        ("http://example.com/a/b?x=1&y=2", "example.com", 80, "/a/b?x=1&y=2"),
        ("https://Example.COM./p", "example.com", 443, "/p"),
        ("http://example.com:8080/", "example.com", 8080, "/"),
        ("https://example.com:8443/x", "example.com", 8443, "/x"),
        ("https://bücher.example/", "xn--bcher-kva.example", 443, "/"),
        ("https://sub.domain.example.co.uk/a", "sub.domain.example.co.uk", 443, "/a"),
    ],
)
def test_ordinary_public_addresses_are_accepted(url, host, port, path):
    target = parse_url(url)
    assert (target.host, target.port, target.path) == (host, port, path)


def test_the_host_header_leaves_out_default_ports():
    assert parse_url("https://example.com/").host_header == "example.com"
    assert parse_url("https://example.com:8443/").host_header == "example.com:8443"


# --- the addresses a name may point to ---


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "127.255.255.254",
        "10.0.0.1",
        "172.16.0.1",
        "172.31.255.255",
        "192.168.1.1",
        "169.254.169.254",
        "100.64.0.1",
        "0.0.0.0",  # noqa: S104  # an address to refuse, not one we bind to
        "192.0.0.1",
        "198.18.0.1",
        "224.0.0.1",
        "240.0.0.1",
        "255.255.255.255",
        "::1",
        "::",
        "fe80::1",
        "fc00::1",
        "fd00::1",
        "ff02::1",
        "2001:db8::1",
        "::ffff:127.0.0.1",
        "::ffff:10.0.0.1",
        "::ffff:169.254.169.254",
        "64:ff9b::7f00:1",
        "64:ff9b::a00:1",
        "2002:7f00:1::1",
        "2002:a00:1::1",
    ],
)
def test_non_public_addresses_are_refused(address):
    assert not http.is_public(ipaddress.ip_address(address))


@pytest.mark.parametrize(
    "address", ["8.8.8.8", "1.1.1.1", "93.184.216.34", "2606:4700:4700::1111", "::ffff:8.8.8.8"]
)
def test_public_addresses_are_allowed(address):
    assert http.is_public(ipaddress.ip_address(address))


def test_one_private_answer_refuses_the_whole_name():
    resolver = lambda host, port: [PUBLIC, "10.0.0.1"]  # noqa: E731
    assert reject_code(lambda: resolve_public("example.com", 80, resolver)) == "blocked_address"


def test_every_answer_must_be_public_and_the_first_is_used():
    resolver = lambda host, port: ["8.8.8.8", "2606:4700:4700::1111"]  # noqa: E731
    assert resolve_public("example.com", 80, resolver) == "8.8.8.8"


def test_garbage_answers_and_empty_answers():
    assert (
        reject_code(lambda: resolve_public("e.com", 80, lambda h, p: ["not-an-ip"]))
        == "blocked_address"
    )
    with pytest.raises(FetchFailed):
        resolve_public("e.com", 80, lambda h, p: [])


def test_a_zone_id_does_not_smuggle_a_private_address_past_the_check():
    assert (
        reject_code(lambda: resolve_public("e.com", 80, lambda h, p: ["fe80::1%eth0"]))
        == "blocked_address"
    )


def test_a_name_that_does_not_resolve_is_a_network_failure_not_a_rejection(monkeypatch):
    def fail(*args, **kwargs):
        raise http.socket.gaierror("no such host")

    monkeypatch.setattr(http.socket, "getaddrinfo", fail)
    with pytest.raises(FetchFailed) as caught:
        http.system_resolver("nope.example", 80)
    assert caught.value.code == "dns_failure"


# --- fetching ---


class Recorder:
    """A fake network: answers from a function and remembers every request."""

    def __init__(self, answer):
        self.answer = answer
        self.requests: list[httpx.Request] = []
        self.transport = httpx.MockTransport(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.answer(request)


def page(text="<html></html>", **kwargs):
    headers = {"content-type": "text/html; charset=utf-8", **kwargs.pop("headers", {})}
    return httpx.Response(200, content=text.encode(), headers=headers, **kwargs)


def get(recorder, url="https://example.com/p", resolver=None, **options):
    client = SafeClient(resolver=resolver or (lambda h, p: [PUBLIC]), transport=recorder.transport)
    settings = {"accept": "text/html", "content_types": HTML, "max_bytes": 1000, "truncate": True}
    return client.get(url, **{**settings, **options})


def test_the_connection_goes_to_the_checked_address_with_the_real_name_in_host_and_sni():
    recorder = Recorder(lambda request: page("hello"))
    result = get(recorder)
    [request] = recorder.requests
    assert (
        request.url.host == PUBLIC
        and request.url.port in (None, 443)
        and request.url.scheme == "https"
    )
    assert request.headers["host"] == "example.com"
    assert request.extensions["sni_hostname"] == "example.com"
    assert request.url.path == "/p"
    assert result.body == b"hello" and result.final_url == "https://example.com/p"


def test_ipv6_addresses_are_connected_to_in_brackets():
    recorder = Recorder(lambda request: page())
    get(recorder, resolver=lambda h, p: ["2606:4700:4700::1111"])
    assert recorder.requests[0].url.host == "2606:4700:4700::1111"


def test_a_name_is_resolved_once_per_hop_so_rebinding_cannot_switch_the_target():
    answers = iter([[PUBLIC], ["127.0.0.1"], ["127.0.0.1"]])
    calls = []

    def resolver(host, port):
        calls.append(host)
        return next(answers)

    recorder = Recorder(lambda request: page())
    get(recorder, resolver=resolver)
    assert calls == ["example.com"]  # one lookup, and the request used its result
    assert recorder.requests[0].url.host == PUBLIC


def test_a_name_that_points_inside_is_refused_before_any_request():
    recorder = Recorder(lambda request: page())
    code = reject_code(lambda: get(recorder, resolver=lambda h, p: ["192.168.0.10"]))
    assert code == "blocked_address" and recorder.requests == []


def test_no_cookies_or_credentials_are_sent_and_none_are_kept():
    def answer(request):
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": "/next", "set-cookie": "sid=1"})
        return page()

    recorder = Recorder(answer)
    get(recorder, url="https://example.com/start")
    for request in recorder.requests:
        assert "cookie" not in request.headers and "authorization" not in request.headers
        assert request.headers["accept-encoding"] == "identity"
        assert request.headers["user-agent"].startswith("WOCommunityLinkPreview")


# --- redirects ---


def redirect_to(location):
    return lambda request: httpx.Response(302, headers={"location": location})


@pytest.mark.parametrize(
    "location, code",
    [
        ("http://127.0.0.1/", "ip_address_host"),
        ("http://localhost:8080/admin", "internal_host"),
        ("http://169.254.169.254/latest/meta-data/", "ip_address_host"),
        ("http://[::1]/", "internal_host"),
        ("file:///etc/passwd", "bad_scheme"),
        ("gopher://example.com/", "bad_scheme"),
        ("http://example.com:22/", "bad_port"),
        ("http://user:pw@example.com/", "credentials_in_url"),
    ],
)
def test_a_redirect_to_somewhere_forbidden_is_refused(location, code):
    recorder = Recorder(redirect_to(location))
    assert reject_code(lambda: get(recorder)) == code
    assert len(recorder.requests) == 1  # the second request was never made


def test_a_redirect_to_a_name_that_resolves_inside_is_refused():
    def resolver(host, port):
        return ["10.1.2.3"] if host == "internal-lookalike.example" else [PUBLIC]

    recorder = Recorder(redirect_to("https://internal-lookalike.example/"))
    assert reject_code(lambda: get(recorder, resolver=resolver)) == "blocked_address"
    assert len(recorder.requests) == 1


def test_relative_and_absolute_redirects_are_followed_up_to_three_times():
    def answer(request):
        step = {"/": "/a", "/a": "https://example.com/b", "/b": "/c"}.get(request.url.path)
        return httpx.Response(302, headers={"location": step}) if step else page("arrived")

    recorder = Recorder(answer)
    result = get(recorder, url="https://example.com/")
    assert result.body == b"arrived" and result.final_url.endswith("/c")
    assert len(recorder.requests) == 4


def test_a_fourth_redirect_is_one_too_many():
    recorder = Recorder(lambda request: httpx.Response(302, headers={"location": "/again"}))
    assert reject_code(lambda: get(recorder)) == "too_many_redirects"
    assert len(recorder.requests) == 4


def test_a_redirect_without_a_location_is_refused():
    recorder = Recorder(lambda request: httpx.Response(302))
    assert reject_code(lambda: get(recorder)) == "bad_redirect"


# --- responses ---


def test_error_statuses_are_network_failures():
    recorder = Recorder(lambda request: httpx.Response(404, content=b"x"))
    with pytest.raises(FetchFailed) as caught:
        get(recorder)
    assert caught.value.code == "status_404"


def test_only_allowed_content_types_are_read():
    recorder = Recorder(
        lambda r: httpx.Response(200, content=b"%PDF", headers={"content-type": "application/pdf"})
    )
    assert reject_code(lambda: get(recorder)) == "unsupported_content_type"
    recorder = Recorder(lambda r: httpx.Response(200, content=b"x"))
    assert reject_code(lambda: get(recorder)) == "unsupported_content_type"


def test_a_long_page_is_cut_off_when_truncating():
    recorder = Recorder(lambda request: page("a" * 5000))
    result = get(recorder, max_bytes=1000)
    assert len(result.body) == 1000 and result.truncated


def test_a_large_file_is_refused_when_not_truncating_by_header_or_by_counting():
    declared = Recorder(lambda r: page("a" * 10, headers={"content-length": "999999"}))
    assert reject_code(lambda: get(declared, truncate=False, max_bytes=1000)) == "too_large"
    counted = Recorder(lambda r: page("a" * 5000))
    assert reject_code(lambda: get(counted, truncate=False, max_bytes=1000)) == "too_large"


def test_the_size_cap_applies_after_decompression():
    bomb = gzip.compress(b"a" * 5_000_000)

    def answer(request):
        return httpx.Response(
            200, content=bomb, headers={"content-type": "text/html", "content-encoding": "gzip"}
        )

    result = get(Recorder(answer), max_bytes=10_000)
    assert len(result.body) == 10_000 and result.truncated
    assert (
        reject_code(lambda: get(Recorder(answer), max_bytes=10_000, truncate=False)) == "too_large"
    )


def test_timeouts_and_connection_errors_are_failures_that_may_pass_later():
    def timed_out(request):
        raise httpx.ReadTimeout("slow", request=request)

    def refused(request):
        raise httpx.ConnectError("no route", request=request)

    with pytest.raises(FetchFailed) as slow:
        get(Recorder(timed_out))
    assert slow.value.code == "timeout"
    with pytest.raises(FetchFailed) as down:
        get(Recorder(refused))
    assert down.value.code == "network_error"


def test_a_slow_trickle_is_cut_off_by_the_overall_deadline():
    ticks = iter(range(0, 1000, 5))

    class Stream(httpx.SyncByteStream):
        def __iter__(self):
            for _ in range(10):
                yield b"x" * 10

    recorder = Recorder(
        lambda request: httpx.Response(200, headers={"content-type": "text/html"}, stream=Stream())
    )
    client = SafeClient(
        resolver=lambda h, p: [PUBLIC], transport=recorder.transport, clock=lambda: next(ticks)
    )
    with pytest.raises(FetchFailed) as caught:
        client.get(
            "https://example.com/",
            accept="text/html",
            content_types=HTML,
            max_bytes=10_000,
            truncate=True,
        )
    assert caught.value.code == "timeout"
