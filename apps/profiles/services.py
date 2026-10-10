"""Commands that change founder profiles."""

import secrets
from typing import Any
from uuid import UUID

from django.db import IntegrityError, transaction
from django.utils.text import slugify
from rest_framework import exceptions

from apps.analytics import services as analytics
from apps.core import etag
from apps.core import events as domain_events
from apps.core.visibility import LEVELS
from apps.profiles import domain, events
from apps.profiles.models import FounderProfile
from apps.reference import selectors as reference
from apps.uploads import services as uploads

SIMPLE_FIELDS = (
    "full_name",
    "headline",
    "bio",
    "country",
    "city",
    "linkedin_url",
    "x_url",
    "website_url",
)


def _new_slug(name: str) -> str:
    base = slugify(name)[:40] or "member"
    return f"{base}-{secrets.token_hex(3)}"


def get_or_create_profile(user_id: UUID) -> FounderProfile:
    profile = FounderProfile.objects.filter(user_id=user_id).first()
    if profile is not None:
        return profile
    try:
        with transaction.atomic():
            return FounderProfile.objects.create(user_id=user_id, slug=_new_slug(""))
    except IntegrityError:  # another request created it first
        return FounderProfile.objects.get(user_id=user_id)


def values_of(profile: FounderProfile) -> dict[str, Any]:
    """Profile values in the shape the completeness rules read."""
    values: dict[str, Any] = {name: getattr(profile, name) for name in SIMPLE_FIELDS}
    values["skills"] = profile.skills.exists() if profile.pk else False
    values["custom_skills"] = profile.custom_skills
    values["open_to"] = profile.open_to
    values["photo"] = profile.photo_key
    return values


def _refresh_completeness(profile: FounderProfile) -> None:
    profile.completeness_score, _ = domain.completeness(values_of(profile))


def _announce(profile: FounderProfile) -> None:
    """Tell the directory and analytics that a profile changed."""
    domain_events.publish(events.ProfileUpdated(user_id=str(profile.user_id)))
    analytics.track(
        "profile_updated",
        actor_id=profile.user_id,
        properties={"completeness": profile.completeness_score},
    )


def create_from_signup(user_id: UUID, details: dict[str, Any]) -> FounderProfile:
    """Fill the profile from the registration form. Safe to run twice."""
    profile = get_or_create_profile(user_id)
    if profile.full_name:
        return profile
    profile.full_name = details["full_name"]
    profile.country = details["country"]
    profile.city = details["city"]
    if profile.slug.startswith("member-"):
        profile.slug = _new_slug(details["full_name"])
    _refresh_completeness(profile)
    profile.save()
    return profile


def update_profile(*, user_id: UUID, data: dict[str, Any], if_match: str | None) -> FounderProfile:
    """Apply a partial update. ``data`` is already validated and cleaned."""
    get_or_create_profile(user_id)
    with transaction.atomic():
        profile = FounderProfile.objects.select_for_update().get(user_id=user_id)
        etag.assert_matches(if_match, profile)
        for field in SIMPLE_FIELDS:
            if field in data:
                setattr(profile, field, data[field])
        if "custom_skills" in data:
            profile.custom_skills = data["custom_skills"]
        if "open_to" in data:
            profile.open_to = data["open_to"]
        if "skills" in data:
            chosen = reference.skills_by_slug(data["skills"])
            if len(chosen) != len(set(data["skills"])):
                raise exceptions.ValidationError({"skills": ["Choose skills from the list."]})
            profile.skills.set(chosen)
        _refresh_completeness(profile)
        profile.save()
        _announce(profile)
    return profile


def update_visibility(*, user_id: UUID, levels: dict[str, str]) -> FounderProfile:
    unknown = sorted(set(levels) - set(domain.GROUP_FIELDS))
    if unknown:
        raise exceptions.ValidationError({name: ["Unknown field group."] for name in unknown})
    bad = sorted(name for name, level in levels.items() if level not in LEVELS)
    if bad:
        raise exceptions.ValidationError(
            {name: [f"Choose one of: {', '.join(LEVELS)}."] for name in bad}
        )
    get_or_create_profile(user_id)
    with transaction.atomic():
        profile = FounderProfile.objects.select_for_update().get(user_id=user_id)
        profile.visibility = {**profile.visibility, **levels}
        profile.save()
        _announce(profile)
    return profile


def set_photo(*, user_id: UUID, upload_id: UUID, if_match: str | None) -> FounderProfile:
    """Use a finished upload as the profile photo, replacing and deleting the old one."""
    get_or_create_profile(user_id)
    with transaction.atomic():
        profile = FounderProfile.objects.select_for_update().get(user_id=user_id)
        etag.assert_matches(if_match, profile)
        upload = uploads.claim(upload_id=upload_id, owner_id=user_id, purpose="profile_photo")
        previous = profile.photo_key
        profile.photo_key = upload.base_key
        _refresh_completeness(profile)
        profile.save()
        uploads.release(previous)
        _announce(profile)
    return profile


def clear_photo(*, user_id: UUID, if_match: str | None) -> FounderProfile:
    get_or_create_profile(user_id)
    with transaction.atomic():
        profile = FounderProfile.objects.select_for_update().get(user_id=user_id)
        etag.assert_matches(if_match, profile)
        previous = profile.photo_key
        profile.photo_key = ""
        _refresh_completeness(profile)
        profile.save()
        uploads.release(previous)
        _announce(profile)
    return profile
