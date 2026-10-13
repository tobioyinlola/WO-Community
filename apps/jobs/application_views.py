from typing import Any, cast
from uuid import UUID

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import exceptions, serializers, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.adminconsole.people import people
from apps.core import policies
from apps.core.pagination import AdminLimitOffsetPagination
from apps.jobs import applications
from apps.jobs.application_serializers import (
    AdminApplicationQuerySerializer,
    ApplicationRowSerializer,
    ApplyJobSerializer,
    DecideApplicationSerializer,
    MyApplicationSerializer,
)
from apps.jobs.models import Job, JobApplication

ERRORS = {
    401: OpenApiResponse(description="Not authenticated"),
    403: OpenApiResponse(description="Not allowed"),
    404: OpenApiResponse(description="Not found, or not visible to you"),
}
MODERATE = policies.admin_permission("jobs.moderate")


def _uid(request: Request) -> UUID:
    return cast(UUID, request.user.pk)


def rows(items: list[JobApplication]) -> list[dict[str, Any]]:
    """Applications with the applicant and the job they are for."""
    who = people(a.applicant_id for a in items)
    jobs = applications.job_titles({a.job_id for a in items})
    out = []
    for a in items:
        job = jobs[a.job_id]
        out.append(
            {
                "id": a.pk,
                "status": a.status,
                "note": a.note,
                "link": a.link,
                "created_at": a.created_at,
                "decided_at": a.decided_at,
                "decision_note": a.decision_note,
                "applicant": who[a.applicant_id],
                "job_id": job.pk,
                "job_title": job.title,
                "job_organisation": job.organisation,
                "job_status": job.status,
            }
        )
    return out


class ApplyView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="Your application to a job",
        responses={200: MyApplicationSerializer, **ERRORS},
        tags=["jobs"],
    )
    def get(self, request: Request, job_id: UUID) -> Response:
        application = applications.mine(_uid(request), job_id)
        if application is None:
            raise exceptions.NotFound()
        return Response(MyApplicationSerializer(application).data)

    @extend_schema(
        summary="Apply to a job through the community",
        request=ApplyJobSerializer,
        responses={
            201: MyApplicationSerializer,
            **ERRORS,
            409: OpenApiResponse(description="Already applied, or the job is closed"),
        },
        tags=["jobs"],
    )
    def post(self, request: Request, job_id: UUID) -> Response:
        serializer = ApplyJobSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        application = applications.apply(
            user_id=_uid(request), job_id=job_id, **serializer.validated_data
        )
        return Response(MyApplicationSerializer(application).data, status=status.HTTP_201_CREATED)


class WithdrawView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="Withdraw your application",
        request=None,
        responses={200: MyApplicationSerializer, **ERRORS},
        tags=["jobs"],
    )
    def post(self, request: Request, application_id: UUID) -> Response:
        application = applications.withdraw(user_id=_uid(request), application_id=application_id)
        return Response(MyApplicationSerializer(application).data)


class JobApplicantsView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="Applications to your job",
        description="Only the member who posted the job, or an admin who moderates jobs.",
        responses={200: ApplicationRowSerializer(many=True), **ERRORS},
        tags=["jobs"],
    )
    def get(self, request: Request, job_id: UUID) -> Response:
        job = Job.objects.filter(pk=job_id).first()
        if job is None or (
            job.poster_id != _uid(request) and not applications.can_moderate(request.user)
        ):
            raise exceptions.NotFound()
        data = rows(list(applications.for_job(job_id)))
        return Response(ApplicationRowSerializer(data, many=True).data)


class DecideView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="Move an application along",
        description="The poster of the job, or an admin. Reviewing, shortlisted, rejected, hired.",
        request=DecideApplicationSerializer,
        responses={200: ApplicationRowSerializer, **ERRORS},
        tags=["jobs"],
    )
    def post(self, request: Request, application_id: UUID) -> Response:
        serializer = DecideApplicationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        application = applications.decide(
            actor=request.user,
            application_id=application_id,
            status=serializer.validated_data["status"],
            note=serializer.validated_data["note"],
        )
        return Response(ApplicationRowSerializer(rows([application])[0]).data)


class AdminApplicationsView(APIView):
    policy = MODERATE
    pagination_class = AdminLimitOffsetPagination  # documents the page shape

    @extend_schema(
        summary="All job applications",
        description="Newest first. Filter by `status`, `job_id` and text (job, organisation, "
        "applicant name or email).",
        parameters=[AdminApplicationQuerySerializer],
        responses={200: ApplicationRowSerializer(many=True), **ERRORS},
        tags=["admin"],
    )
    def get(self, request: Request) -> Response:
        params = AdminApplicationQuerySerializer(data=request.query_params.dict())
        params.is_valid(raise_exception=True)
        filters = {k: v for k, v in params.validated_data.items() if k not in ("limit", "offset")}
        paginator = AdminLimitOffsetPagination()
        page = paginator.paginate_queryset(
            applications.admin_queryset(**filters), request, view=self
        )
        return paginator.get_paginated_response(
            ApplicationRowSerializer(rows(list(page or [])), many=True).data
        )


class ApplicationStatsSerializer(serializers.Serializer):
    submitted = serializers.IntegerField()
    reviewing = serializers.IntegerField()
    shortlisted = serializers.IntegerField()
    rejected = serializers.IntegerField()
    hired = serializers.IntegerField()
    withdrawn = serializers.IntegerField()


class AdminApplicationStatsView(APIView):
    policy = MODERATE

    @extend_schema(
        summary="Applications by status",
        responses={200: ApplicationStatsSerializer, **ERRORS},
        tags=["admin"],
    )
    def get(self, request: Request) -> Response:
        return Response(ApplicationStatsSerializer(applications.counts()).data)
