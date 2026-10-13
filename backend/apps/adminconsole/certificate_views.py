from typing import Any, cast
from uuid import UUID

from django.http import HttpResponse
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import exceptions
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.adminconsole.views import _ip
from apps.core import policies
from apps.core.pagination import AdminLimitOffsetPagination
from apps.learning import certificates
from apps.learning.models import Certificate
from apps.learning.serializers import (
    AdminCertificateSerializer,
    AdminCertificatesQuerySerializer,
    CertificatePreviewSerializer,
    CertificateSettingsSerializer,
    CertificateSettingsWriteSerializer,
    ReissueSerializer,
    RevokeSerializer,
)

MANAGE = policies.admin_permission("courses.manage")
ERRORS = {
    401: OpenApiResponse(description="Not authenticated"),
    403: OpenApiResponse(description="Not allowed, or MFA missing"),
    404: OpenApiResponse(description="Not found"),
}


def _actor(request: Request) -> User:
    return cast(User, request.user)


def _settings_body(row: Any) -> dict[str, Any]:
    return {
        "title_text": row.title_text,
        "signatory_name": row.signatory_name,
        "signatory_title": row.signatory_title,
        "signature_url": certificates.signature_url(row.signature_key),
        "version": row.version,
        "updated_at": row.updated_at,
    }


def _row(certificate: Certificate) -> dict[str, Any]:
    return {
        "id": certificate.pk,
        "number": certificate.code,
        "holder_name": certificate.holder_name,
        "email": certificate.enrolment.user.email,
        "course_title": certificate.course_title,
        "issued_at": certificate.issued_at,
        "hours": float(certificate.hours),
        "status": "valid" if certificate.is_valid else "revoked",
        "revoked_at": certificate.revoked_at,
        "revoked_reason": certificate.revoked_reason,
        "template_version": (certificate.template or {}).get("version"),
    }


def _one(certificate_id: UUID) -> Certificate:
    certificate = (
        Certificate.objects.select_related("enrolment__user", "enrolment__course")
        .filter(pk=certificate_id)
        .first()
    )
    if certificate is None:
        raise exceptions.NotFound()
    return certificate


class CertificateSettingsView(APIView):
    policy = MANAGE

    @extend_schema(
        summary="What appears on every new certificate",
        responses={200: CertificateSettingsSerializer, **ERRORS},
        tags=["admin"],
    )
    def get(self, request: Request) -> Response:
        body = _settings_body(certificates.current_settings())
        return Response(CertificateSettingsSerializer(body).data)

    @extend_schema(
        summary="Change the certificate template",
        description="Applies to certificates issued from now on. Certificates already issued keep "
        "the template they were drawn with until an administrator reissues them.",
        request=CertificateSettingsWriteSerializer,
        responses={200: CertificateSettingsSerializer, **ERRORS},
        tags=["admin"],
    )
    def put(self, request: Request) -> Response:
        data = CertificateSettingsWriteSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        row = certificates.update_settings(
            actor=_actor(request), data=dict(data.validated_data), ip=_ip(request)
        )
        return Response(CertificateSettingsSerializer(_settings_body(row)).data)


class CertificatePreviewView(APIView):
    policy = MANAGE

    @extend_schema(
        summary="Draw the certificate with sample details and the settings being edited",
        description="Nothing is saved. The body can carry unsaved edits of the template.",
        request=CertificatePreviewSerializer,
        responses={(200, "application/pdf"): OpenApiResponse(description="PDF"), **ERRORS},
        tags=["admin"],
    )
    def post(self, request: Request) -> HttpResponse:
        data = CertificatePreviewSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        response = HttpResponse(
            certificates.preview_pdf(data=dict(data.validated_data)),
            content_type=certificates.PDF_TYPE,
        )
        response["Content-Disposition"] = 'inline; filename="certificate-preview.pdf"'
        response["Cache-Control"] = "private, no-store"
        return response


class AdminCertificatesView(APIView):
    policy = MANAGE
    pagination_class = AdminLimitOffsetPagination  # documents the page shape

    @extend_schema(
        operation_id="admin_certificates_list",
        summary="Issued certificates, newest first",
        parameters=[AdminCertificatesQuerySerializer],
        responses={200: AdminCertificateSerializer(many=True), **ERRORS},
        tags=["admin"],
    )
    def get(self, request: Request) -> Response:
        params = AdminCertificatesQuerySerializer(data=request.query_params.dict())
        params.is_valid(raise_exception=True)
        paginator = AdminLimitOffsetPagination()
        rows = certificates.listed(
            q=params.validated_data["q"], status=params.validated_data["status"]
        )
        page = paginator.paginate_queryset(rows, request, view=self)
        return paginator.get_paginated_response(
            AdminCertificateSerializer([_row(c) for c in page or []], many=True).data
        )


class RevokeCertificateView(APIView):
    policy = MANAGE

    @extend_schema(
        summary="Revoke a certificate",
        description="The public page then shows it as revoked and the member can no longer "
        "download it. A reason is required and goes in the audit log.",
        request=RevokeSerializer,
        responses={
            200: AdminCertificateSerializer,
            409: OpenApiResponse(description="Already revoked"),
            **ERRORS,
        },
        tags=["admin"],
    )
    def post(self, request: Request, certificate_id: UUID) -> Response:
        data = RevokeSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        certificates.revoke(
            actor=_actor(request),
            certificate_id=certificate_id,
            reason=data.validated_data["reason"],
            ip=_ip(request),
        )
        return Response(AdminCertificateSerializer(_row(_one(certificate_id))).data)


class ReissueCertificateView(APIView):
    policy = MANAGE

    @extend_schema(
        summary="Draw a certificate again with the template as it is now",
        description="The number stays the same. The name can be corrected at the same time. "
        "The member is told. Reissuing a revoked certificate makes it valid again.",
        request=ReissueSerializer,
        responses={200: AdminCertificateSerializer, **ERRORS},
        tags=["admin"],
    )
    def post(self, request: Request, certificate_id: UUID) -> Response:
        data = ReissueSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        certificates.reissue(
            actor=_actor(request),
            certificate_id=certificate_id,
            holder_name=data.validated_data.get("holder_name"),
            ip=_ip(request),
        )
        return Response(AdminCertificateSerializer(_row(_one(certificate_id))).data)
