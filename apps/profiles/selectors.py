"""Read side of profiles. All visibility decisions happen here."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from django.db.models import Count

from apps.accounts import services as accounts
from apps.core.visibility import Audience, audience_for, effective_levels, project
from apps.profiles import domain
from apps.profiles.models import FounderProfile
from apps.profiles.services import get_or_create_profile, values_of
from apps.uploads import services as uploads


def levels_of(profile: FounderProfile) -> dict[str, str]:
    return effective_levels(profile.visibility, domain.DEFAULT_LEVELS)


def _groups(profile: FounderProfile) -> dict[str, dict[str, Any]]:
    skills = [{"slug": s.slug, "name": s.name} for s in profile.skills.all()]
    return {
        "basics": {
            "full_name": profile.full_name,
            "headline": profile.headline,
            "photo": uploads.image_urls(profile.photo_key),
        },
        "bio": {"bio": profile.bio},
        "location": {"country": profile.country, "city": profile.city},
        "skills": {"skills": skills, "custom_skills": profile.custom_skills},
        "links": {
            "linkedin_url": profile.linkedin_url,
            "x_url": profile.x_url,
            "website_url": profile.website_url,
        },
        "open_to": {"open_to": profile.open_to},
    }


def project_profile(
    profile: FounderProfile, audience: Audience, badges: list[str] | None = None
) -> dict[str, Any] | None:
    """What ``audience`` may see of a profile, or None if not even the basics.

    A member who hides the basics group is invisible to that audience, so the
    caller should answer 404 rather than reveal that the profile exists.
    """
    levels = levels_of(profile)
    visible = project(_groups(profile), levels, audience)
    if "full_name" not in visible:
        return None
    visible.update(user_id=profile.user_id, slug=profile.slug, badges=badges or [])
    return visible


def owner_view(profile: FounderProfile, badges: list[str]) -> dict[str, Any]:
    """Everything, plus the settings that only the owner needs."""
    full = project(_groups(profile), levels_of(profile), Audience.OWNER)
    score, next_missing = domain.completeness(values_of(profile))
    full.update(
        user_id=profile.user_id,
        slug=profile.slug,
        badges=badges,
        visibility=levels_of(profile),
        completeness={"score": score, "next_missing_field": next_missing},
    )
    return full


def own_profile(user_id: UUID) -> tuple[FounderProfile, dict[str, Any]]:
    profile = get_or_create_profile(user_id)
    badges = accounts.badges_for([user_id]).get(user_id, [])
    return profile, owner_view(profile, badges)


def profile_for_viewer(viewer: Any, user_id: UUID) -> dict[str, Any] | None:
    profile = FounderProfile.objects.filter(user_id=user_id).prefetch_related("skills").first()
    if profile is None:
        return None
    audience = audience_for(viewer, frozenset({profile.user_id}))
    badges = accounts.badges_for([user_id]).get(user_id, [])
    return project_profile(profile, audience, badges)


@dataclass(frozen=True)
class PublicProfileSource:
    """A profile as the public may see it, for the directory's read model."""

    user_id: UUID
    slug: str
    view: dict[str, Any]
    created_at: datetime


def public_source(user_id: UUID) -> PublicProfileSource | None:
    """None unless the member is active and has made their basics public."""
    profile = FounderProfile.objects.filter(user_id=user_id).prefetch_related("skills").first()
    if profile is None or not accounts.is_active(user_id):
        return None
    badges = accounts.badges_for([user_id]).get(user_id, [])
    view = project_profile(profile, Audience.PUBLIC, badges)
    if view is None:
        return None
    return PublicProfileSource(user_id, profile.slug, view, profile.created_at)


def profile_user_ids() -> list[UUID]:
    """Every member who has a profile; the directory decides who qualifies."""
    return list(FounderProfile.objects.values_list("user_id", flat=True))


def count_by_skill(slugs: list[str]) -> dict[str, int]:
    rows = (
        FounderProfile.objects.filter(skills__slug__in=slugs)
        .values("skills__slug")
        .annotate(n=Count("id"))
    )
    return {row["skills__slug"]: row["n"] for row in rows}


def cards_for(viewer: Any, user_ids: list[UUID]) -> dict[UUID, dict[str, Any]]:
    """Name, headline and photo for each user, as ``viewer`` may see them.

    Someone who hides their basics from the viewer (``hidden``) appears as an anonymous member,
    so a card never reveals more than the profile page would.
    """
    cards: dict[UUID, dict[str, Any]] = {
        uid: {
            "id": uid,
            "name": "Community member",
            "headline": "",
            "photo": None,
            "slug": None,
            "hidden": False,
        }
        for uid in user_ids
    }
    for profile in FounderProfile.objects.filter(user_id__in=user_ids):
        groups = {
            "basics": {
                "full_name": profile.full_name,
                "headline": profile.headline,
                "photo": uploads.image_urls(profile.photo_key),
            }
        }
        visible = project(
            groups, levels_of(profile), audience_for(viewer, frozenset({profile.user_id}))
        )
        if "full_name" not in visible:
            cards[profile.user_id]["hidden"] = True  # their basics are hidden from this viewer
        else:
            cards[profile.user_id].update(
                name=visible["full_name"],
                headline=visible.get("headline", ""),
                photo=visible.get("photo"),
                slug=profile.slug,
            )
    return cards


# --- for segments: who has which profile attributes ---


def ids_by_country(codes: list[str]) -> Any:
    return FounderProfile.objects.filter(country__in=[c.upper() for c in codes]).values_list(
        "user_id", flat=True
    )


def ids_with_skills(slugs: list[str]) -> Any:
    return FounderProfile.objects.filter(skills__slug__in=slugs).values_list("user_id", flat=True)


def ids_by_completeness(low: int = 0, high: int = 100) -> Any:
    return FounderProfile.objects.filter(
        completeness_score__gte=low, completeness_score__lte=high
    ).values_list("user_id", flat=True)


def first_names(user_ids: list[UUID]) -> dict[UUID, str]:
    """The first word of each member's own name, for greeting them in mail."""
    rows = FounderProfile.objects.filter(user_id__in=user_ids).values_list("user_id", "full_name")
    return {uid: name.split()[0] for uid, name in rows if name.strip()}


def active_member_counts_by_country() -> dict[str, int]:
    """How many active members have each country on their profile."""
    rows = (
        FounderProfile.objects.filter(user_id__in=accounts.active_user_ids())
        .exclude(country="")
        .values("country")
        .annotate(n=Count("id"))
    )
    return {row["country"]: row["n"] for row in rows}


def full_name_of(user_id: UUID) -> str:
    """The name on the member's own profile, whatever its visibility (for their own documents)."""
    return (
        FounderProfile.objects.filter(user_id=user_id).values_list("full_name", flat=True).first()
        or ""
    )
