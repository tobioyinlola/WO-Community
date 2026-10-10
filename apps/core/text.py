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
