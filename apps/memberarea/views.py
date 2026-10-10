from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle, UserRateThrottle
from rest_framework.views import APIView

from apps.core import policies
from apps.core.serializers import StrictSerializer
from apps.memberarea import onboarding, search


class ChecklistItemSerializer(serializers.Serializer):
    key = serializers.CharField()
    done = serializers.BooleanField()


class CompletenessSerializer(serializers.Serializer):
    score = serializers.IntegerField()
    next_missing_field = serializers.CharField(allow_null=True)


class OnboardingSerializer(serializers.Serializer):
    items = ChecklistItemSerializer(many=True)
    complete = serializers.BooleanField()
    profile_completeness = CompletenessSerializer()


class OnboardingView(APIView):
    policy = policies.authenticated

    @extend_schema(
        summary="Your onboarding checklist",
        description="Complete the profile (score of 80 or more), add a startup, add traction, "
        "and save your notification preferences. Calculated from your data on each call.",
        responses={200: OnboardingSerializer, 401: OpenApiResponse(description="Not logged in")},
        tags=["member area"],
    )
    def get(self, request: Request) -> Response:
        return Response(OnboardingSerializer(onboarding.checklist(request.user)).data)


class SearchQuerySerializer(StrictSerializer):
    q = serializers.CharField(min_length=2, max_length=100, trim_whitespace=True)
    types = serializers.CharField(required=False, allow_blank=True, default="", max_length=100)
    limit = serializers.IntegerField(required=False, min_value=1, max_value=20, default=10)

    def validate_types(self, value: str) -> list[str]:
        kinds = [part.strip() for part in value.split(",") if part.strip()]
        unknown = sorted(set(kinds) - set(search.SEARCHERS))
        if unknown:
            raise serializers.ValidationError(f"Unknown type: {', '.join(unknown)}.")
        return kinds or list(search.SEARCHERS)


class SearchHitSerializer(serializers.Serializer):
    type = serializers.CharField()
    id = serializers.UUIDField()
    slug = serializers.CharField()
    title = serializers.CharField()
    subtitle = serializers.CharField(allow_blank=True)
    image = serializers.DictField(allow_null=True)


class SearchResultSerializer(serializers.Serializer):
    members = SearchHitSerializer(many=True, required=False)
    startups = SearchHitSerializer(many=True, required=False)


class SearchView(APIView):
    policy = policies.active_member
    throttle_classes = [UserRateThrottle, ScopedRateThrottle]
    throttle_scope = "search"

    @extend_schema(
        summary="Search members and startups",
        description="Results are what you may see of each item: someone who hides their basics "
        "from members cannot be found. Tolerates small typos. Jobs, courses and the rest join "
        "as their areas are built.",
        parameters=[
            OpenApiParameter("q", str, required=True, description="2 to 100 characters"),
            OpenApiParameter("types", str, description="Comma list: members, startups"),
            OpenApiParameter("limit", int, description="Per type, 1 to 20 (default 10)"),
        ],
        responses={
            200: SearchResultSerializer,
            400: OpenApiResponse(description="Invalid query"),
            401: OpenApiResponse(description="Not logged in"),
            403: OpenApiResponse(description="Not an active member"),
            429: OpenApiResponse(description="Too many searches"),
        },
        tags=["member area"],
    )
    def get(self, request: Request) -> Response:
        params = SearchQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        data = params.validated_data
        found = search.search(request.user, data["q"], data["types"], data["limit"])
        response = Response(SearchResultSerializer(found).data)
        response["Cache-Control"] = "private, no-store"
        return response
