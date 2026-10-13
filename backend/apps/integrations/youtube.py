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


# --- the title of a video, for admins adding lectures ---

OEMBED = "https://www.youtube.com/oembed"


def oembed_title(video_id: str) -> str:
    """The video's title from YouTube, or "" when it cannot be had.

    Only the fixed YouTube address is ever asked, with nothing but an 11 character id, so this
    cannot be steered to another host. A failure is not an error: the admin types a title instead.
    """
    import httpx

    if not VIDEO_ID.match(video_id):
        return ""
    try:
        response = httpx.get(
            OEMBED,
            params={"url": f"https://www.youtube.com/watch?v={video_id}", "format": "json"},
            timeout=4.0,
            follow_redirects=False,
        )
        if response.status_code != 200:
            return ""
        return str(response.json().get("title", ""))[:160]
    except Exception:  # noqa: BLE001 - anything at all means "no title", never a failed request
        return ""


def fake_title(video_id: str) -> str:
    """Stands in for YouTube in tests and offline work."""
    return f"Video {video_id}" if VIDEO_ID.match(video_id) else ""


def title_of(video_id: str) -> str:
    from django.conf import settings
    from django.utils.module_loading import import_string

    lookup = import_string(settings.YOUTUBE_TITLE_LOOKUP)
    return str(lookup(video_id))


def thumbnail_url(video_id: str) -> str:
    return f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg"
