from typing import Any
from uuid import UUID

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import exceptions
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import BaseThrottle
from rest_framework.views import APIView

from apps.accounts import selectors, services
from apps.adminconsole.serializers import (
    MemberQuerySerializer,
    MemberSerializer,
    QueueCountsSerializer,
    ReasonSerializer,
)
from apps.core import policies
from apps.core.pagination import AdminLimitOffsetPagination
from apps.feed import moderation
from apps.jobs import selectors as jobs

ERRORS = {
    401: OpenApiResponse(description="Not authenticated"),
    403: OpenApiResponse(description="Not allowed, MFA missing, or step-up required"),
    404: OpenApiResponse(description="Member not found"),
    409: OpenApiResponse(description="The account is not in a state that allows this"),
}


def _actor(request: Request) -> Any:
    return request.user


def _ip(request: Request) -> str:
    return BaseThrottle().get_ident(request) or ""


class MemberListView(APIView):
    policy = policies.admin_permission("members.view")

    @extend_schema(
        summary="Search and filter members",
        parameters=[MemberQuerySerializer],
        responses={200: MemberSerializer(many=True), **ERRORS},
        tags=["admin"],
    )
    def get(self, request: Request) -> Response:
        serializer = MemberQuerySerializer(data=request.query_params.dict())
        serializer.is_valid(raise_exception=True)
        filters = dict(serializer.validated_data)
        filters.pop("limit", None)
        filters.pop("offset", None)
        queryset = selectors.list_members(**filters)
        paginator = AdminLimitOffsetPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(MemberSerializer(page, many=True).data)


class MemberDetailView(APIView):
    policy = policies.admin_permission("members.view")

    @extend_schema(
        summary="One member", responses={200: MemberSerializer, **ERRORS}, tags=["admin"]
    )
    def get(self, request: Request, user_id: UUID) -> Response:
        member = selectors.get_member(user_id)
        if member is None:
            raise exceptions.NotFound()
        return Response(MemberSerializer(member).data)


class ApproveView(APIView):
    policy = policies.admin_permission("members.approve")

    @extend_schema(
        summary="Approve a pending registration",
        request=None,
        responses={200: MemberSerializer, **ERRORS},
        tags=["admin"],
    )
    def post(self, request: Request, user_id: UUID) -> Response:
        member = services.approve_member(actor=_actor(request), user_id=user_id, ip=_ip(request))
        return Response(MemberSerializer(member).data)


class ReinstateView(APIView):
    policy = policies.admin_permission("members.suspend", step_up=True)

    @extend_schema(
        summary="Reinstate a suspended member",
        request=None,
        responses={200: MemberSerializer, **ERRORS},
        tags=["admin"],
    )
    def post(self, request: Request, user_id: UUID) -> Response:
        member = services.reinstate_member(actor=_actor(request), user_id=user_id, ip=_ip(request))
        return Response(MemberSerializer(member).data)


def _reason(request: Request) -> str:
    serializer = ReasonSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    return str(serializer.validated_data["reason"])


class RejectView(APIView):
    policy = policies.admin_permission("members.approve")

    @extend_schema(
        summary="Reject a pending registration",
        description="The reason is emailed to the applicant.",
        request=ReasonSerializer,
        responses={200: MemberSerializer, **ERRORS},
        tags=["admin"],
    )
    def post(self, request: Request, user_id: UUID) -> Response:
        member = services.reject_registration(
            actor=_actor(request), user_id=user_id, reason=_reason(request), ip=_ip(request)
        )
        return Response(MemberSerializer(member).data)


class SuspendView(APIView):
    policy = policies.admin_permission("members.suspend", step_up=True)

    @extend_schema(
        summary="Suspend a member",
        description="Ends all their sessions immediately.",
        request=ReasonSerializer,
        responses={200: MemberSerializer, **ERRORS},
        tags=["admin"],
    )
    def post(self, request: Request, user_id: UUID) -> Response:
        member = services.suspend_member(
            actor=_actor(request), user_id=user_id, reason=_reason(request), ip=_ip(request)
        )
        return Response(MemberSerializer(member).data)


class RemoveView(APIView):
    policy = policies.admin_permission("members.remove", step_up=True)

    @extend_schema(
        summary="Remove a member",
        description="Ends all their sessions and takes their public pages down.",
        request=ReasonSerializer,
        responses={200: MemberSerializer, **ERRORS},
        tags=["admin"],
    )
    def post(self, request: Request, user_id: UUID) -> Response:
        member = services.remove_member(
            actor=_actor(request), user_id=user_id, reason=_reason(request), ip=_ip(request)
        )
        return Response(MemberSerializer(member).data)


class ResetMfaView(APIView):
    policy = policies.admin_permission("roles.manage", step_up=True)

    @extend_schema(
        summary="Reset an admin's MFA after they lost their authenticator",
        description="Super admin only. Ends the admin's sessions; they enrol again at next login.",
        request=None,
        responses={200: MemberSerializer, **ERRORS},
        tags=["admin"],
    )
    def post(self, request: Request, user_id: UUID) -> Response:
        member = services.reset_member_mfa(actor=_actor(request), user_id=user_id, ip=_ip(request))
        return Response(MemberSerializer(member).data)


class QueuesView(APIView):
    policy = policies.admin_permission("members.view")

    @extend_schema(
        summary="Counts of items waiting for an admin",
        responses={200: QueueCountsSerializer, **ERRORS},
        tags=["admin"],
    )
    def get(self, request: Request) -> Response:
        counts = {
            **selectors.registration_queue_counts(),
            "open_reports": moderation.open_report_count(),
            "jobs_awaiting_review": jobs.pending_count(),
        }
        return Response(QueueCountsSerializer(counts).data)
