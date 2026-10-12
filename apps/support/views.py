from typing import cast
from uuid import UUID

from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import exceptions, serializers, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.core import policies
from apps.core.pagination import AdminLimitOffsetPagination
from apps.core.serializers import StrictSerializer
from apps.support import selectors, services
from apps.support.models import SupportTicket
from apps.support.serializers import (
    AttachmentLinkSerializer,
    FeedbackSerializer,
    MessageCreateSerializer,
    MessageSerializer,
    PublicContactSerializer,
    TicketCreateSerializer,
    TicketDetailSerializer,
    TicketSerializer,
)

ERRORS = {
    401: OpenApiResponse(description="Not logged in"),
    404: OpenApiResponse(description="No such request (or it is not yours)"),
}
IDEMPOTENCY = OpenApiParameter(
    "Idempotency-Key",
    str,
    OpenApiParameter.HEADER,
    description="Send the same value when retrying, so a double click opens one request.",
)


class TicketListQuerySerializer(StrictSerializer):
    status = serializers.ChoiceField(
        choices=("open", "in_progress", "awaiting_member", "resolved"),
        required=False,
        allow_blank=True,
    )
    limit = serializers.IntegerField(required=False, min_value=1, max_value=100)
    offset = serializers.IntegerField(required=False, min_value=0)


def _user(request: Request) -> User:
    return cast(User, request.user)


def _own(request: Request, ticket_id: UUID) -> SupportTicket:
    ticket = selectors.member_ticket(_user(request).pk, ticket_id)
    if ticket is None:
        raise exceptions.NotFound()
    return ticket


def _display_name(user: User) -> str:
    profile = getattr(user, "founder_profile", None)
    return (profile.full_name if profile else "") or user.email.split("@")[0]


class TicketsView(APIView):
    policy = policies.authenticated
    pagination_class = AdminLimitOffsetPagination  # documents the page shape
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "support_write"

    def get_throttles(self) -> list:
        # Reading your own requests is not limited like writing them is.
        return super().get_throttles() if self.request.method == "POST" else []

    @extend_schema(
        summary="Your support requests",
        parameters=[TicketListQuerySerializer],
        responses={200: TicketSerializer(many=True), **ERRORS},
        tags=["support"],
    )
    def get(self, request: Request) -> Response:
        params = TicketListQuerySerializer(data=request.query_params.dict())
        params.is_valid(raise_exception=True)
        paginator = AdminLimitOffsetPagination()
        rows = selectors.member_tickets(_user(request).pk, params.validated_data.get("status", ""))
        page = paginator.paginate_queryset(rows, request, view=self)
        return paginator.get_paginated_response(TicketSerializer(page or [], many=True).data)

    @extend_schema(
        summary="Send a support request",
        description="Attach up to three files (PDF or image, 5 MB each) by passing the ids of "
        "ready `support_attachment` uploads.",
        parameters=[IDEMPOTENCY],
        request=TicketCreateSerializer,
        responses={
            201: TicketDetailSerializer,
            400: OpenApiResponse(description="Invalid request"),
            429: OpenApiResponse(description="Too many requests"),
            **ERRORS,
        },
        tags=["support"],
    )
    def post(self, request: Request) -> Response:
        data = TicketCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        user = _user(request)
        ticket = services.create_ticket(
            member=user,
            name=_display_name(user),
            email=user.email,
            category=data.validated_data["category"],
            subject=data.validated_data["subject"],
            message=data.validated_data["message"],
            upload_ids=data.validated_data["attachments"],
            idempotency_key=request.headers.get("Idempotency-Key", "")[:64],
        )
        return Response(TicketDetailSerializer(ticket).data, status=status.HTTP_201_CREATED)


class TicketView(APIView):
    policy = policies.authenticated

    @extend_schema(
        summary="One of your requests, with its conversation",
        description="Internal notes are never included.",
        responses={200: TicketDetailSerializer, **ERRORS},
        tags=["support"],
    )
    def get(self, request: Request, ticket_id: UUID) -> Response:
        return Response(TicketDetailSerializer(_own(request, ticket_id)).data)


class TicketMessagesView(APIView):
    policy = policies.authenticated
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "support_write"

    @extend_schema(
        summary="Reply on one of your requests",
        request=MessageCreateSerializer,
        responses={
            201: MessageSerializer,
            400: OpenApiResponse(description="Invalid message"),
            409: OpenApiResponse(description="The request is resolved: reopen it first"),
            **ERRORS,
        },
        tags=["support"],
    )
    def post(self, request: Request, ticket_id: UUID) -> Response:
        data = MessageCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        row = services.add_member_message(
            ticket_id=_own(request, ticket_id).pk,
            member=_user(request),
            message=data.validated_data["message"],
            upload_ids=data.validated_data["attachments"],
        )
        return Response(MessageSerializer(row).data, status=status.HTTP_201_CREATED)


class TicketReopenView(APIView):
    policy = policies.authenticated

    @extend_schema(
        summary="Reopen a resolved request",
        description="Allowed for 14 days after it was resolved.",
        request=None,
        responses={
            200: TicketDetailSerializer,
            409: OpenApiResponse(description="Not resolved, or too long ago"),
            **ERRORS,
        },
        tags=["support"],
    )
    def post(self, request: Request, ticket_id: UUID) -> Response:
        ticket = services.reopen(
            ticket_id=_own(request, ticket_id).pk, actor=_user(request), by_member=True
        )
        return Response(TicketDetailSerializer(ticket).data)


class TicketFeedbackView(APIView):
    policy = policies.authenticated

    @extend_schema(
        summary="Say whether the help was useful",
        request=FeedbackSerializer,
        responses={
            200: TicketDetailSerializer,
            409: OpenApiResponse(description="Not resolved yet"),
            **ERRORS,
        },
        tags=["support"],
    )
    def post(self, request: Request, ticket_id: UUID) -> Response:
        data = FeedbackSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        ticket = services.give_feedback(
            ticket_id=_own(request, ticket_id).pk,
            member=_user(request),
            satisfaction=data.validated_data["satisfaction"],
            comment=data.validated_data["comment"],
        )
        return Response(TicketDetailSerializer(ticket).data)


class AttachmentDownloadView(APIView):
    policy = policies.authenticated

    @extend_schema(
        summary="A short lived link to a file attached to one of your requests",
        responses={200: AttachmentLinkSerializer, **ERRORS},
        tags=["support"],
    )
    def get(self, request: Request, attachment_id: UUID) -> Response:
        item = selectors.attachment(attachment_id)
        # Someone else's file, or one on an internal note, looks like no file at all.
        if (
            item is None
            or item.message.ticket.member_id != _user(request).pk
            or item.message.is_internal
        ):
            raise exceptions.NotFound()
        url, ttl = services.attachment_link(item)
        return Response({"url": url, "expires_in": ttl})


class PublicContactView(APIView):
    """For people who cannot sign in. Answered by email, since there is no account to open."""

    policy = policies.public
    authentication_classes: list = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "support_contact"

    @extend_schema(
        summary="Ask for help without signing in",
        description="Meant for sign in problems. We answer by email. A hidden field named "
        "`website` must stay empty.",
        request=PublicContactSerializer,
        responses={
            202: OpenApiResponse(description="Received"),
            400: OpenApiResponse(description="Invalid request"),
            429: OpenApiResponse(description="Too many requests"),
        },
        tags=["support"],
    )
    def post(self, request: Request) -> Response:
        data = PublicContactSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        if values["website"]:  # a bot: say thanks and do nothing
            return Response(status=status.HTTP_202_ACCEPTED)
        services.create_ticket(
            member=None,
            name=values["name"],
            email=values["email"],
            category="account",
            subject=values["subject"],
            message=values["message"],
        )
        return Response(status=status.HTTP_202_ACCEPTED)
