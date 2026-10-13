"""Rules of the founder profile that do not touch the database."""

from collections.abc import Mapping
from typing import Any

OPEN_TO_CHOICES = ("hiring", "mentoring", "seeking_mentor", "partnerships")
MAX_SKILLS = 15
MAX_CUSTOM_SKILLS = 10
MAX_CUSTOM_SKILL_LENGTH = 40

# Field groups: each has one visibility level that the member controls.
GROUP_FIELDS: dict[str, tuple[str, ...]] = {
    "basics": ("full_name", "headline", "photo"),
    "bio": ("bio",),
    "location": ("country", "city"),
    "skills": ("skills", "custom_skills"),
    "links": ("linkedin_url", "x_url", "website_url"),
    "open_to": ("open_to",),
}

# Members see the essentials by default; personal links start private.
DEFAULT_LEVELS: dict[str, str] = {
    "basics": "members",
    "bio": "members",
    "location": "members",
    "skills": "members",
    "links": "private",
    "open_to": "members",
}

# Weight of each field in the completeness score, in the order a member is nudged to fill them.
COMPLETENESS: tuple[tuple[str, int], ...] = (
    ("full_name", 15),
    ("headline", 15),
    ("bio", 20),
    ("location", 10),
    ("skills", 15),
    ("links", 5),
    ("open_to", 5),
    ("photo", 15),
)


def is_filled(field: str, values: Mapping[str, Any]) -> bool:
    if field == "location":
        return bool(values.get("country")) and bool(values.get("city"))
    if field == "skills":
        return bool(values.get("skills")) or bool(values.get("custom_skills"))
    if field == "links":
        return any(values.get(name) for name in GROUP_FIELDS["links"])
    return bool(values.get(field))


def completeness(values: Mapping[str, Any]) -> tuple[int, str | None]:
    """Score from 0 to 100 and the most valuable field still empty."""
    total = sum(weight for _, weight in COMPLETENESS)
    earned = 0
    next_missing: str | None = None
    for field, weight in COMPLETENESS:
        if is_filled(field, values):
            earned += weight
        elif next_missing is None:
            next_missing = field
    return round(earned * 100 / total), next_missing
