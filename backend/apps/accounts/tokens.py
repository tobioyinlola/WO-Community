"""Short lived access tokens signed with an asymmetric key.

Verification needs only the public key. Revocation before expiry works through
a per user minimum token version held in the cache.
"""

import uuid
from typing import Any

import jwt
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from apps.accounts.models import User


class InvalidToken(Exception):
    pass


def _min_version_key(user_id: str) -> str:
    return f"jwt:min_version:{user_id}"


def issue_access_token(
    user: User, *, mfa_at: float | None = None, session_id: object | None = None
) -> str:
    now = timezone.now()
    claims = {
        "iss": settings.JWT_ISSUER,
        "sub": str(user.pk),
        "iat": now,
        "exp": now + settings.JWT_ACCESS_LIFETIME,
        "jti": uuid.uuid4().hex,
        "roles": sorted(user.role_names()),
        "tv": user.token_version,
    }
    if mfa_at is not None:
        claims["mfa_at"] = int(mfa_at)
    if session_id is not None:
        claims["sid"] = str(session_id)
    return jwt.encode(claims, settings.JWT_PRIVATE_KEY, algorithm=settings.JWT_ALGORITHM)


def verify_access_token(token: str) -> dict[str, Any]:
    try:
        claims: dict[str, Any] = jwt.decode(
            token,
            settings.JWT_PUBLIC_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            issuer=settings.JWT_ISSUER,
            options={"require": ["exp", "iat", "sub", "tv", "iss"]},
        )
    except jwt.PyJWTError as exc:
        raise InvalidToken(str(exc)) from exc
    minimum = cache.get(_min_version_key(claims["sub"]))
    if minimum is not None and claims["tv"] < minimum:
        raise InvalidToken("token revoked")
    return claims


def revoke_older_tokens(user: User) -> None:
    """Reject access tokens issued before the user's current token version."""
    ttl = int(settings.JWT_ACCESS_LIFETIME.total_seconds()) + 60
    cache.set(_min_version_key(str(user.pk)), user.token_version, ttl)
