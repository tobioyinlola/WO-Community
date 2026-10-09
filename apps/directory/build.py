"""Turns public projections into read model rows.

Everything here starts from data the visibility rule already approved for the
public. Nothing is read from private fields, and a group that is not public is
simply absent from the source, so it cannot reach a row.
"""

from typing import Any

from django.conf import settings

from apps.profiles.selectors import PublicProfileSource
from apps.startups.selectors import PublicStartupSource


def page_url(kind: str, slug: str) -> str:
    return f"{settings.FRONTEND_BASE_URL}/{kind}/{slug}"


def newest_key(created_at: Any) -> int:
    """Minus the creation time in microseconds, so ascending order is newest first."""
    return -int(created_at.timestamp() * 1_000_000)


def _skills(view: dict[str, Any]) -> list[dict[str, str]]:
    return [{"slug": s["slug"], "name": s["name"]} for s in view.get("skills", [])]


def build_startup(src: PublicStartupSource, founders: list[PublicProfileSource]) -> dict[str, Any]:
    view = src.view
    founder_cards = [
        {"slug": f.slug, "full_name": f.view["full_name"], "headline": f.view.get("headline", "")}
        for f in founders
    ]
    card: dict[str, Any] = {
        "slug": src.slug,
        "name": view["name"],
        "pitch": view["pitch"],
        "sector": view["sector"],
        "stage": view["stage"],
        "country": view["country"],
        "city": view["city"],
        "year_founded": view.get("year_founded"),
        "featured": src.featured_at is not None,
        "founders": [{"slug": f["slug"], "full_name": f["full_name"]} for f in founder_cards],
    }
    detail: dict[str, Any] = {
        **card,
        "founders": founder_cards,
        "traction": [
            {"kind": t["kind"], "value": t["value"], "as_of_date": t["as_of_date"]}
            for t in view.get("traction", [])
        ],
    }
    for optional in ("description", "website_url"):
        if optional in view:
            detail[optional] = view[optional]
    detail["url"] = page_url("startups", src.slug)
    detail["structured_data"] = _organization(detail)

    skills: dict[str, str] = {}
    for founder in founders:
        for skill in _skills(founder.view):
            skills[skill["slug"]] = skill["name"]
    return {
        "startup_id": src.startup_id,
        "owner_id": src.owner_id,
        "slug": src.slug,
        "name": view["name"],
        "country": view["country"],
        "sector_slug": view["sector"]["slug"],
        "stage_slug": view["stage"]["slug"],
        "skill_slugs": sorted(skills),
        "featured_rank": 0 if src.featured_at else 1,
        "newest_key": newest_key(src.created_at),
        "name_key": view["name"].casefold()[:120],
        "pitch": view["pitch"],
        "description": view.get("description", ""),
        "city": view["city"],
        "sector_name": view["sector"]["name"],
        "founder_names": ", ".join(f["full_name"] for f in founder_cards),
        "skill_names": ", ".join(skills.values()),
        "card": card,
        "detail": detail,
    }


def _organization(detail: dict[str, Any]) -> dict[str, Any]:
    data: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": detail["name"],
        "url": detail["url"],
        "description": detail["pitch"],
        "address": {
            "@type": "PostalAddress",
            "addressCountry": detail["country"],
            "addressLocality": detail["city"],
        },
    }
    if detail.get("year_founded"):
        data["foundingDate"] = str(detail["year_founded"])
    if detail.get("website_url"):
        data["sameAs"] = [detail["website_url"]]
    return data


def build_founder(src: PublicProfileSource, startups: list[PublicStartupSource]) -> dict[str, Any]:
    view = src.view
    card: dict[str, Any] = {
        "slug": src.slug,
        "full_name": view["full_name"],
        "badges": view.get("badges", []),
    }
    for optional in ("headline", "country", "city"):
        if optional in view:
            card[optional] = view[optional]
    if "skills" in view:
        card["skills"] = _skills(view)

    linked = [
        {
            "slug": s.slug,
            "name": s.view["name"],
            "pitch": s.view["pitch"],
            "sector": s.view["sector"],
        }
        for s in startups
    ]
    detail: dict[str, Any] = {**card, "startups": linked}
    for optional in ("bio", "custom_skills", "open_to", "linkedin_url", "x_url", "website_url"):
        if optional in view:
            detail[optional] = view[optional]
    detail["url"] = page_url("founders", src.slug)
    detail["structured_data"] = _person(detail)

    skills = _skills(view)
    return {
        "user_id": src.user_id,
        "slug": src.slug,
        "full_name": view["full_name"],
        "country": view.get("country", ""),
        "skill_slugs": sorted(s["slug"] for s in skills),
        "startup_slugs": sorted(s["slug"] for s in linked),
        "newest_key": newest_key(src.created_at),
        "name_key": view["full_name"].casefold()[:120],
        "headline": view.get("headline", ""),
        "bio": view.get("bio", ""),
        "city": view.get("city", ""),
        "skill_names": ", ".join(s["name"] for s in skills),
        "startup_names": ", ".join(s["name"] for s in linked),
        "card": card,
        "detail": detail,
    }


def _person(detail: dict[str, Any]) -> dict[str, Any]:
    data: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "Person",
        "name": detail["full_name"],
        "url": detail["url"],
    }
    if detail.get("headline"):
        data["jobTitle"] = detail["headline"]
    if detail.get("bio"):
        data["description"] = detail["bio"]
    if detail.get("country") or detail.get("city"):
        data["address"] = {
            "@type": "PostalAddress",
            "addressCountry": detail.get("country", ""),
            "addressLocality": detail.get("city", ""),
        }
    links = [detail[k] for k in ("linkedin_url", "x_url", "website_url") if detail.get(k)]
    if links:
        data["sameAs"] = links
    if detail["startups"]:
        data["worksFor"] = [
            {
                "@type": "Organization",
                "name": s["name"],
                "url": page_url("startups", s["slug"]),
            }
            for s in detail["startups"]
        ]
    return data
