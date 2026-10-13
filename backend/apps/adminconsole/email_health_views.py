"""Admin > Email: is mail trusted, how did recent sending go, and who is suppressed."""

from uuid import UUID

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import exceptions, serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.adminconsole.views import _actor, _ip
from apps.audit import services as audit
from apps.core import policies
from apps.core.pagination import AdminLimitOffsetPagination
from apps.core.serializers import StrictSerializer
from apps.notifications import deliverability, services
from apps.notifications.models import Suppression

VIEW = policies.admin_permission("email.health")
REMOVE = policies.admin_permission("email.suppression.manage", step_up=True)
ERRORS = {
    401: OpenApiResponse(description="Not authenticated"),
    403: OpenApiResponse(description="Not allowed, MFA missing, or step-up required"),
}


class DnsCheckSerializer(serializers.Serializer):
    key = serializers.CharField()
    title = serializers.CharField(source="label")
    status = serializers.ChoiceField(choices=["ok", "warning", "missing", "unknown"])
    detail = serializers.CharField()
    record = serializers.CharField(allow_blank=True)


class DomainHealthSerializer(serializers.Serializer):
    domain = serializers.CharField()
    stream = serializers.CharField()
    checks = DnsCheckSerializer(many=True)


class ConfiguredSerializer(serializers.Serializer):
    api_key = serializers.BooleanField()
    webhook_secret = serializers.BooleanField()
    reply_to = serializers.BooleanField()
    logo = serializers.BooleanField()


class SendingStatsSerializer(serializers.Serializer):
    days = serializers.IntegerField()
    sent = serializers.IntegerField()
    delivered = serializers.IntegerField()
    bounced = serializers.IntegerField()
    complained = serializers.IntegerField()
    unsubscribed = serializers.IntegerField()
    suppressed_total = serializers.IntegerField()


class FailureSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    kind = serializers.CharField()
    provider_message_id = serializers.CharField()
    occurred_at = serializers.CharField(allow_blank=True)
    created_at = serializers.DateTimeField()


class HealthSerializer(serializers.Serializer):
    provider = serializers.CharField()
    configured = ConfiguredSerializer()
    separate_streams = serializers.BooleanField()
    hourly_cap = serializers.IntegerField(allow_null=True)
    domains = DomainHealthSerializer(many=True)
    stats = SendingStatsSerializer()
    failures = FailureSerializer(many=True)


class SuppressionQuerySerializer(StrictSerializer):
    email = serializers.CharField(required=False, allow_blank=True, max_length=254, default="")
    limit = serializers.IntegerField(required=False, min_value=1, max_value=100)
    offset = serializers.IntegerField(required=False, min_value=0)


class SuppressionSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    reason = serializers.CharField()
    reference = serializers.SerializerMethodField(
        help_text="The first characters of the address hash"
    )
    created_at = serializers.DateTimeField()

    def get_reference(self, obj: Suppression) -> str:
        return str(obj.email_hash[:10])


class HealthView(APIView):
    policy = VIEW

    @extend_schema(
        summary="Email health: DNS records, sending results and recent failures",
        description="SPF, DKIM and DMARC are read from public DNS. Whether the provider has "
        "verified the domain, and the sender's reputation, cannot be seen from here.",
        responses={200: HealthSerializer, **ERRORS},
        tags=["admin"],
    )
    def get(self, request: Request) -> Response:
        data = deliverability.health()
        data["stats"] = deliverability.stats()
        data["failures"] = deliverability.recent_failures()
        return Response(HealthSerializer(data).data)


class SuppressionsView(APIView):
    policy = VIEW
    pagination_class = AdminLimitOffsetPagination

    @extend_schema(
        summary="Addresses we no longer send broadcasts to",
        description="Addresses are stored as hashes, so search with the full address.",
        parameters=[SuppressionQuerySerializer],
        responses={200: SuppressionSerializer(many=True), **ERRORS},
        tags=["admin"],
    )
    def get(self, request: Request) -> Response:
        params = SuppressionQuerySerializer(data=request.query_params.dict())
        params.is_valid(raise_exception=True)
        rows = Suppression.objects.order_by("-created_at")
        if params.validated_data["email"]:
            rows = rows.filter(email_hash=services.hash_email(params.validated_data["email"]))
        paginator = AdminLimitOffsetPagination()
        page = paginator.paginate_queryset(rows, request, view=self)
        return paginator.get_paginated_response(SuppressionSerializer(page, many=True).data)


class SuppressionView(APIView):
    policy = REMOVE

    @extend_schema(
        summary="Allow broadcasts to an address again",
        description="Super admin only, with a fresh two step check. Recorded in the audit log.",
        responses={204: None, **ERRORS, 404: OpenApiResponse(description="No such entry")},
        tags=["admin"],
    )
    def delete(self, request: Request, suppression_id: UUID) -> Response:
        row = Suppression.objects.filter(pk=suppression_id).first()
        if row is None:
            raise exceptions.NotFound()
        audit.record(
            actor=_actor(request),
            action="email.suppression_removed",
            target_type="suppression",
            target_id=row.pk,
            target_label=row.email_hash[:10],
            before={"reason": row.reason},
            ip=_ip(request),
        )
        row.delete()
        return Response(status=204)
