"""Whom a member might want to follow.

Suggestions are scored from what the two people share and from who the member already follows:
the same sector or stage in their startups, the same country, and how many of the people they
follow already follow the candidate. Members who are active in the feed score a little higher, so
someone new is not shown a ghost town. Only people whose profile basics the member can see are
suggested, and never someone already followed, themselves, or anyone who is not an active member.
"""

from datetime import timedelta
from typing import Any
from uuid import UUID

from django.db.models import Count
from django.utils import timezone

from apps.accounts import services as accounts
from apps.feed import selectors
from apps.feed.models import Follow
from apps.profiles import selectors as profiles
from apps.profiles.models import FounderProfile
from apps.startups import selectors as startups

POOL = 400  # candidates scored per request
WEIGHTS = {"sector": 3, "stage": 2, "country": 2, "social": 2, "active": 1, "mentor": 1}
MAX_SOCIAL = 3
ACTIVE_DAYS = 30


def suggest(viewer: Any, *, limit: int) -> list[dict[str, Any]]:
    followed = set(
        Follow.objects.filter(follower_id=viewer.pk, followee_type=Follow.Kind.MEMBER).values_list(
            "followee_id", flat=True
        )
    )
    pairs = startups.sector_stage_of_member(viewer.pk)
    sectors = {s for s, _ in pairs if s}
    stages = {t for _, t in pairs if t}
    country = (
        FounderProfile.objects.filter(user_id=viewer.pk).values_list("country", flat=True).first()
        or ""
    )

    same_sector = startups.member_ids_by_sector(list(sectors)) if sectors else set()
    same_stage = startups.member_ids_by_stage(list(stages)) if stages else set()
    same_country = set(profiles.ids_by_country([country])) if country else set()
    active = selectors.active_author_ids(timezone.now() - timedelta(days=ACTIVE_DAYS))
    mentors = set(accounts.ids_with_roles(["mentor"]))
    social: dict[UUID, int] = {}
    if followed:
        rows = (
            Follow.objects.filter(follower_id__in=followed, followee_type=Follow.Kind.MEMBER)
            .values("followee_id")
            .annotate(n=Count("id"))
        )
        social = {row["followee_id"]: row["n"] for row in rows}

    candidates = same_sector | same_stage | same_country | set(social)
    if len(candidates) < limit * 3:
        candidates |= set(active)  # little in common yet: fall back to who is around
    candidates -= followed | {viewer.pk}
    pool = list(accounts.filter_active(list(candidates)))[: POOL * 3]
    cards = profiles.cards_for(viewer, pool)

    scored: list[tuple[int, str, dict[str, Any]]] = []
    for user_id in pool:
        card = cards[user_id]
        if card["hidden"] or not card["slug"]:
            continue  # their basics are hidden from this member, or there is no profile yet
        reasons: list[str] = []
        score = 0
        if user_id in same_sector:
            score += WEIGHTS["sector"]
            reasons.append("Works in your sector")
        if user_id in same_stage:
            score += WEIGHTS["stage"]
            reasons.append("At your startup's stage")
        if user_id in same_country:
            score += WEIGHTS["country"]
            reasons.append("In your country")
        if user_id in social:
            shared = min(social[user_id], MAX_SOCIAL)
            score += WEIGHTS["social"] * shared
            reasons.append(
                "Followed by someone you follow"
                if social[user_id] == 1
                else f"Followed by {social[user_id]} people you follow"
            )
        if user_id in active:
            score += WEIGHTS["active"]
        if user_id in mentors:
            score += WEIGHTS["mentor"]
            reasons.append("A mentor")
        scored.append(
            (
                score,
                str(user_id),
                {
                    "id": user_id,
                    "name": card["name"],
                    "headline": card["headline"],
                    "image": card["photo"],
                    "slug": card["slug"],
                    "score": score,
                    "reasons": reasons,
                },
            )
        )
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [item for _, _, item in scored[:limit]]
