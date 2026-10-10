from typing import Any
from uuid import UUID

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.adminconsole.views import _actor, _ip
from apps.core import policies
from apps.feed import services
from apps.feed.serializers import ModerationSerializer

MODERATE = policies.admin_permission("feed.moderate")

ERRORS = {
    401: OpenApiResponse(description="Not authenticated"),
    403: OpenApiResponse(description="Not allowed, or MFA missing"),
    404: OpenApiResponse(description="No such post"),
}


class ModerationResultSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    action = serializers.CharField()


class ModeratePostView(APIView):
    """Pin, feature, hide or remove a post. The URL names the action."""

    policy = MODERATE
    action = ""

    @extend_schema(
        summary="Moderate a post",
        description="Actions: pin, unpin, feature, unfeature, hide, unhide, remove. Hidden posts "
        "disappear from the feed but the author still sees them; removed posts are gone. "
        "Every action is written to the audit log.",
        request=ModerationSerializer,
        responses={200: ModerationResultSerializer, **ERRORS},
        tags=["admin"],
    )
    def post(self, request: Request, post_id: UUID) -> Response:
        serializer = ModerationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        post: Any = services.moderate_post(
            actor=_actor(request),
            post_id=post_id,
            action=self.action,
            reason=serializer.validated_data["reason"],
            ip=_ip(request),
        )
        return Response({"id": post.pk, "action": self.action})


def action_view(name: str) -> type[ModeratePostView]:
    return type(f"{name.title()}PostView", (ModeratePostView,), {"action": name})
