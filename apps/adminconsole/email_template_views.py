"""Admin > Email templates: read the wording, edit it, preview it and send a test."""

from typing import Any

from django.utils import timezone
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import exceptions, serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.adminconsole.views import _actor, _ip
from apps.core import policies
from apps.core.serializers import StrictSerializer
from apps.notifications import emails, templatestore
from apps.notifications import mailtemplates as mt
from apps.notifications.models import EmailTemplateVersion

MANAGE = policies.admin_permission("email.templates.manage")
ERRORS = {
    401: OpenApiResponse(description="Not authenticated"),
    403: OpenApiResponse(description="Not allowed, or MFA missing"),
    404: OpenApiResponse(description="No such template"),
}


class TemplateSummarySerializer(serializers.Serializer):
    key = serializers.CharField()
    name = serializers.CharField()
    about = serializers.CharField()
    stream = serializers.ChoiceField(choices=["transactional", "broadcast"])
    subject = serializers.CharField()
    edited = serializers.BooleanField()
    version = serializers.IntegerField()
    updated_at = serializers.DateTimeField(allow_null=True)


class TemplateVariableSerializer(serializers.Serializer):
    name = serializers.CharField()
    kind = serializers.CharField()
    is_required = serializers.BooleanField(source="required")
    must_appear = serializers.BooleanField()
    sample = serializers.CharField(allow_blank=True)


class TemplateSerializer(TemplateSummarySerializer):
    preheader = serializers.CharField(allow_blank=True)
    body = serializers.CharField()
    default_subject = serializers.CharField()
    default_preheader = serializers.CharField(allow_blank=True)
    default_body = serializers.CharField()
    variables = TemplateVariableSerializer(many=True)


class CopySerializer(StrictSerializer):
    subject = serializers.CharField(max_length=200)
    preheader = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    body = serializers.CharField(max_length=5000, trim_whitespace=False)
    note = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")


class PreviewRequestSerializer(StrictSerializer):
    subject = serializers.CharField(max_length=200, required=False)
    preheader = serializers.CharField(max_length=200, required=False, allow_blank=True)
    body = serializers.CharField(max_length=5000, required=False, trim_whitespace=False)


class PreviewSerializer(serializers.Serializer):
    subject = serializers.CharField()
    preheader = serializers.CharField(allow_blank=True)
    html = serializers.CharField()
    text = serializers.CharField()


class VersionSerializer(serializers.Serializer):
    version = serializers.IntegerField()
    subject = serializers.CharField()
    preheader = serializers.CharField(allow_blank=True)
    body = serializers.CharField()
    note = serializers.CharField(allow_blank=True)
    created_at = serializers.DateTimeField()
    saved_by = serializers.UUIDField(source="saved_by_id", allow_null=True)


class RestoreSerializer(StrictSerializer):
    version = serializers.IntegerField(min_value=1)


def _draft(key: str, data: dict[str, Any]) -> mt.Copy:
    """The saved wording with any fields in the request laid over it."""
    current = templatestore.effective_copy(key)
    return mt.Copy(
        data.get("subject", current.subject),
        data.get("preheader", current.preheader),
        data.get("body", current.body),
    )


def _render_draft(key: str, copy: mt.Copy) -> mt.Rendered:
    tpl = mt.TEMPLATES[key]
    try:
        mt.check_copy(tpl, copy.subject, copy.preheader, copy.body)
        return mt.render(
            key,
            tpl.sample(),
            copy=copy,
            unsubscribe_url="https://example.com/unsubscribe" if tpl.stream == "broadcast" else "",
            preferences_url="" if tpl.stream == "broadcast" else emails.preferences_url(),
        )
    except mt.TemplateError as exc:
        raise exceptions.ValidationError({"body": [str(exc)]}) from exc


class TemplatesView(APIView):
    policy = MANAGE

    @extend_schema(
        summary="Every email template",
        responses={200: TemplateSummarySerializer(many=True), **ERRORS},
        tags=["admin"],
    )
    def get(self, request: Request) -> Response:
        return Response(TemplateSummarySerializer(templatestore.list_all(), many=True).data)


class TemplateView(APIView):
    policy = MANAGE

    @extend_schema(
        summary="One template with its wording and variables",
        responses={200: TemplateSerializer, **ERRORS},
        tags=["admin"],
    )
    def get(self, request: Request, key: str) -> Response:
        return Response(TemplateSerializer(templatestore.describe(key)).data)

    @extend_schema(
        summary="Change the wording of a template",
        description="Only the subject, preview text and body are editable; the layout and brand "
        "are fixed. The previous wording stays in the history.",
        request=CopySerializer,
        responses={200: TemplateSerializer, **ERRORS},
        tags=["admin"],
    )
    def put(self, request: Request, key: str) -> Response:
        serializer = CopySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        templatestore.save(
            actor=_actor(request), key=key, ip=_ip(request), **serializer.validated_data
        )
        return Response(TemplateSerializer(templatestore.describe(key)).data)


class PreviewView(APIView):
    policy = MANAGE

    @extend_schema(
        summary="Preview a template with sample data",
        description="Send a draft to see it without saving. The same HTML serves the desktop and "
        "the mobile view; the layout adapts at 620 px.",
        request=PreviewRequestSerializer,
        responses={
            200: PreviewSerializer,
            400: OpenApiResponse(description="Bad wording"),
            **ERRORS,
        },
        tags=["admin"],
    )
    def post(self, request: Request, key: str) -> Response:
        templatestore.describe(key)  # 404 for an unknown key
        serializer = PreviewRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        rendered = _render_draft(key, _draft(key, serializer.validated_data))
        return Response(PreviewSerializer(rendered.__dict__).data)


class SendTestView(APIView):
    policy = MANAGE

    @extend_schema(
        summary="Send a test of a template to yourself",
        request=PreviewRequestSerializer,
        responses={204: None, 400: OpenApiResponse(description="Bad wording"), **ERRORS},
        tags=["admin"],
    )
    def post(self, request: Request, key: str) -> Response:
        templatestore.describe(key)
        serializer = PreviewRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        rendered = _render_draft(key, _draft(key, serializer.validated_data))
        actor = _actor(request)
        emails.send_rendered(
            actor.email,
            rendered,
            category="template_test",
            subject_prefix="[Test] ",
            nonce=timezone.now().isoformat(),
        )
        return Response(status=204)


class VersionsView(APIView):
    policy = MANAGE

    @extend_schema(
        summary="The history of a template's wording",
        responses={200: VersionSerializer(many=True), **ERRORS},
        tags=["admin"],
    )
    def get(self, request: Request, key: str) -> Response:
        rows: list[EmailTemplateVersion] = templatestore.versions(key)
        return Response(VersionSerializer(rows, many=True).data)


class RestoreView(APIView):
    policy = MANAGE

    @extend_schema(
        summary="Put an earlier wording back",
        request=RestoreSerializer,
        responses={200: TemplateSerializer, **ERRORS},
        tags=["admin"],
    )
    def post(self, request: Request, key: str) -> Response:
        serializer = RestoreSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        templatestore.restore(
            actor=_actor(request),
            key=key,
            version=serializer.validated_data["version"],
            ip=_ip(request),
        )
        return Response(TemplateSerializer(templatestore.describe(key)).data)


class ResetView(APIView):
    policy = MANAGE

    @extend_schema(
        summary="Go back to the built in wording",
        request=None,
        responses={200: TemplateSerializer, **ERRORS},
        tags=["admin"],
    )
    def post(self, request: Request, key: str) -> Response:
        templatestore.reset(actor=_actor(request), key=key, ip=_ip(request))
        return Response(TemplateSerializer(templatestore.describe(key)).data)
