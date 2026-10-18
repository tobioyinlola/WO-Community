"""Things that can be shared: a course, an event or a community post, as a short card.

The card is the brief a member puts in the feed, and the teaser anyone sees from a link shared
outside the platform. It carries only what may be shown to someone who is not signed in: a
title, a few words, an image and some plain facts, never the full content.

Each module registers how to make the card for its own kind, so the feed and the share pages
can show any of them without depending on the modules that own them.
"""

from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any

EXCERPT = 220


@dataclass(frozen=True)
class Card:
    kind: str  # "course", "event" or "post"
    ref: str  # how the owning module finds it again: a slug or an id
    title: str
    excerpt: str
    url: str  # where a signed in member reads it in full, within the app
    badge: str  # what it is, shown above the title ("Course", "Event", "Celebration")
    action: str  # the button that opens it ("View course")
    image: str | None = None  # an absolute address
    facts: list[str] = field(default_factory=list)  # "5 lectures", "Beginner", "21 Oct 2026"
    by: str = ""  # who it is from, when that may be shown

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


Resolver = Callable[[str], Card | None]
_resolvers: dict[str, Resolver] = {}


def register(kind: str, resolver: Resolver) -> None:
    _resolvers[kind] = resolver


def kinds() -> list[str]:
    return sorted(_resolvers)


def card(kind: str, ref: str) -> Card | None:
    """The card, or None when there is no such thing or it may not be shared (a draft, say)."""
    resolver = _resolvers.get(kind)
    if resolver is None or not ref or len(ref) > 120:
        return None
    return resolver(ref)


def excerpt(text: str, limit: int = EXCERPT) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rsplit(" ", 1)[0]
    return f"{cut}…"
