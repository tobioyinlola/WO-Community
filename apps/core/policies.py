"""Policy framework.

A policy is a plain, unit testable function of the acting user. Views declare
exactly one on ``view.policy``. A view without a policy is denied (see
``PolicyPermission``), so forgetting authorisation fails closed.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from apps.core.rbac import permissions_for

UserLike = Any


@dataclass(frozen=True)
class Policy:
    name: str
    check: Callable[[UserLike], bool]

    def __call__(self, user: UserLike) -> bool:
        return bool(self.check(user))


def _is_authenticated(user: UserLike) -> bool:
    return bool(user is not None and getattr(user, "is_authenticated", False))


def _is_active_member(user: UserLike) -> bool:
    return _is_authenticated(user) and getattr(user, "status", None) == "active"


public = Policy("public", lambda user: True)
authenticated = Policy("authenticated", _is_authenticated)
active_member = Policy("active_member", _is_active_member)


def has_permission(code: str) -> Policy:
    """Active user whose roles carry the named permission code."""

    def check(user: UserLike) -> bool:
        if not _is_active_member(user):
            return False
        return code in permissions_for(user.role_names())

    return Policy(f"has_permission:{code}", check)


def owns(owner_of: Callable[[Any], Any]) -> Callable[[UserLike, Any], bool]:
    """Object policy factory: the acting user must be the object's owner."""

    def check(user: UserLike, obj: Any) -> bool:
        return _is_authenticated(user) and owner_of(obj) == user.pk

    return check
