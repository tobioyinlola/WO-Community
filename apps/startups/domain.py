"""Rules of startup profiles that do not touch the database."""

from collections.abc import Mapping
from typing import Any

GROUP_FIELDS: dict[str, tuple[str, ...]] = {
    "basics": ("name", "pitch", "sector", "stage", "country", "city", "year_founded"),
    "description": ("description",),
    "website": ("website_url",),
    "team": ("team",),
}

# Opting into the public directory also makes the basics public (see services).
DEFAULT_LEVELS: dict[str, str] = {
    "basics": "members",
    "description": "members",
    "website": "members",
    "team": "members",
}

TRACTION_KINDS = ("users", "revenue_range", "funding_range", "milestone", "award", "partner")
SINGLE_VALUE_KINDS = ("users", "revenue_range", "funding_range")
TEXT_KINDS = ("milestone", "award", "partner")
MAX_TRACTION_ITEMS = 50
MAX_USERS = 1_000_000_000

# Ranges are bands, not exact figures, so members can share them without exposing accounts.
REVENUE_BANDS = ("none", "lt_1k", "1k_10k", "10k_50k", "50k_250k", "gt_250k")
FUNDING_BANDS = ("none", "lt_50k", "50k_250k", "250k_1m", "1m_5m", "gt_5m")
BANDS = {"revenue_range": REVENUE_BANDS, "funding_range": FUNDING_BANDS}

MIN_YEAR = 1900
MAX_DESCRIPTION = 5000

# In the order a founder is nudged to fill them.
COMPLETENESS: tuple[tuple[str, int], ...] = (
    ("basics", 15),
    ("description", 20),
    ("year_founded", 10),
    ("website", 10),
    ("traction", 25),
    ("team", 20),
)


def is_filled(field: str, values: Mapping[str, Any]) -> bool:
    if field == "basics":
        return all(values.get(name) for name in ("name", "pitch", "sector", "stage", "country"))
    if field == "description":
        return bool(values.get("description"))
    if field == "year_founded":
        return bool(values.get("year_founded"))
    if field == "website":
        return bool(values.get("website_url"))
    if field == "traction":
        return int(values.get("traction_count", 0)) >= 1
    if field == "team":
        return int(values.get("team_count", 0)) >= 2
    return False


def completeness(values: Mapping[str, Any]) -> tuple[int, str | None]:
    total = sum(weight for _, weight in COMPLETENESS)
    earned = 0
    next_missing: str | None = None
    for field, weight in COMPLETENESS:
        if is_filled(field, values):
            earned += weight
        elif next_missing is None:
            next_missing = field
    return round(earned * 100 / total), next_missing
