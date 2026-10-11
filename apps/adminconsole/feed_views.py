from typing import Any
from uuid import UUID

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import exceptions, serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.adminconsole.views import _actor, _ip
from apps.core import policies
from apps.core.pagination import AdminLimitOffsetPagination
from apps.editorial import reporting as editorial_reporting
from apps.editorial.models import CommentReport
from apps.feed import moderation, previews_admin, services
from apps.feed.models import Report
from apps.feed.serializers import (
    AdminPreviewQuerySerializer,
    AdminPreviewSerializer,
    AdminReportSerializer,
    BlockDomainSerializer,
    BlockedDomainSerializer,
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
        description="Reports oldest first, open ones by default, for posts, comments and "
        "comments on news (`target_type=news_comment`). Each shows a short look at what was "
        "reported and how many open reports it has.",
        parameters=[ReportQuerySerializer],
        responses={200: AdminReportSerializer(many=True), **REPORT_ERRORS},
        tags=["admin"],
    )
    def get(self, request: Request) -> Response:
        params = ReportQuerySerializer(data=request.query_params.dict())
        params.is_valid(raise_exception=True)
        filters = {k: v for k, v in params.validated_data.items() if k not in ("limit", "offset")}
        wanted = filters.get("target_type", "")
        feed_rows: list[Any] = (
            [] if wanted == "news_comment" else list(moderation.queue(**filters)[:2000])
        )
        news_rows: list[Any] = (
            []
            if wanted in ("post", "comment")
            else list(
                editorial_reporting.queue(
                    status=filters.get("status", ""), reason=filters.get("reason", "")
                )[:2000]
            )
        )
        merged: list[Any] = sorted(
            [*feed_rows, *news_rows], key=lambda r: (r.created_at, str(r.pk))
        )
        paginator = AdminLimitOffsetPagination()
        page: list[Any] = (
            paginator.paginate_queryset(merged, request, view=self) or []  # type: ignore[arg-type]
        )
        views = _report_views(_actor(request), page)
        return paginator.get_paginated_response(AdminReportSerializer(views, many=True).data)


def _report_views(viewer: Any, reports: list[Any]) -> list[dict[str, Any]]:
    """Views for a mixed page of feed and editorial reports, in the page's order."""
    feed_part = [r for r in reports if isinstance(r, Report)]
    news_part = [r for r in reports if isinstance(r, CommentReport)]
    built = {
        **{v["id"]: v for v in moderation.report_views(viewer, feed_part)},
        **{v["id"]: v for v in editorial_reporting.views(viewer, news_part)},
    }
    return [built[r.pk] for r in reports]


def _find(report_id: UUID) -> Any:
    found: Any = Report.objects.filter(pk=report_id).first()
    if found is None:
        found = editorial_reporting.get_report(report_id)
    if found is None:
        raise exceptions.NotFound()
    return found


class ReportDetailView(APIView):
    policy = HANDLE

    @extend_schema(
        summary="One report",
        responses={200: AdminReportSerializer, **REPORT_ERRORS},
        tags=["admin"],
    )
    def get(self, request: Request, report_id: UUID) -> Response:
        report = _find(report_id)
        return Response(AdminReportSerializer(_report_views(_actor(request), [report])[0]).data)


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
        handler = (
            editorial_reporting.review
            if isinstance(_find(report_id), CommentReport)
            else moderation.review
        )
        report = handler(
            actor=_actor(request),
            report_id=report_id,
            note=serializer.validated_data["note"],
            ip=_ip(request),
        )
        return Response(AdminReportSerializer(_report_views(_actor(request), [report])[0]).data)


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
        handler = (
            editorial_reporting.act
            if isinstance(_find(report_id), CommentReport)
            else moderation.act
        )
        report = handler(
            actor=_actor(request),
            report_id=report_id,
            action=data["action"],
            note=data["note"],
            ip=_ip(request),
        )
        return Response(AdminReportSerializer(_report_views(_actor(request), [report])[0]).data)


# --- link preview cards ---


class AdminPreviewsView(APIView):
    policy = MODERATE

    @extend_schema(
        summary="Link preview cards",
        description="Newest first. Search by address (`q`) or filter by `status`. Shows how many "
        "posts use each card and whether its site is blocked.",
        parameters=[AdminPreviewQuerySerializer],
        responses={200: AdminPreviewSerializer(many=True), **ERRORS},
        tags=["admin"],
    )
    def get(self, request: Request) -> Response:
        params = AdminPreviewQuerySerializer(data=request.query_params.dict())
        params.is_valid(raise_exception=True)
        filters = {k: v for k, v in params.validated_data.items() if k in ("q", "status")}
        paginator = AdminLimitOffsetPagination()
        page = paginator.paginate_queryset(previews_admin.previews(**filters), request, view=self)
        rows = [previews_admin.preview_view(p) for p in page or []]
        return paginator.get_paginated_response(AdminPreviewSerializer(rows, many=True).data)


class AdminPreviewRefreshView(APIView):
    policy = MODERATE

    @extend_schema(
        summary="Fetch a card again",
        description="Queues a new fetch now. Refused for a blocked site.",
        request=None,
        responses={200: AdminPreviewSerializer, **ERRORS},
        tags=["admin"],
    )
    def post(self, request: Request, preview_id: UUID) -> Response:
        preview = previews_admin.refresh(
            actor=_actor(request), preview_id=preview_id, ip=_ip(request)
        )
        return Response(AdminPreviewSerializer(previews_admin.preview_view(preview)).data)


class BlockedDomainsView(APIView):
    policy = MODERATE

    @extend_schema(
        summary="Sites that never get a preview card",
        responses={200: BlockedDomainSerializer(many=True), **ERRORS},
        tags=["admin"],
    )
    def get(self, request: Request) -> Response:
        return Response(BlockedDomainSerializer(previews_admin.blocked(), many=True).data)

    @extend_schema(
        summary="Block a site from preview cards",
        description="The domain and every subdomain. Cards that already exist for it are taken "
        "down now and nothing more is fetched from it. Posts keep their plain link.",
        request=BlockDomainSerializer,
        responses={201: BlockedDomainSerializer, **ERRORS},
        tags=["admin"],
    )
    def post(self, request: Request) -> Response:
        serializer = BlockDomainSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        entry = previews_admin.block(
            actor=_actor(request), ip=_ip(request), **serializer.validated_data
        )
        return Response(BlockedDomainSerializer(entry).data, status=201)


class BlockedDomainView(APIView):
    policy = MODERATE

    @extend_schema(
        summary="Allow a site to have preview cards again",
        responses={204: None, **ERRORS},
        tags=["admin"],
    )
    def delete(self, request: Request, entry_id: UUID) -> Response:
        previews_admin.unblock(actor=_actor(request), entry_id=entry_id, ip=_ip(request))
        return Response(status=204)
