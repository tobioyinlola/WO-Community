"""Checking YouTube links entered by admins. No network: it only reads the address.

Course videos are embedded from YouTube and never hosted by us, so the one thing the backend must
get right is accepting only real YouTube video addresses. Anything else (another site, plain http,
an address with credentials or a port, a playlist or channel, a malformed id) is refused.
"""

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}
VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
PATH_PREFIXES = ("embed", "shorts", "live", "v")


class InvalidVideoUrl(ValueError):
    pass


@dataclass(frozen=True)
class YouTubeVideo:
    video_id: str
    url: str  # the normalised watch address
    embed_url: str  # privacy-enhanced embed address


def parse(value: str) -> YouTubeVideo:
    """The video behind a YouTube address, or ``InvalidVideoUrl``."""
    text = value.strip()
    if not text or len(text) > 300 or any(c.isspace() or ord(c) < 32 for c in text):
        raise InvalidVideoUrl("Enter a YouTube video link.")
    try:
        parts = urlsplit(text)
        host, port = (parts.hostname or "").lower(), parts.port
    except ValueError as exc:
        raise InvalidVideoUrl("Enter a YouTube video link.") from exc
    if parts.scheme != "https" or host not in HOSTS:
        raise InvalidVideoUrl("Use an https link on youtube.com or youtu.be.")
    if parts.username is not None or parts.password is not None or port not in (None, 443):
        raise InvalidVideoUrl("Enter a plain YouTube video link.")
    segments = [s for s in parts.path.split("/") if s]
    candidate = ""
    if host == "youtu.be":
        candidate = segments[0] if len(segments) == 1 else ""
    elif segments == ["watch"]:
        candidate = (parse_qs(parts.query).get("v") or [""])[0]
    elif len(segments) == 2 and segments[0] in PATH_PREFIXES:
        candidate = segments[1]
    if not VIDEO_ID.match(candidate):
        raise InvalidVideoUrl("That link does not point to a single YouTube video.")
    return YouTubeVideo(
        video_id=candidate,
        url=f"https://www.youtube.com/watch?v={candidate}",
        embed_url=f"https://www.youtube-nocookie.com/embed/{candidate}",
    )


def embed_url(video_id: str) -> str:
    return f"https://www.youtube-nocookie.com/embed/{video_id}"
