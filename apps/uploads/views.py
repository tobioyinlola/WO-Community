from typing import cast
from uuid import UUID

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.core import policies
from apps.uploads import services
from apps.uploads.serializers import (
    UploadCreatedSerializer,
    UploadRequestSerializer,
    UploadSerializer,
    created_body,
)

ERRORS = {
    400: OpenApiResponse(description="Invalid purpose, type or size"),
    401: OpenApiResponse(description="Not authenticated"),
    404: OpenApiResponse(description="No such upload"),
    409: OpenApiResponse(description="The file has not arrived, or the upload window closed"),
    429: OpenApiResponse(description="Too many uploads"),
}


def _uid(request: Request) -> UUID:
    return cast(UUID, request.user.pk)


class UploadCreateView(APIView):
    policy = policies.authenticated
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "uploads"

    @extend_schema(
        summary="Reserve an upload and get the form to send the file with",
        description="Post the form's `form_data`, then the file as the last field named `file`, "
        "to the form's `url`. The file goes straight to storage, never through this API. "
        "Then call `POST /uploads/{id}/complete`. Allowed: JPEG, PNG or WebP up to 5 MB.",
        request=UploadRequestSerializer,
        responses={201: UploadCreatedSerializer, **ERRORS},
        tags=["uploads"],
    )
    def post(self, request: Request) -> Response:
        serializer = UploadRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        upload, post = services.request_upload(owner_id=_uid(request), **serializer.validated_data)
        response = Response(
            UploadCreatedSerializer(created_body(upload, post)).data,
            status=status.HTTP_201_CREATED,
        )
        response["Cache-Control"] = "no-store"
        return response


class UploadDetailView(APIView):
    policy = policies.authenticated

    @extend_schema(
        summary="Status of one of your uploads",
        responses={200: UploadSerializer, **ERRORS},
        tags=["uploads"],
    )
    def get(self, request: Request, upload_id: UUID) -> Response:
        upload = services.get_owned(_uid(request), upload_id)
        response = Response(UploadSerializer(upload).data)
        response["Cache-Control"] = "no-store"
        return response


class UploadCompleteView(APIView):
    policy = policies.authenticated

    @extend_schema(
        summary="Tell the server the file has been uploaded",
        description="Starts the checks. Poll `GET /uploads/{id}` until the status is `ready` "
        "or `rejected`. Calling it again is harmless.",
        request=None,
        responses={202: UploadSerializer, **ERRORS},
        tags=["uploads"],
    )
    def post(self, request: Request, upload_id: UUID) -> Response:
        upload = services.complete_upload(owner_id=_uid(request), upload_id=upload_id)
        response = Response(UploadSerializer(upload).data, status=status.HTTP_202_ACCEPTED)
        response["Cache-Control"] = "no-store"
        return response
