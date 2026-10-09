"""Policy framework.

A policy is a plain, unit testable function of the acting user and the claims
of the access token they presented. Views declare exactly one on
``view.policy``. A view without a policy is denied (see ``PolicyPermission``),
so forgetting authorisation fails closed.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from django.conf import settings

from apps.core.rbac import ADMIN_ROLES, permissions_for

UserLike = Any
Claims = dict[str, Any] | None


@dataclass(frozen=True)
class Policy:
    name: str
    check: Callable[[UserLike, Claims], bool]

    def __call__(self, user: UserLike, claims: Claims = None) -> bool:
        return bool(self.check(user, claims))


def _is_authenticated(user: UserLike) -> bool:
    return bool(user is not None and getattr(user, "is_authenticated", False))


def _is_active_member(user: UserLike) -> bool:
    return _is_authenticated(user) and getattr(user, "status", None) == "active"


public = Policy("public", lambda user, claims: True)
authenticated = Policy("authenticated", lambda user, claims: _is_authenticated(user))
active_member = Policy("active_member", lambda user, claims: _is_active_member(user))


def has_permission(code: str) -> Policy:
    """Active user whose roles carry the named permission code."""

    def check(user: UserLike, claims: Claims) -> bool:
        if not _is_active_member(user):
            return False
        return code in permissions_for(user.role_names())

    return Policy(f"has_permission:{code}", check)


def _mfa_age(claims: Claims) -> float | None:
    stamp = (claims or {}).get("mfa_at")
    return time.time() - float(stamp) if isinstance(stamp, int | float) else None


def admin_permission(code: str, *, step_up: bool = False) -> Policy:
    """Admin action: the permission, a session that passed MFA, and for
    destructive actions an MFA check that is recent.

    The MFA errors are raised only once the permission is held, so callers
    without it learn nothing about how admin access works.
    """

    def check(user: UserLike, claims: Claims) -> bool:
        # Imported here: errors pulls in DRF settings, which import this module.
        from apps.core.errors import MfaRequired, StepUpRequired

        if not has_permission(code)(user, claims):
            return False
        if not set(user.role_names()) & {role.value for role in ADMIN_ROLES}:
            return False
        age = _mfa_age(claims)
        if age is None:
            raise MfaRequired()
        if step_up and age > settings.STEP_UP_MAX_AGE_SECONDS:
            raise StepUpRequired()
        return True

    return Policy(f"admin_permission:{code}{':step_up' if step_up else ''}", check)


def owns(owner_of: Callable[[Any], Any]) -> Callable[[UserLike, Any], bool]:
    """Object policy factory: the acting user must be the object's owner."""

    def check(user: UserLike, obj: Any) -> bool:
        return _is_authenticated(user) and owner_of(obj) == user.pk

    return check
