"""Who joined through whom: the search people use while signing up, a member's own list, and the
figures the console shows.

A person counts as referred when they named a member (or opened that member's link). A referral
counts for the referrer only once the person is approved, so nobody is credited for sign ups that
are later turned away.
"""

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from django.conf import settings
from django.db.models import Count, Q
from django.utils import timezone

from apps.accounts import referrals
from apps.accounts.models import User
from apps.profiles import selectors as profiles
from apps.profiles.models import FounderProfile
from apps.startups import selectors as startups

MIN_QUERY = 3
SEARCH_LIMIT = 5
OVERFETCH = 4


def link_for(code: str) -> str:
    return f"{settings.FRONTEND_BASE_URL}/join?ref={code}"


def _startup_names(viewer: Any, user_ids: list[UUID]) -> dict[UUID, str]:
    """The first startup of each person, as the viewer may see it."""
    first: dict[UUID, UUID] = {}
    for uid in user_ids:
        ids = startups.startup_ids_of_member(uid)
        if ids:
            first[uid] = ids[0]
    cards = startups.cards_for(viewer, list(first.values()))
    return {
        uid: str(cards[sid]["name"])
        for uid, sid in first.items()
        if sid in cards and cards[sid].get("name")
    }


def search_referrers(query: str) -> list[dict[str, Any]]:
    """Active members a newcomer can name, found by name or by their exact email address.

    This is open to people who have no account yet, so it is deliberately narrow: at least three
    letters, at most five answers, only people whose name is public, and an email address finds
    someone only when it is typed in full. The caller is throttled by address.
    """
    term = query.strip()
    if len(term) < MIN_QUERY:
        return []
    by_email = User.objects.filter(email__iexact=term, status="active").values("id")
    candidates = (
        FounderProfile.objects.filter(user__status="active")
        .filter(Q(full_name__icontains=term) | Q(user_id__in=by_email))
        .order_by("full_name", "pk")[: SEARCH_LIMIT * OVERFETCH]
    )
    ids = [p.user_id for p in candidates]
    cards = profiles.cards_for(None, ids)  # None: what a visitor may see
    shown = [uid for uid in ids if not cards[uid]["hidden"]][:SEARCH_LIMIT]
    names = _startup_names(None, shown)
    return [
        {
            "id": uid,
            "name": cards[uid]["name"],
            "headline": cards[uid]["headline"],
            "photo": cards[uid]["photo"],
            "startup": names.get(uid, ""),
        }
        for uid in shown
    ]


def my_referrals(user: User) -> dict[str, Any]:
    """The member's code and link, and who has joined (and been approved) through them."""
    code = referrals.ensure_code(user)
    joined = list(
        User.objects.filter(referred_by=user, status="active").order_by(
            "-approved_at", "-created_at"
        )
    )
    ids = [u.pk for u in joined]
    cards = profiles.cards_for(user, ids)
    names = _startup_names(user, ids)
    waiting = User.objects.filter(referred_by=user, status="pending").count()
    return {
        "code": code,
        "url": link_for(code),
        "approved_count": len(joined),
        "waiting_count": waiting,
        "members": [
            {
                "id": u.pk,
                "name": cards[u.pk]["name"],
                "startup": names.get(u.pk, ""),
                "joined_at": u.approved_at or u.created_at,
            }
            for u in joined
        ],
    }


# --- the console ---


def month_bounds(now: datetime) -> tuple[datetime, datetime, datetime]:
    """The start of last month, of this month, and the moment asked."""
    this = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last = (this.replace(day=1) - timedelta(days=1)).replace(day=1)
    return last, this, now


def _window(start: datetime, end: datetime) -> dict[str, int]:
    rows = User.objects.filter(created_at__gte=start, created_at__lt=end)
    counts = rows.aggregate(
        signups=Count("id"),
        referred=Count("id", filter=Q(referred_by__isnull=False)),
        approved=Count("id", filter=Q(referred_by__isnull=False, status="active")),
    )
    return {k: int(v) for k, v in counts.items()}


def summary(now: datetime | None = None) -> dict[str, Any]:
    """This month against last: sign ups, how many were referred, and where people heard of us."""
    last, this, moment = month_bounds(now or timezone.now())
    current = _window(this, moment + timedelta(microseconds=1))
    previous = _window(last, this)
    sources = (
        User.objects.filter(created_at__gte=this)
        .values("referral_source")
        .annotate(n=Count("id"))
        .order_by("-n")
    )
    breakdown = [
        {
            "kind": row["referral_source"] or "none",
            "kind_label": referrals.SOURCE_LABELS.get(row["referral_source"], "Did not say"),
            "count": row["n"],
        }
        for row in sources
    ]
    share = round(100 * current["referred"] / current["signups"]) if current["signups"] else 0
    return {
        "this_month": current,
        "last_month": previous,
        "referred_share": share,
        "sources": breakdown,
    }


def top_referrers(limit: int = 10) -> list[dict[str, Any]]:
    """Members with the most approved referrals, most first."""
    rows = (
        User.objects.filter(referrals__status="active")
        .annotate(n=Count("referrals", filter=Q(referrals__status="active")))
        .order_by("-n", "created_at")[:limit]
    )
    people = list(rows)
    names = dict(
        FounderProfile.objects.filter(user_id__in=[p.pk for p in people]).values_list(
            "user_id", "full_name"
        )
    )
    return [
        {"id": p.pk, "name": names.get(p.pk) or p.email.split("@")[0], "approved": p.n}
        for p in people
    ]


def referrer_for_link(code: str) -> dict[str, Any]:
    """Who a referral link belongs to, as a visitor may see them, so the form can say so.

    A member who keeps their name from visitors is still a valid referrer; they appear without a
    name or an id, and the code itself ties the sign up to them.
    """
    owner = referrals.referrer_for_code(code)
    if owner is None:
        return {"found": False, "id": None, "name": "", "startup": "", "photo": None}
    card = profiles.cards_for(None, [owner.pk])[owner.pk]
    if card["hidden"]:
        return {
            "found": True,
            "id": None,
            "name": "A WO Community member",
            "startup": "",
            "photo": None,
        }
    names = _startup_names(None, [owner.pk])
    return {
        "found": True,
        "id": owner.pk,
        "name": card["name"],
        "startup": names.get(owner.pk, ""),
        "photo": card["photo"],
    }
