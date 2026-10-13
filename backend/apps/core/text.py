"""Cleaning of free text and links that members type into profiles."""

import html
import re
from urllib.parse import urlparse

import nh3
from rest_framework import serializers

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_IP_HOST = re.compile(r"^(\d{1,3}\.){3}\d{1,3}$|^\[.*\]$")


def plain(value: str) -> str:
    """Text with markup removed and control characters dropped.

    The result is plain text to be shown as text; clients must still escape it.
    """
    stripped = html.unescape(nh3.clean(value, tags=set()))
    return _CONTROL.sub("", stripped).strip()


def clean_url(value: str, *, hosts: tuple[str, ...] = ()) -> str:
    """An https link on a real hostname, optionally limited to some domains.

    Blank clears the field. Anything else (other schemes, IP addresses,
    credentials in the address) is refused.
    """
    value = value.strip()
    if not value:
        return ""
    if len(value) > 300:
        raise serializers.ValidationError("Enter a shorter link.")
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not host or "." not in host:
        raise serializers.ValidationError("Enter a full https:// link.")
    if parsed.username or parsed.password or _IP_HOST.match(host) or host == "localhost":
        raise serializers.ValidationError("Enter a link to a public website.")
    if hosts and not any(host == h or host.endswith("." + h) for h in hosts):
        raise serializers.ValidationError(f"Link must be on {', '.join(hosts)}.")
    return value


# Rich text: what a post or comment may contain. Everything else is removed, not escaped.
_POST_TAGS = {"p", "br", "strong", "em", "ul", "ol", "li", "h2", "h3", "blockquote", "a"}
_COMMENT_TAGS = {"p", "br", "strong", "em", "a"}
_SCHEMES = {"http", "https"}


def _rich(value: str, tags: set[str]) -> str:
    cleaned = nh3.clean(
        value,
        tags=tags,
        attributes={"a": {"href"}},
        url_schemes=_SCHEMES,
        link_rel="noopener nofollow ugc",
        strip_comments=True,
    )
    return _CONTROL.sub("", cleaned).strip()


def rich_post(value: str) -> str:
    """HTML for a post: paragraphs, bold, italic, lists, headings, quotes and http(s) links."""
    return _rich(value, _POST_TAGS)


def rich_comment(value: str) -> str:
    """HTML for a comment: paragraphs, bold, italic and http(s) links."""
    return _rich(value, _COMMENT_TAGS)


def text_of(html_value: str) -> str:
    """The words of a piece of rich text with all markup removed, whitespace collapsed."""
    spaced = re.sub(r"<[^>]+>", " ", html_value)
    return re.sub(r"\s+", " ", plain(spaced))
