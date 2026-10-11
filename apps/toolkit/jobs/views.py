import hashlib
from typing import Any
from uuid import UUID

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import exceptions
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.toolkit.jobs import exports, services
from apps.toolkit.jobs.serializers import TkExportFileSerializer, TkJobSerializer
from apps.toolkit.ventures.permissions import member_policy, uid

ERRORS = {
    401: OpenApiResponse(description="Not authenticated"),
    403: OpenApiResponse(description="Not an approved member"),
    404: OpenApiResponse(description="No such job, or not yours"),
}


def _tag(data: dict) -> str:
    stamp = f"{data['id']}:{data['status']}:{data['progress']}:{data['step_label']}"
    return '"' + hashlib.sha256(stamp.encode()).hexdigest()[:32] + '"'


def job_response(request: Request, data: dict, status_code: int = 200) -> Response:
    """The job, with an ETag so a poll that sees no change costs almost nothing (304)."""
    tag = _tag(data)
    response: Response
    if request.headers.get("If-None-Match") == tag and status_code == 200:
        response = Response(status=304)
    else:
        response = Response(TkJobSerializer(data).data, status=status_code)
    response["ETag"] = tag
    response["Cache-Control"] = "private, no-store"
    return response


class JobView(APIView):
    policy = member_policy()

    @extend_schema(
        summary="Where a job stands",
        description="Poll every couple of seconds with `If-None-Match`; an unchanged job answers "
        "304. `status` is queued, running, succeeded, failed or cancelled. On success `result` "
        "says what was made.",
        responses={200: TkJobSerializer, 304: OpenApiResponse(description="Unchanged"), **ERRORS},
        tags=["toolkit"],
    )
    def get(self, request: Request, job_id: UUID) -> Response:
        job = services.owned(uid(request), job_id)
        if job is None:
            raise exceptions.NotFound()
        return job_response(request, services.view(job))


class JobCancelView(APIView):
    policy = member_policy()

    @extend_schema(
        summary="Stop a job",
        description="A queued job is cancelled at once; a running one stops at its next step.",
        request=None,
        responses={200: TkJobSerializer, **ERRORS},
        tags=["toolkit"],
    )
    def post(self, request: Request, job_id: UUID) -> Response:
        job = services.owned(uid(request), job_id)
        if job is None:
            raise exceptions.NotFound()
        return job_response(request, services.view(services.cancel(job)))


class ExportFileView(APIView):
    policy = member_policy()

    @extend_schema(
        summary="A generated document and a fresh download link",
        description="Ask again for a new link when one has expired. Files are removed after "
        "a week; generate the document again if it is gone (404).",
        responses={200: TkExportFileSerializer, **ERRORS},
        tags=["toolkit"],
    )
    def get(self, request: Request, export_id: UUID) -> Response:
        file = exports.owned(uid(request), export_id)
        if file is None:
            raise exceptions.NotFound()
        response = Response(TkExportFileSerializer(exports.view(file)).data)
        response["Cache-Control"] = "private, no-store"
        return response


def accepted(request: Request, job: Any, created: bool) -> Response:
    """The answer to a request that started a job: 202 with the job to poll."""
    response = job_response(request, services.view(job), status_code=202 if created else 200)
    response["Location"] = f"/api/v1/toolkit/jobs/{job.pk}"
    return response


def idempotency_key(request: Request) -> str:
    return request.headers.get("Idempotency-Key", "").strip()[:80]
