"""Field level visibility, decided in one place.

Every field group of a profile or startup has a level: ``private`` (the owner
only), ``members`` (any active member) or ``public`` (anyone). Selectors call
``project`` before anything is serialised, so a field the viewer may not see is
never even loaded into the response.
"""

from collections.abc import Mapping
from enum import IntEnum, StrEnum
from typing import Any


class Level(StrEnum):
    PRIVATE = "private"
    MEMBERS = "members"
    PUBLIC = "public"


class Audience(IntEnum):
    PUBLIC = 0
    MEMBER = 1
    OWNER = 2


LEVELS = tuple(level.value for level in Level)


def can_see(level: str, audience: Audience) -> bool:
    if audience == Audience.OWNER:
        return True
    if level == Level.PUBLIC:
        return True
    return level == Level.MEMBERS and audience >= Audience.MEMBER


def audience_for(viewer: Any, owner_ids: set[Any] | frozenset[Any] = frozenset()) -> Audience:
    """Who the viewer is, relative to the owners of the thing being viewed.

    Pending accounts are not members yet, so they see what a visitor sees.
    """
    if viewer is None or not getattr(viewer, "is_authenticated", False):
        return Audience.PUBLIC
    if viewer.pk in owner_ids:
        return Audience.OWNER
    if getattr(viewer, "status", None) == "active":
        return Audience.MEMBER
    return Audience.PUBLIC


def effective_levels(
    stored: Mapping[str, str] | None, defaults: Mapping[str, str]
) -> dict[str, str]:
    """Stored choices layered over the defaults. Unknown or invalid entries are ignored."""
    levels = dict(defaults)
    for group, level in (stored or {}).items():
        if group in defaults and level in LEVELS:
            levels[group] = level
    return levels


def project(
    groups: Mapping[str, Mapping[str, Any]],
    levels: Mapping[str, str],
    audience: Audience,
) -> dict[str, Any]:
    """Flatten the groups the audience may see. A group missing from ``levels`` is hidden."""
    visible: dict[str, Any] = {}
    for group, values in groups.items():
        if group in levels and can_see(levels[group], audience):
            visible.update(values)
    return visible
