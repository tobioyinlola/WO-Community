from typing import Any

from rest_framework.permissions import BasePermission
from rest_framework.request import Request

from apps.core.policies import Policy


class PolicyPermission(BasePermission):
    """Default deny. A view must set ``policy`` to be reachable at all.

    Object level rules are optional and live on ``view.object_policy``, a
    function ``(user, obj) -> bool``. Owner scoped querysets remain the first
    defence against insecure direct object references.
    """

    def has_permission(self, request: Request, view: Any) -> bool:
        policy = getattr(view, "policy", None)
        if not isinstance(policy, Policy):
            return False
        return policy(request.user)

    def has_object_permission(self, request: Request, view: Any, obj: Any) -> bool:
        object_policy = getattr(view, "object_policy", None)
        if object_policy is None:
            return True
        return bool(object_policy(request.user, obj))
