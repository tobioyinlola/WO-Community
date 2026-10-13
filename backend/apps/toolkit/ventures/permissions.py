"""Who may use the toolkit, in the framework's policy terms, and how a venture is looked up."""

from typing import Any, cast
from uuid import UUID

from django.conf import settings
from rest_framework import exceptions
from rest_framework.request import Request

from apps.core.policies import Policy
from apps.core.rbac import permissions_for
from apps.toolkit.ventures import selectors
from apps.toolkit.ventures.models import Venture


def member_policy(feature: str | None = None) -> Policy:
    """An active, approved member, with the named tool switched on.

    A tool that is switched off answers 404, as though it did not exist.
    """

    def check(user: Any, claims: Any) -> bool:
        if user is None or not getattr(user, "is_authenticated", False):
            return False
        if getattr(user, "status", None) != "active":
            return False
        if "toolkit.use" not in permissions_for(user.role_names()):
            return False
        if feature is not None and not settings.TOOLKIT_FEATURES.get(feature, False):
            raise exceptions.NotFound()
        return True

    return Policy(f"toolkit_member:{feature or 'any'}", check)


def uid(request: Request) -> UUID:
    return cast(UUID, request.user.pk)


def owned_venture(request: Request, venture_id: UUID) -> Venture:
    """The caller's own venture, or 404. Writes always go through this."""
    venture = selectors.owned(uid(request), venture_id)
    if venture is None:
        raise exceptions.NotFound()
    return venture


def readable_venture(request: Request, venture_id: UUID) -> Venture:
    """The caller's venture, or one shared with them for reading, or 404."""
    venture = selectors.readable(uid(request), venture_id)
    if venture is None:
        raise exceptions.NotFound()
    return venture
