"""Following members and startups.

Following is private to the follower: nobody is told who follows them (counts and notices can be
added later without changing this). A follow stays on record if its target is later suspended or
hidden, but it stops having any effect until the target is visible again.
"""

from typing import Any
from uuid import UUID

from django.db import IntegrityError, transaction
from django.db.models import QuerySet
from rest_framework import exceptions

from apps.accounts import services as accounts
from apps.core.keyset import paginate
from apps.feed.models import Follow
from apps.profiles import selectors as profiles
from apps.startups import selectors as startups

MAX_FOLLOWS = 500


def _check_target(viewer: Any, kind: str, target_id: UUID) -> None:
    """The target must exist and be something the follower can see."""
    not_found = exceptions.NotFound("Nothing to follow here.")
    if kind == Follow.Kind.MEMBER:
        if target_id == viewer.pk:
            raise exceptions.ValidationError({"id": ["You cannot follow yourself."]})
        if not accounts.is_active(target_id):
            raise not_found
        if profiles.cards_for(viewer, [target_id])[target_id]["hidden"]:
            raise not_found  # their profile basics are hidden from you
    else:
        startup = startups.get_startup(target_id)
        if startup is None or not accounts.is_active(startup.owner_id):
            raise not_found
        if startups.startup_for_viewer(viewer, target_id) is None:
            raise not_found


def follow(*, viewer: Any, kind: str, target_id: UUID) -> bool:
    """Start following. Returns False when the member already did."""
    _check_target(viewer, kind, target_id)
    try:
        with transaction.atomic():
            if Follow.objects.filter(follower_id=viewer.pk).count() >= MAX_FOLLOWS:
                raise exceptions.ValidationError(
                    {"id": [f"You can follow up to {MAX_FOLLOWS} members and startups."]}
                )
            _, created = Follow.objects.get_or_create(
                follower_id=viewer.pk, followee_type=kind, followee_id=target_id
            )
    except IntegrityError:  # a concurrent identical request won the race
        return False
    return created


def unfollow(*, user_id: UUID, kind: str, target_id: UUID) -> bool:
    removed, _ = Follow.objects.filter(
        follower_id=user_id, followee_type=kind, followee_id=target_id
    ).delete()
    return bool(removed)


def followed_ids(user_id: UUID, kind: str) -> QuerySet[Follow, UUID]:
    return Follow.objects.filter(follower_id=user_id, followee_type=kind).values_list(
        "followee_id", flat=True
    )


def is_following(user_id: UUID, kind: str, ids: list[UUID]) -> set[UUID]:
    """Which of ``ids`` the member follows."""
    return set(followed_ids(user_id, kind).filter(followee_id__in=ids))


def following(viewer: Any, *, kind: str, cursor: str, limit: int) -> dict[str, Any]:
    """Who the member follows, newest first. Targets they can no longer see are left out."""
    queryset = Follow.objects.filter(follower_id=viewer.pk)
    if kind:
        queryset = queryset.filter(followee_type=kind)
    rows, next_cursor = paginate(
        queryset,
        fields=("created_at", "id"),
        sort=f"following:{kind}",
        cursor=cursor,
        limit=limit,
    )
    members = [r.followee_id for r in rows if r.followee_type == Follow.Kind.MEMBER]
    member_cards = profiles.cards_for(viewer, members)
    active = set(accounts.filter_active(members))
    startup_cards = startups.cards_for(
        viewer, [r.followee_id for r in rows if r.followee_type == Follow.Kind.STARTUP]
    )
    results = []
    for row in rows:
        item: dict[str, Any] | None = None
        if row.followee_type == Follow.Kind.MEMBER:
            card = member_cards[row.followee_id]
            if row.followee_id in active and not card["hidden"]:
                item = {"name": card["name"], "headline": card["headline"], "image": card["photo"]}
                item["slug"] = card["slug"]
        elif row.followee_id in startup_cards:
            card = startup_cards[row.followee_id]
            item = {
                "name": card["name"],
                "headline": "",
                "image": card["logo"],
                "slug": card["slug"],
            }
        if item is not None:
            results.append(
                {
                    "type": row.followee_type,
                    "id": row.followee_id,
                    "followed_at": row.created_at,
                    **item,
                }
            )
    return {"results": results, "next_cursor": next_cursor}
