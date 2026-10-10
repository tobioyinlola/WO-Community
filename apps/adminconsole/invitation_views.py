from uuid import UUID

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import exceptions, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.accounts import selectors, services
from apps.adminconsole.serializers import (
    BulkInvitationSerializer,
    BulkReportSerializer,
    InvitationCreateSerializer,
    InvitationQuerySerializer,
    InvitationSerializer,
)
from apps.adminconsole.views import ERRORS as BASE_ERRORS
from apps.adminconsole.views import _actor, _ip
from apps.core import policies
from apps.core.pagination import AdminLimitOffsetPagination

ERRORS = {
    **BASE_ERRORS,
    404: OpenApiResponse(description="Invitation not found"),
    409: OpenApiResponse(
        description="Already registered, already invited, or not in a state that allows this"
    ),
}

MANAGE = policies.admin_permission("invitations.manage")


class InvitationListCreateView(APIView):
    policy = MANAGE

    @extend_schema(
        summary="List invitations",
        parameters=[InvitationQuerySerializer],
        responses={200: InvitationSerializer(many=True), **ERRORS},
        tags=["admin"],
    )
    def get(self, request: Request) -> Response:
        serializer = InvitationQuerySerializer(data=request.query_params.dict())
        serializer.is_valid(raise_exception=True)
        filters = dict(serializer.validated_data)
        filters.pop("limit", None)
        filters.pop("offset", None)
        paginator = AdminLimitOffsetPagination()
        page = paginator.paginate_queryset(
            selectors.list_invitations(**filters), request, view=self
        )
        return paginator.get_paginated_response(InvitationSerializer(page, many=True).data)

    @extend_schema(
        summary="Invite one person by email",
        description="Registering through the emailed link approves the member automatically.",
        request=InvitationCreateSerializer,
        responses={201: InvitationSerializer, **ERRORS},
        tags=["admin"],
    )
    def post(self, request: Request) -> Response:
        serializer = InvitationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invitation = services.create_invitation(
            actor=_actor(request), ip=_ip(request), **serializer.validated_data
        )
        return Response(InvitationSerializer(invitation).data, status=status.HTTP_201_CREATED)


class InvitationBulkView(APIView):
    policy = MANAGE
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "admin_bulk"

    @extend_schema(
        summary="Invite many people from CSV text",
        description="Send the file's contents as `csv`. The first row must name the columns: "
        "`email` (required), `role` and `message` (optional). Up to 500 rows. Rows that fail "
        "are reported and skipped; the rest are invited.",
        request=BulkInvitationSerializer,
        responses={200: BulkReportSerializer, **ERRORS},
        tags=["admin"],
    )
    def post(self, request: Request) -> Response:
        serializer = BulkInvitationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        report = services.bulk_create(
            actor=_actor(request), csv_text=serializer.validated_data["csv"], ip=_ip(request)
        )
        return Response(BulkReportSerializer(report).data)


class InvitationResendView(APIView):
    policy = MANAGE

    @extend_schema(
        summary="Resend an invitation",
        description="Issues a new link and expiry; the previous link stops working.",
        request=None,
        responses={200: InvitationSerializer, **ERRORS},
        tags=["admin"],
    )
    def post(self, request: Request, invitation_id: UUID) -> Response:
        invitation = services.resend_invitation(
            actor=_actor(request), invitation_id=invitation_id, ip=_ip(request)
        )
        return Response(InvitationSerializer(invitation).data)


class InvitationRevokeView(APIView):
    policy = MANAGE

    @extend_schema(
        summary="Revoke an invitation",
        request=None,
        responses={200: InvitationSerializer, **ERRORS},
        tags=["admin"],
    )
    def post(self, request: Request, invitation_id: UUID) -> Response:
        invitation = services.revoke_invitation(
            actor=_actor(request), invitation_id=invitation_id, ip=_ip(request)
        )
        return Response(InvitationSerializer(invitation).data)


class InvitationDetailView(APIView):
    policy = MANAGE

    @extend_schema(
        summary="One invitation", responses={200: InvitationSerializer, **ERRORS}, tags=["admin"]
    )
    def get(self, request: Request, invitation_id: UUID) -> Response:
        invitation = selectors.get_invitation(invitation_id)
        if invitation is None:
            raise exceptions.NotFound()
        return Response(InvitationSerializer(invitation).data)
