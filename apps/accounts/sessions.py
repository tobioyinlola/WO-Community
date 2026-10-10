"""Refresh token families: issue, rotate with reuse detection, revoke."""

import hashlib
import secrets
import uuid
from datetime import datetime

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import BLOCKED_STATUSES, RefreshTokenFamily, User
from apps.audit import services as audit


class InvalidRefreshToken(Exception):
    pass


def _digest(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def _sliding_expiry(absolute_expires_at: datetime) -> datetime:
    return min(timezone.now() + settings.REFRESH_SLIDING_LIFETIME, absolute_expires_at)


def _format(family_id: uuid.UUID, secret: str) -> str:
    return f"{family_id}.{secret}"


def start(
    user: User, *, user_agent: str, ip: str, mfa_verified_at: datetime | None = None
) -> tuple[str, RefreshTokenFamily]:
    """Open a new session and return the raw refresh token."""
    secret = secrets.token_urlsafe(32)
    now = timezone.now()
    absolute = now + settings.REFRESH_ABSOLUTE_LIFETIME
    family = RefreshTokenFamily.objects.create(
        user=user,
        current_hash=_digest(secret),
        user_agent=user_agent[:255],
        ip_hash=audit.hash_value(ip),
        expires_at=_sliding_expiry(absolute),
        absolute_expires_at=absolute,
        mfa_verified_at=mfa_verified_at,
    )
    return _format(family.pk, secret), family


def _parse(raw: str) -> tuple[uuid.UUID, str]:
    family_part, separator, secret = raw.partition(".")
    if not separator or not secret:
        raise InvalidRefreshToken("malformed")
    try:
        return uuid.UUID(family_part), secret
    except ValueError as exc:
        raise InvalidRefreshToken("malformed") from exc


def revoke(family: RefreshTokenFamily, reason: str) -> None:
    if family.revoked_at is None:
        family.revoked_at = timezone.now()
        family.revoked_reason = reason
        family.save(update_fields=["revoked_at", "revoked_reason", "updated_at"])


def revoke_all(user: User, reason: str) -> int:
    return RefreshTokenFamily.objects.filter(user=user, revoked_at__isnull=True).update(
        revoked_at=timezone.now(), revoked_reason=reason, updated_at=timezone.now()
    )


def rotate(raw: str, *, ip: str) -> tuple[User, str, RefreshTokenFamily]:
    """Exchange a refresh token for a new one.

    The family row is locked so concurrent refreshes cannot both succeed. A
    token that is not the current one revokes the family: either the client
    replayed an old token or someone else holds a copy.
    """
    family_id, secret = _parse(raw)
    failure: str | None = None
    result: tuple[User, str, RefreshTokenFamily] | None = None
    # The revocations below must commit even though the call then fails, so
    # the error is raised only after the transaction block has closed.
    with transaction.atomic():
        family = (
            RefreshTokenFamily.objects.select_for_update()
            .select_related("user")
            .filter(pk=family_id)
            .first()
        )
        now = timezone.now()
        if family is None or family.revoked_at is not None:
            failure = "unknown or revoked"
        elif family.expires_at <= now or family.absolute_expires_at <= now:
            revoke(family, "expired")
            failure = "expired"
        elif not secrets.compare_digest(family.current_hash, _digest(secret)):
            revoke(family, "reuse_detected")
            audit.record(
                actor=family.user,
                action="auth.refresh_reuse_detected",
                target_type="session",
                target_id=family.pk,
                ip=ip,
            )
            failure = "reuse"
        elif family.user.status in BLOCKED_STATUSES:
            revoke(family, "account_unavailable")
            failure = "account unavailable"
        else:
            new_secret = secrets.token_urlsafe(32)
            family.current_hash = _digest(new_secret)
            family.last_used_at = now
            family.expires_at = _sliding_expiry(family.absolute_expires_at)
            family.save(update_fields=["current_hash", "last_used_at", "expires_at", "updated_at"])
            result = (family.user, _format(family.pk, new_secret), family)
    if result is None:
        raise InvalidRefreshToken(failure or "invalid")
    return result


def family_for_token(raw: str) -> RefreshTokenFamily | None:
    """The family a token claims to belong to, without validating the secret."""
    try:
        family_id, _ = _parse(raw)
    except InvalidRefreshToken:
        return None
    return RefreshTokenFamily.objects.filter(pk=family_id).first()


def mark_mfa_verified(session_id: uuid.UUID, user: User) -> RefreshTokenFamily | None:
    """Record a fresh MFA check on one of the user's live sessions."""
    family = (
        RefreshTokenFamily.objects.select_for_update()
        .filter(pk=session_id, user=user, revoked_at__isnull=True)
        .first()
    )
    if family is None:
        return None
    family.mfa_verified_at = timezone.now()
    family.save(update_fields=["mfa_verified_at", "updated_at"])
    return family
