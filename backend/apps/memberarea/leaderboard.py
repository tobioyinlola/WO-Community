"""The community leaderboard: members ranked by what they did on the platform lately.

Points come from the source tables, counted over the last ``PERIOD_DAYS``:

    a post 10, a comment 5, a comment on a news story 5, a reaction given 1 (to posts, comments
    or news), a reaction received on a post 2, and each day signed in 3.

Only active members count; staff accounts that are not members are left out. Hidden or deleted
posts and comments earn nothing, and reacting to your own post earns nothing. The ranking is
worked out at most every few minutes and cached, since every member's dashboard shows it.
"""

from collections import Counter
from datetime import timedelta
from typing import Any
from uuid import UUID

from django.core.cache import cache
from django.db.models import Count
from django.db.models.functions import TruncDate
from django.utils import timezone

from apps.accounts import selectors as accounts
from apps.accounts import services as account_services
from apps.audit.models import AuditLog
from apps.editorial.models import ItemComment, ItemReaction
from apps.feed.models import Comment, Post, Reaction
from apps.profiles import selectors as profiles

PERIOD_DAYS = 30
TOP = 10
CACHE_SECONDS = 300

POINTS = {
    "posts": 10,
    "comments": 5,
    "news_comments": 5,
    "reactions_given": 1,
    "reactions_received": 2,
    "login_days": 3,
}
MEMBER_ROLES = ["member", "mentor"]


def _counts(rows: Any, key: str) -> Counter[UUID]:
    return Counter({row[key]: row["n"] for row in rows if row[key] is not None})


def _activity(since: Any) -> dict[str, Counter[UUID]]:
    """What each person did since ``since``, by kind."""
    posts = Post.objects.filter(
        created_at__gte=since, deleted_at__isnull=True, hidden_at__isnull=True
    )
    comments = Comment.objects.filter(
        created_at__gte=since, deleted_at__isnull=True, hidden_at__isnull=True
    )
    news_comments = ItemComment.objects.filter(
        created_at__gte=since, deleted_at__isnull=True, hidden_at__isnull=True
    )
    given = _counts(
        Reaction.objects.filter(created_at__gte=since).values("user_id").annotate(n=Count("id")),
        "user_id",
    )
    given.update(
        _counts(
            ItemReaction.objects.filter(created_at__gte=since)
            .values("user_id")
            .annotate(n=Count("id")),
            "user_id",
        )
    )

    # Reactions received on posts, from other people.
    received: Counter[UUID] = Counter()
    on_posts = list(
        Reaction.objects.filter(target_type="post", created_at__gte=since).values_list(
            "target_id", "user_id"
        )
    )
    authors = dict(
        Post.objects.filter(
            pk__in={target for target, _ in on_posts}, deleted_at__isnull=True
        ).values_list("pk", "author_id")
    )
    for target, reactor in on_posts:
        author = authors.get(target)
        if author is not None and author != reactor:
            received[author] += 1

    login_days: Counter[UUID] = Counter()
    days = (
        AuditLog.objects.filter(action="auth.login", created_at__gte=since, actor_id__isnull=False)
        .annotate(day=TruncDate("created_at"))
        .order_by()  # the log's own ordering would make every row distinct
        .values("actor_id", "day")
        .distinct()
    )
    for row in days:
        login_days[row["actor_id"]] += 1

    return {
        "posts": _counts(posts.values("author_id").annotate(n=Count("id")), "author_id"),
        "comments": _counts(comments.values("author_id").annotate(n=Count("id")), "author_id"),
        "news_comments": _counts(
            news_comments.values("author_id").annotate(n=Count("id")), "author_id"
        ),
        "reactions_given": given,
        "reactions_received": received,
        "login_days": login_days,
    }


def _eligible(user_ids: set[UUID]) -> set[UUID]:
    active = set(accounts.active_user_ids().filter(id__in=user_ids).values_list("id", flat=True))
    members = set(accounts.ids_with_roles(MEMBER_ROLES).filter(user_id__in=active))
    return {UUID(str(u)) for u in members}


def standings() -> list[dict[str, Any]]:
    """Everyone with points, best first, with their rank and how the points were earned.

    Ties share a rank (1, 2, 2, 4); within a tie the order is stable.
    """
    cached = cache.get("leaderboard:v1")
    if cached is not None:
        return list(cached)
    since = timezone.now() - timedelta(days=PERIOD_DAYS)
    activity = _activity(since)
    people = _eligible({uid for counter in activity.values() for uid in counter})
    rows: list[dict[str, Any]] = []
    for uid in people:
        breakdown = {kind: int(activity[kind].get(uid, 0)) for kind in POINTS}
        points = sum(POINTS[kind] * n for kind, n in breakdown.items())
        if points > 0:
            rows.append({"user_id": uid, "points": points, "breakdown": breakdown})
    rows.sort(key=lambda r: (-int(r["points"]), str(r["user_id"])))
    rank, previous = 0, None
    for index, row in enumerate(rows, start=1):
        if row["points"] != previous:
            rank, previous = index, row["points"]
        row["rank"] = rank
    cache.set("leaderboard:v1", rows, CACHE_SECONDS)
    return rows


def for_viewer(viewer: Any) -> dict[str, Any]:
    """The top ten as ``viewer`` may see them, and where the viewer stands."""
    rows = standings()
    top = rows[:TOP]
    cards = profiles.cards_for(viewer, [r["user_id"] for r in top])
    entries = [
        {
            **row,
            "name": cards.get(row["user_id"], {}).get("name", "Community member"),
            "headline": cards.get(row["user_id"], {}).get("headline", ""),
            "photo": cards.get(row["user_id"], {}).get("photo"),
            "is_me": row["user_id"] == viewer.pk,
        }
        for row in top
    ]
    mine = next((r for r in rows if r["user_id"] == viewer.pk), None)
    return {
        "period_days": PERIOD_DAYS,
        "points": POINTS,
        "entries": entries,
        "me": {
            "rank": mine["rank"] if mine else None,
            "points": mine["points"] if mine else 0,
            "breakdown": mine["breakdown"] if mine else dict.fromkeys(POINTS, 0),
            "ranked_members": len(rows),
        },
    }


def for_admins() -> dict[str, Any]:
    """The top ten with real names and email addresses, for the admin console."""
    rows = standings()[:TOP]
    ids = [r["user_id"] for r in rows]
    names = profiles.names_for(ids)
    emails = account_services.emails_for(ids)
    return {
        "period_days": PERIOD_DAYS,
        "points": POINTS,
        "entries": [
            {
                **row,
                "name": names.get(row["user_id"]) or "Name not given",
                "email": emails.get(row["user_id"], ""),
            }
            for row in rows
        ],
    }
