from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle, UserRateThrottle
from rest_framework.views import APIView

from apps.adminconsole import search
from apps.core import policies
from apps.core.serializers import StrictSerializer


class AdminSearchQuerySerializer(StrictSerializer):
    q = serializers.CharField(min_length=2, max_length=100, trim_whitespace=True)
    types = serializers.CharField(required=False, allow_blank=True, default="", max_length=100)
    limit = serializers.IntegerField(required=False, min_value=1, max_value=20, default=6)

    def validate_types(self, value: str) -> list[str]:
        kinds = [part.strip() for part in value.split(",") if part.strip()]
        unknown = sorted(set(kinds) - set(search.GROUPS) - set(search.EXTRA_GROUPS))
        if unknown:
            raise serializers.ValidationError(f"Unknown type: {', '.join(unknown)}.")
        return kinds


class AdminHitSerializer(serializers.Serializer):
    type = serializers.CharField()
    id = serializers.UUIDField()
    title = serializers.CharField()
    subtitle = serializers.CharField(allow_blank=True)
    status = serializers.CharField(allow_blank=True)
    url = serializers.CharField(help_text="Path in the console")


class AdminSearchResultSerializer(serializers.Serializer):
    members = AdminHitSerializer(many=True, required=False)
    approvals = AdminHitSerializer(many=True, required=False)
    courses = AdminHitSerializer(many=True, required=False)
    jobs = AdminHitSerializer(many=True, required=False)
    events = AdminHitSerializer(many=True, required=False)
    ventures = AdminHitSerializer(many=True, required=False)
    tickets = AdminHitSerializer(many=True, required=False)


class AdminSearchView(APIView):
    policy = policies.admin_permission("admin.access")
    throttle_classes = [UserRateThrottle, ScopedRateThrottle]
    throttle_scope = "search"

    @extend_schema(
        summary="Search the console",
        description="Members (pending ones too), approvals, courses, jobs, events, ventures and "
        "support tickets. A group is left out when the role does not hold its permission.",
        parameters=[AdminSearchQuerySerializer],
        responses={
            200: AdminSearchResultSerializer,
            400: OpenApiResponse(description="Invalid query"),
            401: OpenApiResponse(description="Not authenticated"),
            403: OpenApiResponse(description="Not allowed, or MFA missing"),
            429: OpenApiResponse(description="Too many searches"),
        },
        tags=["admin"],
    )
    def get(self, request: Request) -> Response:
        params = AdminSearchQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        data = params.validated_data
        found = search.search(request.user, data["q"], data["types"], data["limit"])
        response = Response(AdminSearchResultSerializer(found).data)
        response["Cache-Control"] = "private, no-store"
        return response
