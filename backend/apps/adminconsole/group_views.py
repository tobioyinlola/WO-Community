from typing import Any
from uuid import UUID

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.adminconsole.views import _actor, _ip
from apps.core import policies
from apps.groups import selectors, services
from apps.groups.serializers import (
    AdminChatGroupSerializer,
    AdminGroupWriteSerializer,
    GroupMessagePageSerializer,
    GroupMessageQuerySerializer,
)

MODERATE = policies.admin_permission("feed.moderate")

ERRORS = {
    401: OpenApiResponse(description="Not authenticated"),
    403: OpenApiResponse(description="Not allowed, or MFA missing"),
    404: OpenApiResponse(description="No such group or message"),
}


def _one(group_id: UUID) -> dict[str, Any]:
    return next(g for g in selectors.admin_groups() if g["id"] == group_id)


class AdminGroupsView(APIView):
    policy = MODERATE

    @extend_schema(
        summary="Group chats",
        description="Every group, archived ones last, with members and messages.",
        responses={200: AdminChatGroupSerializer(many=True), **ERRORS},
        tags=["admin"],
    )
    def get(self, request: Request) -> Response:
        return Response(AdminChatGroupSerializer(selectors.admin_groups(), many=True).data)

    @extend_schema(
        summary="Create a group chat",
        request=AdminGroupWriteSerializer,
        responses={201: AdminChatGroupSerializer, **ERRORS},
        tags=["admin"],
    )
    def post(self, request: Request) -> Response:
        serializer = AdminGroupWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        group = services.create_group(
            actor=_actor(request), data=serializer.validated_data, ip=_ip(request)
        )
        return Response(
            AdminChatGroupSerializer(_one(group.pk)).data, status=status.HTTP_201_CREATED
        )


class AdminGroupView(APIView):
    policy = MODERATE

    @extend_schema(
        summary="Change a group chat",
        description="Rename it, change its description, emoji or place in the list, or archive "
        "it (`archived: true`). An archived group disappears for members; its messages are kept.",
        request=AdminGroupWriteSerializer,
        responses={200: AdminChatGroupSerializer, **ERRORS},
        tags=["admin"],
    )
    def patch(self, request: Request, group_id: UUID) -> Response:
        serializer = AdminGroupWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.update_group(
            actor=_actor(request),
            group_id=group_id,
            data=serializer.validated_data,
            ip=_ip(request),
        )
        return Response(AdminChatGroupSerializer(_one(group_id)).data)


class AdminGroupMessagesView(APIView):
    policy = MODERATE

    @extend_schema(
        summary="Messages in a group chat, for moderation",
        parameters=[GroupMessageQuerySerializer],
        responses={200: GroupMessagePageSerializer, **ERRORS},
        tags=["admin"],
    )
    def get(self, request: Request, group_id: UUID) -> Response:
        params = GroupMessageQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        page = selectors.messages(request.user, group_id, moderator=True, **params.validated_data)
        response = Response(GroupMessagePageSerializer(page).data)
        response["Cache-Control"] = "private, no-store"
        return response


class AdminGroupMessageView(APIView):
    policy = MODERATE

    @extend_schema(
        summary="Remove a message from a group chat",
        description="Members see that a message was removed. Written to the audit log.",
        responses={204: None, **ERRORS},
        tags=["admin"],
    )
    def delete(self, request: Request, message_id: UUID) -> Response:
        services.remove_message(actor=_actor(request), message_id=message_id, ip=_ip(request))
        return Response(status=status.HTTP_204_NO_CONTENT)
