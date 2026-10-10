"""Public read side of the reference lists."""

from collections.abc import Iterable
from typing import Any

from apps.reference.countries import COUNTRIES
from apps.reference.models import Sector, Skill, Stage


def countries() -> list[dict[str, str]]:
    return [
        {"code": code, "name": name} for code, name in sorted(COUNTRIES.items(), key=lambda i: i[1])
    ]


def is_country(code: str) -> bool:
    return code in COUNTRIES


def country_name(code: str) -> str:
    return COUNTRIES.get(code, "")


def sectors() -> Any:
    return Sector.objects.filter(active=True)


def stages() -> Any:
    return Stage.objects.filter(active=True)


def skills() -> Any:
    return Skill.objects.filter(active=True)


def get_sector(slug: str) -> Sector | None:
    return Sector.objects.filter(slug=slug, active=True).first()


def get_stage(slug: str) -> Stage | None:
    return Stage.objects.filter(slug=slug, active=True).first()


def skills_by_slug(slugs: Iterable[str]) -> list[Skill]:
    """Active skills for the given slugs, in no particular order. Unknown slugs are missing."""
    return list(Skill.objects.filter(slug__in=list(slugs), active=True))
