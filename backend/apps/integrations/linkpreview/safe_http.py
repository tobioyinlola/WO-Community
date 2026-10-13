"""Fetching a web page on behalf of a member without letting them reach our own network.

Server-side request forgery is when a user gets the server to call an address they could not reach
themselves: an internal service, a cloud metadata endpoint, localhost. The controls here, all of
which apply to every hop of a redirect chain:

* only ``http`` and ``https``, only ports 80, 443, 8080 and 8443, no credentials in the address;
* named hosts only: IP literals, numeric forms like ``2130706433`` and single-label or internal
  names (``localhost``, ``.local``, ``.internal``) are refused before any lookup;
* the name is resolved once, **every** address must be publicly routable (any private, loopback,
  link-local, shared, multicast, reserved or tunnelled address refuses the whole name), and the
  connection is then made to that exact address, so a name that changes its answer between our
  check and our connection (DNS rebinding) cannot redirect us;
* the certificate is still checked against the real host name, and the ``Host`` header is the real
  name;
* redirects are followed by hand, at most three, each one checked again from the start;
* a connection timeout, a read timeout per chunk and an overall deadline; a size cap on what is
  read (counted after decompression); no cookies; an allow list of content types.
"""

import ipaddress
import re
import socket
import time
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import SplitResult, urljoin, urlsplit

import httpx

from apps.integrations.linkpreview.base import FetchFailed, FetchRejected

ALLOWED_PORTS = {80, 443, 8080, 8443}
MAX_URL_LENGTH = 2000
MAX_REDIRECTS = 3
CONNECT_TIMEOUT = 3.0
READ_TIMEOUT = 4.0
DEADLINE_SECONDS = 8.0
USER_AGENT = "WOCommunityLinkPreview/1.0"
REDIRECT_STATUSES = {301, 302, 303, 307, 308}

_BLOCKED_SUFFIXES = (".localhost", ".local", ".internal", ".localdomain", ".home.arpa", ".lan")
_FORBIDDEN_CHARS = re.compile(r"[\s\x00-\x1f\x7f\\]")
_TLD = re.compile(r"^[a-z][a-z0-9-]*$")

# Ranges that are "global" to Python's ipaddress module but still must not be reached: NAT64 and
# 6to4 embed an IPv4 address that could be private.
_TUNNELS = (ipaddress.ip_network("64:ff9b::/96"), ipaddress.ip_network("2002::/16"))

Resolver = Callable[[str, int], list[str]]


@dataclass(frozen=True)
class Target:
    scheme: str
    host: str  # ASCII (punycode) host name
    port: int
    path: str  # path and query, never empty

    @property
    def host_header(self) -> str:
        default = 443 if self.scheme == "https" else 80
        return self.host if self.port == default else f"{self.host}:{self.port}"


def parse_url(url: str) -> Target:
    """Check an address without touching the network. Raises ``FetchRejected``."""
    if not url or len(url) > MAX_URL_LENGTH or _FORBIDDEN_CHARS.search(url):
        raise FetchRejected("invalid_url")
    try:
        parts: SplitResult = urlsplit(url)
        port = parts.port
        raw_host = parts.hostname
    except ValueError as exc:
        raise FetchRejected("invalid_url") from exc
    if parts.scheme not in ("http", "https"):
        raise FetchRejected("bad_scheme")
    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        raise FetchRejected("credentials_in_url")
    if not raw_host:
        raise FetchRejected("invalid_url")
    try:
        host = raw_host.rstrip(".").encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise FetchRejected("invalid_host") from exc
    if "." not in host or host == "localhost" or host.endswith(_BLOCKED_SUFFIXES):
        raise FetchRejected("internal_host")
    if not _TLD.match(host.rsplit(".", 1)[1]):
        raise FetchRejected("ip_address_host")  # IPv4 in any notation, or an IPv6 literal
    port = port or (443 if parts.scheme == "https" else 80)
    if port not in ALLOWED_PORTS:
        raise FetchRejected("bad_port")
    path = parts.path or "/"
    return Target(parts.scheme, host, port, f"{path}?{parts.query}" if parts.query else path)


def is_public(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped is not None:
            return is_public(address.ipv4_mapped)
        if any(address in net for net in _TUNNELS):
            return False
    return bool(address.is_global) and not address.is_multicast


def system_resolver(host: str, port: int) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise FetchFailed("dns_failure") from exc
    return list(dict.fromkeys(str(info[4][0]) for info in infos))


def resolve_public(host: str, port: int, resolver: Resolver) -> str:
    """The address to connect to. Refuses the name if any answer is not publicly routable."""
    answers = resolver(host, port)
    if not answers:
        raise FetchFailed("dns_failure")
    addresses = []
    for answer in answers:
        try:
            addresses.append(ipaddress.ip_address(answer.split("%", 1)[0]))
        except ValueError as exc:
            raise FetchRejected("blocked_address") from exc
    if not all(is_public(a) for a in addresses):
        raise FetchRejected("blocked_address")
    return str(addresses[0])


@dataclass(frozen=True)
class Fetched:
    final_url: str
    content_type: str
    body: bytes
    truncated: bool


class SafeClient:
    """Performs GET requests under the rules in the module docstring."""

    def __init__(
        self,
        *,
        resolver: Resolver = system_resolver,
        transport: httpx.BaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._resolver = resolver
        self._transport = transport
        self._clock = clock

    def get(
        self,
        url: str,
        *,
        accept: str,
        content_types: set[str],
        max_bytes: int,
        truncate: bool,
    ) -> Fetched:
        """GET ``url``, following up to three redirects, each re-checked.

        ``truncate`` decides what happens when the body is longer than ``max_bytes``: keep what
        was read (a page whose preview data is at the top) or refuse (an image).
        """
        deadline = self._clock() + DEADLINE_SECONDS
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            target = parse_url(current)
            address = resolve_public(target.host, target.port, self._resolver)
            response = self._request(
                target, address, accept, content_types, max_bytes, truncate, deadline
            )
            if isinstance(response, Fetched):
                return response
            current = urljoin(current, response)  # the Location of a redirect
        raise FetchRejected("too_many_redirects")

    def _request(
        self,
        target: Target,
        address: str,
        accept: str,
        content_types: set[str],
        max_bytes: int,
        truncate: bool,
        deadline: float,
    ) -> "Fetched | str":
        literal = f"[{address}]" if ":" in address else address
        timeout = httpx.Timeout(
            connect=CONNECT_TIMEOUT, read=READ_TIMEOUT, write=CONNECT_TIMEOUT, pool=CONNECT_TIMEOUT
        )
        headers = {
            "Host": target.host_header,
            "User-Agent": USER_AGENT,
            "Accept": accept,
            "Accept-Encoding": "identity",
        }
        client = httpx.Client(
            transport=self._transport,
            timeout=timeout,
            follow_redirects=False,
            trust_env=False,  # no proxy or certificate settings from the environment
            cookies=None,
        )
        try:
            with client.stream(
                "GET",
                f"{target.scheme}://{literal}:{target.port}{target.path}",
                headers=headers,
                extensions={"sni_hostname": target.host},
            ) as response:
                if response.status_code in REDIRECT_STATUSES:
                    location = response.headers.get("location", "")
                    if not location:
                        raise FetchRejected("bad_redirect")
                    return location
                if response.status_code != 200:
                    raise FetchFailed(f"status_{response.status_code}")
                content_type = (
                    response.headers.get("content-type", "").split(";")[0].strip().lower()
                )
                if content_type not in content_types:
                    raise FetchRejected("unsupported_content_type")
                declared = response.headers.get("content-length", "")
                if not truncate and declared.isdigit() and int(declared) > max_bytes:
                    raise FetchRejected("too_large")
                body = bytearray()
                for chunk in response.iter_bytes():
                    if self._clock() > deadline:
                        raise FetchFailed("timeout")
                    body.extend(chunk)
                    if len(body) > max_bytes:
                        if not truncate:
                            raise FetchRejected("too_large")
                        return Fetched(
                            f"{target.scheme}://{target.host_header}{target.path}",
                            content_type,
                            bytes(body[:max_bytes]),
                            True,
                        )
                return Fetched(
                    f"{target.scheme}://{target.host_header}{target.path}",
                    content_type,
                    bytes(body),
                    False,
                )
        except httpx.TimeoutException as exc:
            raise FetchFailed("timeout") from exc
        except httpx.HTTPError as exc:
            raise FetchFailed("network_error") from exc
        finally:
            client.close()
