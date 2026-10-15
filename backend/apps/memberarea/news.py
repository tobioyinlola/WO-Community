"""News as it concerns one member: what is about people they follow, and the weekly digest.

The shared news feed is the editorial module's. What follows a member around (startups and people
they follow, an opt-in digest) needs the follows from the feed module too, so it lives here, above
both.
"""

from datetime import timedelta
from typing import Any
from uuid import UUID

import structlog
from django.conf import settings
from django.utils import timezone

from apps.core import ratelimit
from apps.editorial import selectors as editorial
from apps.feed import follows
from apps.feed.models import Follow
from apps.notifications import emails, notify
from apps.notifications.models import NotificationPreference
from apps.startups import selectors as startups

logger = structlog.get_logger(__name__)

DIGEST_DAYS = 7
DIGEST_ITEMS = 8


def followed_startup_ids(user_id: UUID) -> list[UUID]:
    """Startups the member follows, and the startups of the people they follow."""
    ids = set(follows.followed_ids(user_id, Follow.Kind.STARTUP))
    for member_id in follows.followed_ids(user_id, Follow.Kind.MEMBER):
        ids.update(startups.startup_ids_of_member(member_id))
    return list(ids)


def following_feed(viewer: Any, *, type: str, cursor: str, limit: int) -> dict[str, Any]:  # noqa: A002
    """News and wins that feature a startup the member follows, or one run by someone they do."""
    ids = followed_startup_ids(viewer.pk)
    if not ids:
        return {"results": [], "next_cursor": None}
    return editorial.feed(viewer, type=type, cursor=cursor, limit=limit, startup_ids=ids)


# --- notices when something about a followed startup is published ---


def notify_followers_of_item(item_id: UUID) -> int:
    """Tell members who follow a featured startup (or the person behind it). Returns how many."""
    item = editorial.published().filter(pk=item_id).first()
    if item is None:
        return 0
    featured = editorial.item_startup_ids(item.pk)
    if not featured:
        return 0
    recipients = set(
        Follow.objects.filter(
            followee_type=Follow.Kind.STARTUP, followee_id__in=featured
        ).values_list("follower_id", flat=True)
    )
    owners = set(
        Follow.objects.filter(
            followee_type=Follow.Kind.MEMBER, followee_id__in=_owners_of(featured)
        ).values_list("follower_id", flat=True)
    )
    sent = 0
    for user_id in recipients | owners:
        created = notify.notify(
            user_id,
            "news_featuring_followed",
            {"item_id": str(item.pk), "slug": item.slug, "title": item.title[:120]},
            dedupe_key=f"news:{item.pk.hex}:{user_id.hex}",
        )
        sent += 1 if created is not None else 0
    return sent


def _owners_of(startup_ids: list[UUID]) -> list[UUID]:
    owners = []
    for startup_id in startup_ids:
        startup = startups.get_startup(startup_id)
        if startup is not None:
            owners.append(startup.owner_id)
    return owners


# --- the weekly digest ---


def digest_recipients() -> list[UUID]:
    """Active members, less those who switched the digest email off (it is on until they do).

    Saved preferences keep only what differs from the defaults, so an opt-out is the stored row.
    """
    from apps.accounts import selectors as accounts

    opted_out = NotificationPreference.objects.filter(choices__news_digest__email=False)
    members = accounts.active_members().exclude(pk__in=opted_out.values("user_id"))
    return list(members.values_list("pk", flat=True))


def send_digest(now: Any = None) -> int:
    """Email the week's most talked about stories to members who asked for them."""
    from apps.accounts import services as accounts

    now = now or timezone.now()
    items = list(
        editorial.published()
        .filter(published_at__gte=now - timedelta(days=DIGEST_DAYS))
        .order_by("-comment_count", "-reaction_count", "-published_at")[:DIGEST_ITEMS]
    )
    if not items:
        return 0
    week = now.strftime("%G-W%V")
    lines = [f"- {item.title}: {settings.FRONTEND_BASE_URL}/news/{item.slug}" for item in items]
    body = (
        "The most talked about stories on WO Community this week:\n\n"
        + "\n".join(lines)
        + f"\n\nOpen the community: {settings.FRONTEND_BASE_URL}/news"
    )
    sent = 0
    for user_id in digest_recipients():
        if not accounts.is_active(user_id):
            continue
        if ratelimit.hit(f"news-digest:{user_id}:{week}", 9 * 86400) > 1:
            continue  # this week's digest already went out
        contact = accounts.get_contact(user_id)
        if contact is None:
            continue
        emails.send_notice(contact.email, "This week on WO Community", body, category="news_digest")
        sent += 1
    return sent
