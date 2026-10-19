from typing import cast
from uuid import UUID

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import BaseThrottle, ScopedRateThrottle, UserRateThrottle
from rest_framework.views import APIView

from apps.core import policies
from apps.groups import selectors, services
from apps.groups.serializers import (
    ChatGroupSerializer,
    GroupMembershipSerializer,
    GroupMessageCreateSerializer,
    GroupMessagePageSerializer,
    GroupMessageQuerySerializer,
    GroupMessageSerializer,
    GroupReactionResultSerializer,
    GroupReactionSerializer,
)

ERRORS = {
    401: OpenApiResponse(description="Not authenticated"),
    403: OpenApiResponse(description="Not an active member, or not in this group"),
    404: OpenApiResponse(description="No such group or message"),
}


def _uid(request: Request) -> UUID:
    return cast(UUID, request.user.pk)


def _private(response: Response) -> Response:
    response["Cache-Control"] = "private, no-store"
    return response


class GroupsView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="Group chats",
        description="The open groups, whether you are in each, and how many messages you have "
        "not read.",
        responses={200: ChatGroupSerializer(many=True), **ERRORS},
        tags=["groups"],
    )
    def get(self, request: Request) -> Response:
        return _private(
            Response(ChatGroupSerializer(selectors.groups_for(request.user), many=True).data)
        )


class GroupView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="One group chat", responses={200: ChatGroupSerializer, **ERRORS}, tags=["groups"]
    )
    def get(self, request: Request, group_id: UUID) -> Response:
        return _private(
            Response(ChatGroupSerializer(selectors.group_for(request.user, group_id)).data)
        )


class MembershipView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="Join a group",
        request=None,
        responses={200: GroupMembershipSerializer, **ERRORS},
        tags=["groups"],
    )
    def post(self, request: Request, group_id: UUID) -> Response:
        services.join(user_id=_uid(request), group_id=group_id)
        return Response({"joined": True})

    @extend_schema(
        summary="Leave a group",
        responses={200: GroupMembershipSerializer, **ERRORS},
        tags=["groups"],
    )
    def delete(self, request: Request, group_id: UUID) -> Response:
        services.leave(user_id=_uid(request), group_id=group_id)
        return Response({"joined": False})


class MessagesView(APIView):
    policy = policies.active_member
    throttle_classes = [UserRateThrottle, ScopedRateThrottle]

    def get_throttles(self) -> list[BaseThrottle]:
        self.throttle_scope = "groups_post" if self.request.method == "POST" else "groups_read"
        return super().get_throttles()

    @extend_schema(
        summary="Messages in a group",
        description="The latest messages, oldest first. Pass `older` from a page as `cursor` for "
        "the messages before it. Reading marks the group as read.",
        parameters=[GroupMessageQuerySerializer],
        responses={200: GroupMessagePageSerializer, **ERRORS},
        tags=["groups"],
    )
    def get(self, request: Request, group_id: UUID) -> Response:
        params = GroupMessageQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        page = selectors.messages(request.user, group_id, **params.validated_data)
        if not params.validated_data["cursor"]:
            services.mark_read(user_id=_uid(request), group_id=group_id)
        return _private(Response(GroupMessagePageSerializer(page).data))

    @extend_schema(
        summary="Send a message",
        description="Plain text with emoji, up to 2000 characters. `reply_to` quotes an earlier "
        "message in the same group.",
        request=GroupMessageCreateSerializer,
        responses={
            201: GroupMessageSerializer,
            **ERRORS,
            429: OpenApiResponse(description="Sending too fast"),
        },
        tags=["groups"],
    )
    def post(self, request: Request, group_id: UUID) -> Response:
        serializer = GroupMessageCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        message = services.send(
            user_id=_uid(request),
            group_id=group_id,
            body=serializer.validated_data["body"],
            reply_to=serializer.validated_data["reply_to"],
        )
        view = selectors.message_for(request.user, message.pk)
        return Response(GroupMessageSerializer(view).data, status=status.HTTP_201_CREATED)


class MessageView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="Delete your message",
        responses={204: None, **ERRORS},
        tags=["groups"],
    )
    def delete(self, request: Request, message_id: UUID) -> Response:
        services.delete_own(user_id=_uid(request), message_id=message_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ReactionView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="React to a message with an emoji",
        description="Toggles: the same emoji again takes your reaction back.",
        request=GroupReactionSerializer,
        responses={200: GroupReactionResultSerializer, **ERRORS},
        tags=["groups"],
    )
    def post(self, request: Request, message_id: UUID) -> Response:
        serializer = GroupReactionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        on = services.toggle_reaction(
            user_id=_uid(request), message_id=message_id, emoji=serializer.validated_data["emoji"]
        )
        reactions = selectors.reactions_for(request.user, message_id)
        return Response(GroupReactionResultSerializer({"on": on, "reactions": reactions}).data)
