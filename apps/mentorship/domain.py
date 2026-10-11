"""Rules for what a mentor says about themselves, shared by applications and profiles."""

from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from rest_framework import exceptions

from apps.core.text import clean_url, plain
from apps.reference import selectors as reference

LANGUAGES = {
    "en": "English",
    "fr": "French",
    "pt": "Portuguese",
    "es": "Spanish",
    "ar": "Arabic",
    "sw": "Swahili",
    "yo": "Yoruba",
    "ig": "Igbo",
    "ha": "Hausa",
    "am": "Amharic",
    "zu": "Zulu",
    "af": "Afrikaans",
    "de": "German",
    "hi": "Hindi",
    "zh": "Chinese",
}
MAX_EXPERTISE = 8
MAX_INDUSTRIES = 5
MAX_STAGES = 4
MAX_LANGUAGES = 5
MIN_MOTIVATION = 50
MAX_MOTIVATION = 1500
MAX_ABOUT = 1000
CONDUCT_VERSION = "2026-01"


def invalid(field: str, message: str) -> exceptions.ValidationError:
    return exceptions.ValidationError({field: [message]})


def expertise(value: Any) -> list[str]:
    tags: list[str] = []
    for raw in value:
        tag = " ".join(plain(str(raw)).lower().split())
        if not 2 <= len(tag) <= 50:
            raise invalid("expertise", "Each area must be 2 to 50 characters.")
        if tag not in tags:
            tags.append(tag)
    if not 1 <= len(tags) <= MAX_EXPERTISE:
        raise invalid("expertise", f"Give 1 to {MAX_EXPERTISE} areas of expertise.")
    return tags


def years(value: int) -> int:
    if not 1 <= value <= 60:
        raise invalid("years_experience", "Between 1 and 60 years.")
    return value


def text(field: str, value: str, *, limit: int, minimum: int = 1) -> str:
    cleaned = plain(value)
    if len(cleaned) < minimum:
        raise invalid(
            field,
            "This field may not be blank." if minimum <= 1 else f"At least {minimum} characters.",
        )
    if len(cleaned) > limit:
        raise invalid(field, f"Up to {limit} characters.")
    return cleaned


def linkedin(value: str) -> str:
    try:
        url = clean_url(value, hosts=("linkedin.com",))
    except exceptions.ValidationError as exc:
        raise invalid("linkedin_url", " ".join(str(m) for m in exc.detail)) from exc
    if not url:
        raise invalid("linkedin_url", "This field may not be blank.")
    return url


def industries(slugs: list[str]) -> list[str]:
    unique = list(dict.fromkeys(slugs))
    if not 1 <= len(unique) <= MAX_INDUSTRIES:
        raise invalid("industries", f"Choose 1 to {MAX_INDUSTRIES} industries.")
    known = {s.slug for s in reference.sectors().filter(slug__in=unique)}
    if set(unique) - known:
        raise invalid("industries", "Choose industries from the list.")
    return unique


def stages(slugs: list[str]) -> list[str]:
    unique = list(dict.fromkeys(slugs))
    if not 1 <= len(unique) <= MAX_STAGES:
        raise invalid("stages", f"Choose 1 to {MAX_STAGES} stages.")
    known = {s.slug for s in reference.stages().filter(slug__in=unique)}
    if set(unique) - known:
        raise invalid("stages", "Choose stages from the list.")
    return unique


def languages(codes: list[str]) -> list[str]:
    unique = list(dict.fromkeys(codes))
    if not 1 <= len(unique) <= MAX_LANGUAGES:
        raise invalid("languages", f"Choose 1 to {MAX_LANGUAGES} languages.")
    if set(unique) - set(LANGUAGES):
        raise invalid("languages", "Choose languages from the list.")
    return unique


def timezone_name(value: str) -> str:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError, OSError) as exc:
        raise invalid("timezone", "Use a time zone name such as Africa/Lagos.") from exc
    return value


def weekly_hours(value: int) -> int:
    if not 1 <= value <= 40:
        raise invalid("weekly_hours", "Between 1 and 40 hours.")
    return value


def capacity(value: int) -> int:
    if not 1 <= value <= 20:
        raise invalid("capacity_per_week", "Between 1 and 20 sessions a week.")
    return value


def clean_fields(data: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalise whichever of the shared fields are present."""
    out: dict[str, Any] = {}
    if "expertise" in data:
        out["expertise"] = expertise(data["expertise"])
    if "years_experience" in data:
        out["years_experience"] = years(data["years_experience"])
    if "current_role" in data:
        out["current_role"] = text("current_role", data["current_role"], limit=120)
    if "company" in data:
        out["company"] = text("company", data["company"], limit=120)
    if "industries" in data:
        out["industries"] = industries(data["industries"])
    if "stages" in data:
        out["stages"] = stages(data["stages"])
    if "languages" in data:
        out["languages"] = languages(data["languages"])
    if "timezone" in data:
        out["timezone"] = timezone_name(data["timezone"])
    return out
