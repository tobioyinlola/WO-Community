from typing import Any
from uuid import UUID

from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import exceptions, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.adminconsole.views import _actor, _ip
from apps.core import etag, policies
from apps.core.pagination import AdminLimitOffsetPagination
from apps.editorial import selectors, services
from apps.editorial.models import EditorialItem, WinSubmission
from apps.editorial.serializers import (
    AdminItemSerializer,
    AdminQuerySerializer,
    AdminWinSerializer,
    CoverSerializer,
    ItemCommentModerationSerializer,
    ItemCreateSerializer,
    ItemUpdateSerializer,
    ScheduleSerializer,
    WinQuerySerializer,
    WinReviewSerializer,
)

MANAGE = policies.admin_permission("editorial.manage")
IF_MATCH = OpenApiParameter("If-Match", str, OpenApiParameter.HEADER, required=True)
ERRORS = {
    401: OpenApiResponse(description="Not authenticated"),
    403: OpenApiResponse(description="Not allowed, or MFA missing"),
    404: OpenApiResponse(description="Not found"),
}


def _one(request: Request, item: EditorialItem, status_code: int = 200) -> Response:
    fresh = EditorialItem.objects.prefetch_related("startup_links").get(pk=item.pk)
    view = selectors.admin_views(_actor(request), [fresh])[0]
    return etag.add_etag(Response(AdminItemSerializer(view).data, status=status_code), fresh)


class AdminEditorialView(APIView):
    policy = MANAGE

    @extend_schema(
        summary="Editorial items, any state",
        description="Newest first. Filter by `status` (draft, scheduled, published), `type`, text.",
        parameters=[AdminQuerySerializer],
        responses={200: AdminItemSerializer(many=True), **ERRORS},
        tags=["admin"],
    )
    def get(self, request: Request) -> Response:
        params = AdminQuerySerializer(data=request.query_params.dict())
        params.is_valid(raise_exception=True)
        filters = {k: v for k, v in params.validated_data.items() if k not in ("limit", "offset")}
        paginator = AdminLimitOffsetPagination()
        queryset = selectors.admin_queryset(**filters).prefetch_related("startup_links")
        page = paginator.paginate_queryset(queryset, request, view=self)
        views = selectors.admin_views(_actor(request), page or [])
        return paginator.get_paginated_response(AdminItemSerializer(views, many=True).data)

    @extend_schema(
        summary="Write a news item, award, celebration, partnership, funding story or announcement",
        description="Starts as a draft. Publish it now, or schedule it. Only announcements can "
        "have a banner window (at most 90 days). `public` lets the public website show it.",
        request=ItemCreateSerializer,
        responses={201: AdminItemSerializer, **ERRORS},
        tags=["admin"],
    )
    def post(self, request: Request) -> Response:
        serializer = ItemCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = services.create_item(
            actor=_actor(request), data=dict(serializer.validated_data), ip=_ip(request)
        )
        return _one(request, item, 201)


class AdminEditorialItemView(APIView):
    policy = MANAGE

    @extend_schema(
        summary="One item", responses={200: AdminItemSerializer, **ERRORS}, tags=["admin"]
    )
    def get(self, request: Request, item_id: UUID) -> Response:
        item = (
            EditorialItem.objects.exclude(status=EditorialItem.Status.REMOVED)
            .filter(pk=item_id)
            .first()
        )
        if item is None:
            raise exceptions.NotFound()
        return _one(request, item)

    @extend_schema(
        summary="Edit an item",
        parameters=[IF_MATCH],
        request=ItemUpdateSerializer,
        responses={
            200: AdminItemSerializer,
            **ERRORS,
            412: OpenApiResponse(description="Changed since the ETag was issued"),
            428: OpenApiResponse(description="If-Match header missing"),
        },
        tags=["admin"],
    )
    def patch(self, request: Request, item_id: UUID) -> Response:
        serializer = ItemUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = services.update_item(
            actor=_actor(request),
            item_id=item_id,
            data=dict(serializer.validated_data),
            if_match=request.headers.get("If-Match"),
            ip=_ip(request),
        )
        return _one(request, item)

    @extend_schema(summary="Remove an item", responses={204: None, **ERRORS}, tags=["admin"])
    def delete(self, request: Request, item_id: UUID) -> Response:
        services.remove_item(actor=_actor(request), item_id=item_id, ip=_ip(request))
        return Response(status=status.HTTP_204_NO_CONTENT)


class PublishItemView(APIView):
    """Publish now, or take down / cancel a schedule (the URL names the action)."""

    policy = MANAGE
    action = ""

    @extend_schema(
        summary="Publish an item now, or take it down",
        request=None,
        responses={
            200: AdminItemSerializer,
            **ERRORS,
            409: OpenApiResponse(description="Not in a state that allows this"),
        },
        tags=["admin"],
    )
    def post(self, request: Request, item_id: UUID) -> Response:
        call = services.publish_now if self.action == "publish" else services.unpublish
        item = call(actor=_actor(request), item_id=item_id, ip=_ip(request))
        return _one(request, item)


def publish_view(action: str) -> type[PublishItemView]:
    return type(f"{action.title()}ItemView", (PublishItemView,), {"action": action})


class ScheduleItemView(APIView):
    policy = MANAGE

    @extend_schema(
        summary="Schedule an item to publish itself",
        description="`publish_at` must be in the future. A worker publishes it within a minute "
        "of that time, stamped with the scheduled time.",
        request=ScheduleSerializer,
        responses={
            200: AdminItemSerializer,
            **ERRORS,
            409: OpenApiResponse(description="Published"),
        },
        tags=["admin"],
    )
    def post(self, request: Request, item_id: UUID) -> Response:
        serializer = ScheduleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = services.schedule(
            actor=_actor(request),
            item_id=item_id,
            publish_at=serializer.validated_data["publish_at"],
            ip=_ip(request),
        )
        return _one(request, item)


class ItemCoverView(APIView):
    policy = MANAGE

    @extend_schema(
        summary="Use a finished upload as the cover",
        description="Upload with `POST /uploads` (purpose `editorial_cover`) and wait for `ready`.",
        request=CoverSerializer,
        responses={200: AdminItemSerializer, **ERRORS},
        tags=["admin"],
    )
    def put(self, request: Request, item_id: UUID) -> Response:
        serializer = CoverSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = services.set_cover(
            actor=_actor(request), item_id=item_id, upload_id=serializer.validated_data["upload_id"]
        )
        return _one(request, item)

    @extend_schema(
        summary="Remove the cover", responses={200: AdminItemSerializer, **ERRORS}, tags=["admin"]
    )
    def delete(self, request: Request, item_id: UUID) -> Response:
        item = services.set_cover(actor=_actor(request), item_id=item_id, upload_id=None)
        return _one(request, item)


class ModerateItemCommentView(APIView):
    """Hide, unhide or remove a comment on an item (the URL names the action)."""

    policy = MANAGE
    action = ""

    @extend_schema(
        summary="Moderate a comment on an item",
        request=ItemCommentModerationSerializer,
        responses={200: ItemCommentModerationSerializer, **ERRORS},
        tags=["admin"],
    )
    def post(self, request: Request, comment_id: UUID) -> Response:
        serializer = ItemCommentModerationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.moderate_comment(
            actor=_actor(request),
            comment_id=comment_id,
            action=self.action,
            reason=serializer.validated_data["reason"],
            ip=_ip(request),
        )
        return Response({"reason": serializer.validated_data["reason"]})


def comment_view(action: str) -> type[ModerateItemCommentView]:
    return type(f"{action.title()}ItemCommentView", (ModerateItemCommentView,), {"action": action})


class AdminWinsView(APIView):
    policy = MANAGE

    @extend_schema(
        summary="Win submissions awaiting review (or any status)",
        parameters=[WinQuerySerializer],
        responses={200: AdminWinSerializer(many=True), **ERRORS},
        tags=["admin"],
    )
    def get(self, request: Request) -> Response:
        params = WinQuerySerializer(data=request.query_params.dict())
        params.is_valid(raise_exception=True)
        paginator = AdminLimitOffsetPagination()
        queryset = selectors.admin_win_queryset(status=params.validated_data["status"])
        page = paginator.paginate_queryset(queryset, request, view=self)
        data = AdminWinSerializer(selectors.admin_win_views(page or []), many=True).data
        return paginator.get_paginated_response(data)


class ReviewWinView(APIView):
    policy = MANAGE
    decision = ""

    @extend_schema(
        summary="Approve or reject a win submission",
        description="Approving creates a draft story (linked as `item_id`) for an editor to "
        "polish and publish. Rejecting needs a reason. The member is told either way.",
        request=WinReviewSerializer,
        responses={
            200: AdminWinSerializer,
            **ERRORS,
            409: OpenApiResponse(description="Already reviewed"),
        },
        tags=["admin"],
    )
    def post(self, request: Request, win_id: UUID) -> Response:
        serializer = WinReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        win: WinSubmission = services.review_win(
            actor=_actor(request),
            win_id=win_id,
            decision=self.decision,
            note=serializer.validated_data["reason"],
            ip=_ip(request),
        )
        data: Any = selectors.admin_win_views([win])[0]
        return Response(AdminWinSerializer(data).data)


def win_view(decision: str) -> type[ReviewWinView]:
    return type(f"{decision.title()}WinView", (ReviewWinView,), {"decision": decision})
