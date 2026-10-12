"""How people heard of the community, and who brought them.

Every member has a short code that identifies them to people who join through them. At sign up the
person may say how they heard of us; if it was a member, that member is recorded as their referrer.
Nothing here makes a referral count for anything before the person is approved.
"""

import secrets
from typing import Any
from uuid import UUID

from django.db import IntegrityError, transaction
from rest_framework import exceptions

from apps.accounts.models import User
from apps.analytics import services as analytics
from apps.core.text import plain

SOURCE_LABELS = {
    "member": "A WO Community member",
    "social": "Social media",
    "event": "An event or demo day",
    "partner": "A partner organisation",
    "search": "Search engine",
    "newsletter": "Newsletter",
    "other": "Other",
}
SOURCES = tuple(SOURCE_LABELS)
# Sources where a few words of detail make sense (which platform, which event, whose name).
DETAIL_SOURCES = ("member", "social", "event", "partner", "other")
DETAIL_MAX = 200

# No 0, 1, I or O, so a code read aloud or from a screen is not mistyped.
ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
CODE_LENGTH = 8


def new_code() -> str:
    """A code nobody else holds. Eight of 32 symbols is about a trillion, so a clash is a rarity."""
    while True:
        code = "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))
        if not User.objects.filter(referral_code=code).exists():
            return code


def ensure_code(user: User) -> str:
    """Give an account its code if it has none yet (accounts made before codes existed)."""
    if user.referral_code:
        return user.referral_code
    for _ in range(5):
        try:
            with transaction.atomic():
                user.referral_code = new_code()
                user.save(update_fields=["referral_code", "updated_at"])
            return user.referral_code
        except IntegrityError:  # a concurrent request took the same code; try another
            continue
    raise RuntimeError("could not allocate a referral code")


def referrer_for_code(code: str) -> User | None:
    """The active member a code belongs to, or None. Case does not matter."""
    cleaned = (code or "").strip().upper()
    if not cleaned:
        return None
    return User.objects.filter(referral_code=cleaned, status="active").first()


def _field(message: str, field: str = "referral") -> exceptions.ValidationError:
    return exceptions.ValidationError({field: [message]})


def clean(data: dict[str, Any] | None, *, own_id: UUID | None = None) -> dict[str, Any]:
    """The referral fields for an account, validated. Blank means they did not say."""
    data = data or {}
    source = data.get("kind") or ""
    if source and source not in SOURCES:
        raise _field("Choose one of the listed ways you heard of us.", "kind")
    code = (data.get("code") or "").strip().upper()
    code_owner = referrer_for_code(code) if code else None
    referrer: User | None = None
    referred_by = data.get("referred_by")
    if source == "member":
        if referred_by:
            referrer = User.objects.filter(pk=referred_by, status="active").first()
            if referrer is None:
                raise _field("We could not find that member.", "referred_by")
        elif code_owner is not None:
            referrer = code_owner
    elif referred_by:
        raise _field("Choose “A WO Community member” to name a member.", "referred_by")
    if referrer is not None and own_id is not None and referrer.pk == own_id:
        raise _field("You cannot refer yourself.", "referred_by")
    detail = plain(data.get("detail") or "")[:DETAIL_MAX] if source in DETAIL_SOURCES else ""
    return {
        "referral_source": source,
        "referral_detail": detail,
        "referred_by": referrer,
        "referral_code_used": code if code_owner is not None else "",
    }


def capture(user: User, data: dict[str, Any] | None) -> None:
    """Record what a new person said about how they heard of us. A bad entry never blocks sign up.

    The form validates what it can; anything that still does not hold (a member removed in the
    meantime) is dropped rather than refusing a registration over a courtesy question.
    """
    if not data:
        return
    try:
        fields = clean(data, own_id=user.pk)
    except exceptions.ValidationError:
        fields = clean({"kind": data.get("kind"), "detail": data.get("detail")}, own_id=user.pk)
    for name, value in fields.items():
        setattr(user, name, value)
    user.save(update_fields=[*fields, "updated_at"])
    if fields["referral_source"]:
        analytics.track(
            "referral_captured",
            actor_id=user.pk,
            properties={"kind": fields["referral_source"]},
        )
