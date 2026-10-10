from typing import Any
from uuid import UUID

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.adminconsole.views import _actor, _ip
from apps.core import policies
from apps.core.pagination import AdminLimitOffsetPagination
from apps.feed import moderation, services
from apps.feed.serializers import (
    AdminReportSerializer,
    ModerationSerializer,
    ReportActionSerializer,
    ReportQuerySerializer,
    ReportReviewSerializer,
)

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


class ModerateCommentView(APIView):
    """Hide, unhide or remove a comment. The URL names the action."""

    policy = MODERATE
    action = ""

    @extend_schema(
        summary="Moderate a comment",
        description="Actions: hide, unhide, remove (removing takes its replies too). The post's "
        "comment count follows. Every action is written to the audit log.",
        request=ModerationSerializer,
        responses={200: ModerationResultSerializer, **ERRORS},
        tags=["admin"],
    )
    def post(self, request: Request, comment_id: UUID) -> Response:
        serializer = ModerationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        comment: Any = moderation.moderate_comment(
            actor=_actor(request),
            comment_id=comment_id,
            action=self.action,
            reason=serializer.validated_data["reason"],
            ip=_ip(request),
        )
        return Response({"id": comment.pk, "action": self.action})


def comment_action_view(name: str) -> type[ModerateCommentView]:
    return type(f"{name.title()}CommentView", (ModerateCommentView,), {"action": name})


HANDLE = policies.admin_permission("reports.handle")
REPORT_ERRORS = {
    401: OpenApiResponse(description="Not authenticated"),
    403: OpenApiResponse(description="Not allowed, or MFA missing"),
    404: OpenApiResponse(description="No such report"),
}


class ReportListView(APIView):
    policy = HANDLE

    @extend_schema(
        summary="The moderation queue",
        description="Reports oldest first, open ones by default. Each shows a short look at the "
        "post or comment reported and how many open reports it has.",
        parameters=[ReportQuerySerializer],
        responses={200: AdminReportSerializer(many=True), **REPORT_ERRORS},
        tags=["admin"],
    )
    def get(self, request: Request) -> Response:
        params = ReportQuerySerializer(data=request.query_params.dict())
        params.is_valid(raise_exception=True)
        filters = {k: v for k, v in params.validated_data.items() if k not in ("limit", "offset")}
        paginator = AdminLimitOffsetPagination()
        page = paginator.paginate_queryset(moderation.queue(**filters), request, view=self)
        views = moderation.report_views(_actor(request), page or [])
        return paginator.get_paginated_response(AdminReportSerializer(views, many=True).data)


class ReportDetailView(APIView):
    policy = HANDLE

    @extend_schema(
        summary="One report",
        responses={200: AdminReportSerializer, **REPORT_ERRORS},
        tags=["admin"],
    )
    def get(self, request: Request, report_id: UUID) -> Response:
        report = moderation.get_report(report_id)
        return Response(
            AdminReportSerializer(moderation.report_views(_actor(request), [report])[0]).data
        )


class ReportReviewView(APIView):
    policy = HANDLE

    @extend_schema(
        summary="Mark a report as reviewed, with no action needed",
        request=ReportReviewSerializer,
        responses={
            200: AdminReportSerializer,
            **REPORT_ERRORS,
            409: OpenApiResponse(description="Already actioned"),
        },
        tags=["admin"],
    )
    def post(self, request: Request, report_id: UUID) -> Response:
        serializer = ReportReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        report = moderation.review(
            actor=_actor(request),
            report_id=report_id,
            note=serializer.validated_data["note"],
            ip=_ip(request),
        )
        return Response(
            AdminReportSerializer(moderation.report_views(_actor(request), [report])[0]).data
        )


class ReportActionView(APIView):
    policy = HANDLE

    @extend_schema(
        summary="Hide or remove what was reported",
        description="Applies the action to the post or comment and closes every open report "
        "about it as actioned. Written to the audit log.",
        request=ReportActionSerializer,
        responses={200: AdminReportSerializer, **REPORT_ERRORS},
        tags=["admin"],
    )
    def post(self, request: Request, report_id: UUID) -> Response:
        serializer = ReportActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        report = moderation.act(
            actor=_actor(request),
            report_id=report_id,
            action=data["action"],
            note=data["note"],
            ip=_ip(request),
        )
        return Response(
            AdminReportSerializer(moderation.report_views(_actor(request), [report])[0]).data
        )
