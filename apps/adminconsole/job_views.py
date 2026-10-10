from typing import Any
from uuid import UUID

from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import exceptions
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.adminconsole.views import _actor, _ip
from apps.core import etag, policies
from apps.core.pagination import AdminLimitOffsetPagination
from apps.jobs import selectors, services
from apps.jobs.models import Job, JobSettings
from apps.jobs.serializers import (
    AdminJobCreateSerializer,
    AdminJobQuerySerializer,
    AdminJobSerializer,
    JobSettingsSerializer,
    JobUpdateSerializer,
    ReviewSerializer,
)

MODERATE = policies.admin_permission("jobs.moderate")
SETTINGS = policies.admin_permission("settings.manage")
IF_MATCH = OpenApiParameter("If-Match", str, OpenApiParameter.HEADER, required=True)
ERRORS = {
    401: OpenApiResponse(description="Not authenticated"),
    403: OpenApiResponse(description="Not allowed, or MFA missing"),
    404: OpenApiResponse(description="No such job"),
}


def _one(request: Request, job: Job, status_code: int = 200) -> Response:
    view = selectors.admin_views(_actor(request), [job])[0]
    return etag.add_etag(Response(AdminJobSerializer(view).data, status=status_code), job)


def _get(job_id: UUID) -> Job:
    job = Job.objects.filter(pk=job_id).first()
    if job is None:
        raise exceptions.NotFound()
    return job


class AdminJobsView(APIView):
    policy = MODERATE

    @extend_schema(
        summary="All jobs, for moderation",
        description="Oldest first. Filter by `status` (use `pending` for the review queue), "
        "`origin` (member or admin) and text.",
        parameters=[AdminJobQuerySerializer],
        responses={200: AdminJobSerializer(many=True), **ERRORS},
        tags=["admin"],
    )
    def get(self, request: Request) -> Response:
        params = AdminJobQuerySerializer(data=request.query_params.dict())
        params.is_valid(raise_exception=True)
        filters = {k: v for k, v in params.validated_data.items() if k not in ("limit", "offset")}
        paginator = AdminLimitOffsetPagination()
        page = paginator.paginate_queryset(selectors.admin_queryset(**filters), request, view=self)
        views = selectors.admin_views(_actor(request), page or [])
        return paginator.get_paginated_response(AdminJobSerializer(views, many=True).data)

    @extend_schema(
        summary="Post a job for the community or a partner",
        description="Goes live at once. Needs an external https link to apply, and either a "
        "startup or the name of the hiring organisation.",
        request=AdminJobCreateSerializer,
        responses={201: AdminJobSerializer, **ERRORS},
        tags=["admin"],
    )
    def post(self, request: Request) -> Response:
        serializer = AdminJobCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        job = services.create_job(
            user_id=_actor(request).pk, data=dict(serializer.validated_data), admin=True
        )
        return _one(request, job, 201)


class AdminJobView(APIView):
    policy = MODERATE

    @extend_schema(summary="One job", responses={200: AdminJobSerializer, **ERRORS}, tags=["admin"])
    def get(self, request: Request, job_id: UUID) -> Response:
        return _one(request, _get(job_id))

    @extend_schema(
        summary="Edit any job",
        parameters=[IF_MATCH],
        request=JobUpdateSerializer,
        responses={
            200: AdminJobSerializer,
            **ERRORS,
            409: OpenApiResponse(description="Closed, expired or rejected"),
            412: OpenApiResponse(description="Changed since the ETag was issued"),
            428: OpenApiResponse(description="If-Match header missing"),
        },
        tags=["admin"],
    )
    def patch(self, request: Request, job_id: UUID) -> Response:
        serializer = JobUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        job = services.update_job(
            user_id=_actor(request).pk,
            job_id=job_id,
            data=dict(serializer.validated_data),
            if_match=request.headers.get("If-Match"),
            admin=True,
        )
        return _one(request, job)


class ReviewJobView(APIView):
    """Approve, reject, unpublish or remove a job. The URL names the decision."""

    policy = MODERATE
    decision = ""

    @extend_schema(
        summary="Review a job",
        description="Decisions: approve and reject (pending jobs; rejecting needs a reason, "
        "which the poster is told), unpublish (live jobs) and remove (any). Audited.",
        request=ReviewSerializer,
        responses={
            200: AdminJobSerializer,
            **ERRORS,
            409: OpenApiResponse(description="Not in a state that allows this"),
        },
        tags=["admin"],
    )
    def post(self, request: Request, job_id: UUID) -> Response:
        serializer = ReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        job = services.review_job(
            actor=_actor(request),
            job_id=job_id,
            decision=self.decision,
            note=serializer.validated_data["reason"],
            ip=_ip(request),
        )
        return _one(request, job)


def review_view(decision: str) -> type[ReviewJobView]:
    return type(f"{decision.title()}JobView", (ReviewJobView,), {"decision": decision})


class JobSettingsView(APIView):
    policy = SETTINGS

    @extend_schema(
        summary="Job board settings",
        responses={200: JobSettingsSerializer, **ERRORS},
        tags=["admin"],
    )
    def get(self, request: Request) -> Response:
        return Response(JobSettingsSerializer(JobSettings.load()).data)

    @extend_schema(
        summary="Change job board settings",
        description="`require_approval`: member jobs wait for an admin (true) or go live at once. "
        "`default_duration_days`: how long a job without a deadline stays up.",
        request=JobSettingsSerializer,
        responses={200: JobSettingsSerializer, **ERRORS},
        tags=["admin"],
    )
    def put(self, request: Request) -> Response:
        serializer = JobSettingsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        current: Any = JobSettings.load()
        current.require_approval = serializer.validated_data["require_approval"]
        current.default_duration_days = serializer.validated_data["default_duration_days"]
        current.save()
        return Response(JobSettingsSerializer(current).data)
