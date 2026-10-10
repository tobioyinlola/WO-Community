"""The one way any module tells a member something.

``notify(user_id, type, payload)`` checks the member's preferences for each channel, writes the
in-app notification and, if wanted, sends the email. Delivery is idempotent when a ``dedupe_key``
is given, so a retried event never notifies twice. Wording lives here, not in the data: the
payload carries ids, and titles are produced when a notification is read or emailed.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import structlog
from django.conf import settings
from django.db import IntegrityError, transaction

from apps.accounts import services as accounts
from apps.core import ratelimit
from apps.notifications import emails, preferences
from apps.notifications.models import Notification
from apps.profiles import selectors as profiles

logger = structlog.get_logger(__name__)

EMAIL_BURST_LIMIT = 10  # emails of one kind to one member per hour; the rest stay in-app only
EMAIL_BURST_WINDOW = 3600


@dataclass(frozen=True)
class Spec:
    preference: str  # the preference type that switches it on and off
    title: Callable[[str, dict[str, Any]], str]  # (actor name, payload) -> sentence
    link: Callable[[dict[str, Any]], str]  # frontend path
    email: bool = False
    rate_limited_email: bool = False  # members can trigger these for each other


def _outcome_title(payload: dict[str, Any]) -> str:
    what = payload.get("target_type", "content")
    if payload.get("outcome") == "actioned":
        return f"A moderator removed or hid the {what} you reported"
    if payload.get("outcome") == "reviewed":
        return f"A moderator reviewed your report and took no action on the {what}"
    return "A moderator handled your report"


def _post_link(payload: dict[str, Any]) -> str:
    return f"/posts/{payload['post_id']}"


TYPES: dict[str, Spec] = {
    "comment": Spec(
        "comments",
        lambda who, p: f"{who} commented on your post",
        _post_link,
        email=True,
        rate_limited_email=True,
    ),
    "reply": Spec(
        "comments",
        lambda who, p: f"{who} replied to your comment",
        _post_link,
        email=True,
        rate_limited_email=True,
    ),
    "mention": Spec(
        "mentions",
        lambda who, p: f"{who} mentioned you in a {p.get('target_type', 'post')}",
        _post_link,
        email=True,
        rate_limited_email=True,
    ),
    "member_approved": Spec(
        "approvals", lambda who, p: "Your registration was approved. Welcome!", lambda p: "/home"
    ),
    "report_outcome": Spec("moderation", lambda who, p: _outcome_title(p), lambda p: "/home"),
}


def actor_names(viewer_id: UUID, actor_ids: list[UUID]) -> dict[UUID, str]:
    """Names as the recipient may see them: someone hidden from them is "Community member"."""
    if not actor_ids:
        return {}

    class _Viewer:
        pk = viewer_id
        is_authenticated = True
        status = "active"

    cards = profiles.cards_for(_Viewer(), actor_ids)
    return {uid: card["name"] for uid, card in cards.items()}


def _actor_id(payload: dict[str, Any]) -> UUID | None:
    raw = payload.get("actor_id")
    return UUID(raw) if raw else None


def notify(
    user_id: UUID, type_: str, payload: dict[str, Any], *, dedupe_key: str = ""
) -> Notification | None:
    """Notify one member. Returns the in-app notification, or None if none was created.

    Nothing is sent to the person who caused it, to anyone who is not an active member, or
    again for a ``dedupe_key`` that was already used.
    """
    spec = TYPES[type_]
    actor_id = _actor_id(payload)
    if actor_id == user_id or not accounts.is_active(user_id):
        return None
    if dedupe_key and Notification.objects.filter(user_id=user_id, dedupe_key=dedupe_key).exists():
        return None

    created: Notification | None = None
    if preferences.allows(user_id, spec.preference, "in_app"):
        try:
            with transaction.atomic():
                created = Notification.objects.create(
                    user_id=user_id,
                    type=type_,
                    payload=payload,
                    dedupe_key=dedupe_key,
                    channels_sent=["in_app"],
                )
        except IntegrityError:  # a concurrent delivery of the same event won
            return None
    if spec.email and preferences.allows(user_id, spec.preference, "email"):
        _email(user_id, type_, spec, payload, created)
    return created


def _email(
    user_id: UUID,
    type_: str,
    spec: Spec,
    payload: dict[str, Any],
    notification: Notification | None,
) -> None:
    if spec.rate_limited_email:
        key = f"notify-email:{user_id}:{spec.preference}"
        if ratelimit.hit(key, EMAIL_BURST_WINDOW) > EMAIL_BURST_LIMIT:
            logger.info("notification_email_throttled", type=type_)
            return
    contact = accounts.get_contact(user_id)
    if contact is None:
        return
    actor_id = _actor_id(payload)
    who = actor_names(user_id, [actor_id]).get(actor_id, "Someone") if actor_id else "Someone"
    title = spec.title(who, payload)
    emails.send_notice(
        contact.email,
        title,
        f"{title}.\n\n{settings.FRONTEND_BASE_URL}{spec.link(payload)}",
        category=f"notification_{type_}",
    )
    if notification is not None:
        notification.channels_sent = [*notification.channels_sent, "email"]
        notification.save(update_fields=["channels_sent", "updated_at"])


def render(user_id: UUID, rows: list[Notification]) -> list[dict[str, Any]]:
    """Notifications ready to show: wording and link produced from the type and payload."""
    actor_ids = [a for a in (_actor_id(n.payload) for n in rows) if a]
    names = actor_names(user_id, list(dict.fromkeys(actor_ids)))
    items = []
    for row in rows:
        spec = TYPES.get(row.type)
        if spec is None:  # a type retired since this was written
            continue
        actor_id = _actor_id(row.payload)
        who = names.get(actor_id, "Someone") if actor_id else "Someone"
        items.append(
            {
                "id": row.pk,
                "type": row.type,
                "title": spec.title(who, row.payload),
                "link": spec.link(row.payload),
                "meta": row.payload,
                "read": row.read_at is not None,
                "created_at": row.created_at,
            }
        )
    return items
