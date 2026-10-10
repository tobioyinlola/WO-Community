from typing import Any, cast
from uuid import UUID

from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import exceptions, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core import etag, policies
from apps.core.public import PublicView
from apps.jobs import selectors, services
from apps.jobs.models import JobAlert
from apps.jobs.serializers import (
    AlertCreateSerializer,
    AlertSerializer,
    BoardQuerySerializer,
    JobCreateSerializer,
    JobPageSerializer,
    JobSerializer,
    JobSitemapListSerializer,
    JobUpdateSerializer,
    PageQuerySerializer,
    PublicJobPageSerializer,
    PublicJobSerializer,
    PublicQuerySerializer,
    RenewSerializer,
    SaveResultSerializer,
)

IF_MATCH = OpenApiParameter("If-Match", str, OpenApiParameter.HEADER, required=True)
ERRORS = {
    401: OpenApiResponse(description="Not authenticated"),
    403: OpenApiResponse(description="Not an active member"),
    404: OpenApiResponse(description="Not found, or not visible to you"),
}


def _uid(request: Request) -> UUID:
    return cast(UUID, request.user.pk)


def _require_post_permission(request: Request) -> None:
    if not policies.has_permission("jobs.post")(request.user, None):
        raise exceptions.PermissionDenied()


def _job_response(request: Request, job_id: UUID, *, status_code: int = 200) -> Response:
    job, view = selectors.detail(request.user, job_id)
    return etag.add_etag(Response(JobSerializer(view).data, status=status_code), job)


def _page(request: Request, serializer_class: Any) -> dict[str, Any]:
    params = serializer_class(data=request.query_params)
    params.is_valid(raise_exception=True)
    return dict(params.validated_data)


class JobsView(APIView):
    policy = policies.active_member

    @extend_schema(
        operation_id="jobs_list",
        summary="The jobs board",
        description="Live jobs, newest first. Filter by text, type, remote, startup, location "
        "and how recently they were posted. Text search tolerates small typos.",
        parameters=[BoardQuerySerializer],
        responses={200: JobPageSerializer, **ERRORS},
        tags=["jobs"],
    )
    def get(self, request: Request) -> Response:
        response = Response(
            JobPageSerializer(
                selectors.board(request.user, **_page(request, BoardQuerySerializer))
            ).data
        )
        response["Cache-Control"] = "private, no-store"
        return response

    @extend_schema(
        summary="Post a job or opportunity",
        description="Apply by an external https link or an email address; the platform does not "
        "handle applications. Depending on the board setting the job goes live at once or waits "
        "for an admin (`status` says which). Name your startup or the hiring organisation. "
        "Limited per member per day.",
        request=JobCreateSerializer,
        responses={201: JobSerializer, **ERRORS, 429: OpenApiResponse(description="Daily limit")},
        tags=["jobs"],
    )
    def post(self, request: Request) -> Response:
        _require_post_permission(request)
        serializer = JobCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        job = services.create_job(user_id=_uid(request), data=dict(serializer.validated_data))
        return _job_response(request, job.pk, status_code=201)


class JobView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="One job",
        description="Live jobs, and your own jobs in any state except removed.",
        responses={200: JobSerializer, **ERRORS},
        tags=["jobs"],
    )
    def get(self, request: Request, job_id: UUID) -> Response:
        return _job_response(request, job_id)

    @extend_schema(
        summary="Edit your job",
        description="Send only what changes, with the ETag in If-Match. Pending and published "
        "jobs only; renew a closed or expired job first.",
        parameters=[IF_MATCH],
        request=JobUpdateSerializer,
        responses={
            200: JobSerializer,
            **ERRORS,
            409: OpenApiResponse(description="Closed, expired or rejected"),
            412: OpenApiResponse(description="Changed since the ETag was issued"),
            428: OpenApiResponse(description="If-Match header missing"),
        },
        tags=["jobs"],
    )
    def patch(self, request: Request, job_id: UUID) -> Response:
        serializer = JobUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.update_job(
            user_id=_uid(request),
            job_id=job_id,
            data=dict(serializer.validated_data),
            if_match=request.headers.get("If-Match"),
        )
        return _job_response(request, job_id)


class RenewJobView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="Renew a job for another term",
        description="Works on published, expired and closed jobs. Send a new `deadline` or none "
        "for the default duration.",
        request=RenewSerializer,
        responses={200: JobSerializer, **ERRORS, 409: OpenApiResponse(description="Cannot renew")},
        tags=["jobs"],
    )
    def post(self, request: Request, job_id: UUID) -> Response:
        serializer = RenewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.renew_job(
            user_id=_uid(request), job_id=job_id, deadline=serializer.validated_data["deadline"]
        )
        return _job_response(request, job_id)


class CloseJobView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="Close your job",
        request=None,
        responses={200: JobSerializer, **ERRORS, 409: OpenApiResponse(description="Cannot close")},
        tags=["jobs"],
    )
    def post(self, request: Request, job_id: UUID) -> Response:
        services.close_job(user_id=_uid(request), job_id=job_id)
        return _job_response(request, job_id)


class MyJobsView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="Jobs you posted, in any state",
        parameters=[PageQuerySerializer],
        responses={200: JobPageSerializer, **ERRORS},
        tags=["jobs"],
    )
    def get(self, request: Request) -> Response:
        page = selectors.mine(request.user, **_page(request, PageQuerySerializer))
        response = Response(JobPageSerializer(page).data)
        response["Cache-Control"] = "private, no-store"
        return response


class SaveJobView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="Save a job",
        description="Idempotent. Up to 200 saved jobs.",
        request=None,
        responses={201: SaveResultSerializer, 200: SaveResultSerializer, **ERRORS},
        tags=["jobs"],
    )
    def post(self, request: Request, job_id: UUID) -> Response:
        created = services.save_job(user_id=_uid(request), job_id=job_id)
        body = {"job_id": job_id, "saved": True}
        return Response(SaveResultSerializer(body).data, status=201 if created else 200)

    @extend_schema(
        summary="Unsave a job",
        description="Idempotent.",
        responses={204: None, **ERRORS},
        tags=["jobs"],
    )
    def delete(self, request: Request, job_id: UUID) -> Response:
        services.unsave_job(user_id=_uid(request), job_id=job_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


class SavedJobsView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="Your saved jobs",
        description="Newest save first. Jobs that have since ended stay listed, with their status.",
        parameters=[PageQuerySerializer],
        responses={200: JobPageSerializer, **ERRORS},
        tags=["jobs"],
    )
    def get(self, request: Request) -> Response:
        page = selectors.saved(request.user, **_page(request, PageQuerySerializer))
        response = Response(JobPageSerializer(page).data)
        response["Cache-Control"] = "private, no-store"
        return response


class AlertsView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="Your job alerts",
        responses={200: AlertSerializer(many=True), **ERRORS},
        tags=["jobs"],
    )
    def get(self, request: Request) -> Response:
        alerts = JobAlert.objects.filter(user_id=_uid(request)).order_by("created_at", "id")
        return Response(AlertSerializer(alerts, many=True).data)

    @extend_schema(
        summary="Create a job alert",
        description="Get told when a new job matches these filters, at once or in a daily "
        "digest. Up to 5 alerts. Notices follow your notification preferences for jobs.",
        request=AlertCreateSerializer,
        responses={201: AlertSerializer, **ERRORS},
        tags=["jobs"],
    )
    def post(self, request: Request) -> Response:
        serializer = AlertCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        alert = services.create_alert(
            user_id=_uid(request),
            filters=dict(serializer.validated_data["filters"]),
            frequency=serializer.validated_data["frequency"],
        )
        return Response(AlertSerializer(alert).data, status=201)


class AlertView(APIView):
    policy = policies.active_member

    @extend_schema(summary="Delete a job alert", responses={204: None, **ERRORS}, tags=["jobs"])
    def delete(self, request: Request, alert_id: UUID) -> Response:
        services.delete_alert(user_id=_uid(request), alert_id=alert_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


# --- public ---


class PublicJobsView(PublicView):
    @extend_schema(
        operation_id="public_jobs_list",
        summary="Public job board",
        description="Live jobs for anyone, cached. Apply emails are never shown.",
        parameters=[PublicQuerySerializer],
        responses={200: PublicJobPageSerializer, 400: OpenApiResponse(description="Bad filter")},
        tags=["public"],
    )
    def get(self, request: Request) -> Response:
        params = PublicQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        page = selectors.public_board(**params.validated_data)
        return self.cached(request, PublicJobPageSerializer(page).data)


class PublicJobView(PublicView):
    @extend_schema(
        summary="One public job, with Open Graph data for sharing",
        responses={200: PublicJobSerializer, 404: OpenApiResponse(description="Not found")},
        tags=["public"],
    )
    def get(self, request: Request, slug: str) -> Response:
        return self.cached(request, PublicJobSerializer(selectors.public_detail(slug)).data)


class PublicJobsSitemapView(PublicView):
    @extend_schema(
        summary="Every live public job with its last change, for search engines",
        responses={200: JobSitemapListSerializer},
        tags=["public"],
    )
    def get(self, request: Request) -> Response:
        if request.query_params:
            raise exceptions.ValidationError({"detail": "No parameters are accepted."})
        return self.cached(
            request, JobSitemapListSerializer({"results": selectors.public_sitemap()}).data
        )
