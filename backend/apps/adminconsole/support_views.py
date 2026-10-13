from typing import cast
from uuid import UUID

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import exceptions, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import selectors as accounts
from apps.accounts.models import User
from apps.audit import services as audit
from apps.core import policies
from apps.core.pagination import AdminLimitOffsetPagination
from apps.core.rbac import permissions_for
from apps.support import selectors, services
from apps.support.models import SupportCannedReply, SupportTicket
from apps.support.serializers import (
    AdminMessageSerializer,
    AdminTicketDetailSerializer,
    AdminTicketQuerySerializer,
    AdminTicketRowSerializer,
    AdminTicketUpdateSerializer,
    AttachmentLinkSerializer,
    CannedReplyOutSerializer,
    CannedReplySerializer,
    StatsSerializer,
    SupportMessageSerializer,
    SupportPersonSerializer,
    person,
)

MANAGE = policies.admin_permission("support.manage")
ERRORS = {
    401: OpenApiResponse(description="Not authenticated"),
    403: OpenApiResponse(description="Not allowed, or MFA missing"),
    404: OpenApiResponse(description="Not found"),
}


def _admin(request: Request) -> User:
    return cast(User, request.user)


def _ticket(ticket_id: UUID) -> SupportTicket:
    ticket = (
        SupportTicket.objects.select_related(
            "member", "member__founder_profile", "assignee", "assignee__founder_profile"
        )
        .filter(pk=ticket_id)
        .first()
    )
    if ticket is None:
        raise exceptions.NotFound()
    return ticket


def _detail(ticket_id: UUID, status_code: int = 200) -> Response:
    return Response(AdminTicketDetailSerializer(_ticket(ticket_id)).data, status=status_code)


class AdminTicketsView(APIView):
    policy = MANAGE
    pagination_class = AdminLimitOffsetPagination  # documents the page shape

    @extend_schema(
        operation_id="admin_support_tickets_list",
        summary="The support inbox",
        description="`status=working` means everything not resolved. `assignee` is `me`, "
        "`unassigned` or a person's id. `q` matches the ticket number (SUP-1042), subject, name "
        "and email.",
        parameters=[AdminTicketQuerySerializer],
        responses={200: AdminTicketRowSerializer(many=True), **ERRORS},
        tags=["admin"],
    )
    def get(self, request: Request) -> Response:
        params = AdminTicketQuerySerializer(data=request.query_params.dict())
        params.is_valid(raise_exception=True)
        filters = {k: v for k, v in params.validated_data.items() if k not in ("limit", "offset")}
        paginator = AdminLimitOffsetPagination()
        rows = selectors.admin_tickets(me=_admin(request).pk, **filters)
        page = paginator.paginate_queryset(rows, request, view=self)
        return paginator.get_paginated_response(
            AdminTicketRowSerializer(page or [], many=True).data
        )


class AdminTicketView(APIView):
    policy = MANAGE

    @extend_schema(
        operation_id="admin_support_ticket_read",
        summary="One request with its whole conversation, internal notes included",
        responses={200: AdminTicketDetailSerializer, **ERRORS},
        tags=["admin"],
    )
    def get(self, request: Request, ticket_id: UUID) -> Response:
        return _detail(ticket_id)

    @extend_schema(
        summary="Change status, assignee, priority or category",
        request=AdminTicketUpdateSerializer,
        responses={
            200: AdminTicketDetailSerializer,
            400: OpenApiResponse(description="Invalid"),
            **ERRORS,
        },
        tags=["admin"],
    )
    def patch(self, request: Request, ticket_id: UUID) -> Response:
        data = AdminTicketUpdateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        _ticket(ticket_id)
        services.update_ticket(
            ticket_id=ticket_id, admin=_admin(request), changes=dict(data.validated_data)
        )
        return _detail(ticket_id)


class AdminTicketMessagesView(APIView):
    policy = MANAGE

    @extend_schema(
        summary="Reply to the member, or leave an internal note",
        description="A reply moves the request to `status` (default: awaiting the member) and "
        "tells the member. An internal note changes nothing and is never shown to the member.",
        request=AdminMessageSerializer,
        responses={
            201: SupportMessageSerializer,
            400: OpenApiResponse(description="Invalid"),
            **ERRORS,
        },
        tags=["admin"],
    )
    def post(self, request: Request, ticket_id: UUID) -> Response:
        data = AdminMessageSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        _ticket(ticket_id)
        row = services.add_admin_message(
            ticket_id=ticket_id,
            admin=_admin(request),
            body=data.validated_data["body"],
            internal=data.validated_data["internal"],
            status=data.validated_data["status"],
            upload_ids=data.validated_data["attachments"],
        )
        return Response(SupportMessageSerializer(row).data, status=status.HTTP_201_CREATED)


class AdminTicketResolveView(APIView):
    policy = MANAGE

    @extend_schema(
        summary="Resolve a request",
        description="Records who resolved it and when, and tells the member.",
        request=None,
        responses={200: AdminTicketDetailSerializer, **ERRORS},
        tags=["admin"],
    )
    def post(self, request: Request, ticket_id: UUID) -> Response:
        _ticket(ticket_id)
        services.resolve(ticket_id=ticket_id, admin=_admin(request))
        return _detail(ticket_id)


class AdminTicketReopenView(APIView):
    policy = MANAGE

    @extend_schema(
        summary="Reopen a resolved request",
        request=None,
        responses={
            200: AdminTicketDetailSerializer,
            409: OpenApiResponse(description="Not resolved"),
            **ERRORS,
        },
        tags=["admin"],
    )
    def post(self, request: Request, ticket_id: UUID) -> Response:
        _ticket(ticket_id)
        services.reopen(ticket_id=ticket_id, actor=_admin(request), by_member=False)
        return _detail(ticket_id)


class AdminSupportStatsView(APIView):
    policy = MANAGE

    @extend_schema(
        summary="Numbers for the top of the inbox",
        responses={200: StatsSerializer, **ERRORS},
        tags=["admin"],
    )
    def get(self, request: Request) -> Response:
        body = {
            "counts": selectors.counts(),
            "median_first_response_seconds": selectors.median_first_response_seconds(),
            "overdue": selectors.overdue_count(),
            "sla_hours": services.sla_hours(),
        }
        return Response(StatsSerializer(body).data)


class AdminSupportAgentsView(APIView):
    policy = MANAGE

    @extend_schema(
        summary="People a request can be assigned to",
        responses={200: SupportPersonSerializer(many=True), **ERRORS},
        tags=["admin"],
    )
    def get(self, request: Request) -> Response:
        ids = accounts.ids_with_roles(services.ADMIN_ROLES).distinct()
        users = (
            User.objects.filter(pk__in=list(ids), status="active")
            .select_related("founder_profile")
            .order_by("email")
        )
        rows = [person(u) for u in users if "support.manage" in permissions_for(u.role_names())]
        return Response(SupportPersonSerializer(rows, many=True).data)


class AdminCannedRepliesView(APIView):
    policy = MANAGE

    @extend_schema(
        summary="Saved replies",
        parameters=[],
        responses={200: CannedReplyOutSerializer(many=True), **ERRORS},
        tags=["admin"],
    )
    def get(self, request: Request) -> Response:
        category = request.query_params.get("category", "")
        every = request.query_params.get("all") == "true"
        rows = selectors.canned(category, active_only=not every)
        return Response(CannedReplyOutSerializer(rows, many=True).data)

    @extend_schema(
        summary="Save a reply",
        request=CannedReplySerializer,
        responses={
            201: CannedReplyOutSerializer,
            400: OpenApiResponse(description="Invalid"),
            **ERRORS,
        },
        tags=["admin"],
    )
    def post(self, request: Request) -> Response:
        data = CannedReplySerializer(data=request.data)
        data.is_valid(raise_exception=True)
        reply = services.save_canned(reply=None, data=dict(data.validated_data))
        return Response(CannedReplyOutSerializer(reply).data, status=status.HTTP_201_CREATED)


class AdminCannedReplyView(APIView):
    policy = MANAGE

    def _reply(self, reply_id: UUID) -> SupportCannedReply:
        reply = SupportCannedReply.objects.filter(pk=reply_id).first()
        if reply is None:
            raise exceptions.NotFound()
        return reply

    @extend_schema(
        summary="Change a saved reply",
        request=CannedReplySerializer,
        responses={
            200: CannedReplyOutSerializer,
            400: OpenApiResponse(description="Invalid"),
            **ERRORS,
        },
        tags=["admin"],
    )
    def put(self, request: Request, reply_id: UUID) -> Response:
        data = CannedReplySerializer(data=request.data)
        data.is_valid(raise_exception=True)
        reply = services.save_canned(reply=self._reply(reply_id), data=dict(data.validated_data))
        return Response(CannedReplyOutSerializer(reply).data)

    @extend_schema(
        summary="Delete a saved reply",
        responses={204: OpenApiResponse(description="Deleted"), **ERRORS},
        tags=["admin"],
    )
    def delete(self, request: Request, reply_id: UUID) -> Response:
        reply = self._reply(reply_id)
        audit.record(
            actor=_admin(request),
            action="support.canned_reply.deleted",
            target_type="support_canned_reply",
            target_id=reply.pk,
            before={"title": reply.title},
        )
        reply.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminAttachmentDownloadView(APIView):
    policy = MANAGE

    @extend_schema(
        summary="A short lived link to a file on a request",
        responses={200: AttachmentLinkSerializer, **ERRORS},
        tags=["admin"],
    )
    def get(self, request: Request, attachment_id: UUID) -> Response:
        item = selectors.attachment(attachment_id)
        if item is None:
            raise exceptions.NotFound()
        url, ttl = services.attachment_link(item)
        return Response({"url": url, "expires_in": ttl})
