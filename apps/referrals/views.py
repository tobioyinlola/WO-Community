from typing import cast

from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.core import policies
from apps.core.serializers import StrictSerializer
from apps.referrals import selectors


class ReferrerSearchQuerySerializer(StrictSerializer):
    q = serializers.CharField(max_length=100, trim_whitespace=True)


class ReferrerCandidateSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    headline = serializers.CharField(allow_blank=True)
    photo = serializers.DictField(allow_null=True)
    startup = serializers.CharField(allow_blank=True)


class ReferrerSearchSerializer(serializers.Serializer):
    results = ReferrerCandidateSerializer(many=True)


class ReferralEntrySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    startup = serializers.CharField(allow_blank=True)
    joined_at = serializers.DateTimeField()


class MyReferralsSerializer(serializers.Serializer):
    code = serializers.CharField()
    url = serializers.CharField(help_text="The link to share. It opens the sign up page.")
    approved_count = serializers.IntegerField()
    waiting_count = serializers.IntegerField()
    members = ReferralEntrySerializer(many=True)


class ReferrerSearchView(APIView):
    """Open to people signing up, so it is narrow and throttled by address."""

    policy = policies.public
    authentication_classes: list = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "referrer_search"

    @extend_schema(
        summary="Find the member who told you about us",
        description="For the sign up form. Needs at least three characters and answers with at "
        "most five people: members whose name is public, found by name or by their email address "
        "typed in full. Throttled by address.",
        parameters=[OpenApiParameter("q", str, required=True, description="3 to 100 characters")],
        responses={
            200: ReferrerSearchSerializer,
            400: OpenApiResponse(description="Invalid query"),
            429: OpenApiResponse(description="Too many searches"),
        },
        tags=["referrals"],
    )
    def get(self, request: Request) -> Response:
        params = ReferrerSearchQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        found = selectors.search_referrers(params.validated_data["q"])
        response = Response({"results": found})
        response["Cache-Control"] = "private, no-store"
        return response


class MyReferralsView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="Your referral link and the members who joined through you",
        description="Shows only people who have been approved, and only what each of them allows "
        "you to see.",
        responses={
            200: MyReferralsSerializer,
            401: OpenApiResponse(description="Not logged in"),
            403: OpenApiResponse(description="Not an active member"),
        },
        tags=["referrals"],
    )
    def get(self, request: Request) -> Response:
        return Response(
            MyReferralsSerializer(selectors.my_referrals(cast(User, request.user))).data
        )


class ReferrerByCodeQuerySerializer(StrictSerializer):
    code = serializers.CharField(max_length=12, trim_whitespace=True)


class ReferrerByCodeSerializer(serializers.Serializer):
    found = serializers.BooleanField()
    id = serializers.UUIDField(allow_null=True)
    name = serializers.CharField(allow_blank=True)
    startup = serializers.CharField(allow_blank=True)
    photo = serializers.DictField(allow_null=True)


class ReferrerByCodeView(APIView):
    """Lets the sign up form say who a referral link came from."""

    policy = policies.public
    authentication_classes: list = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "referrer_search"

    @extend_schema(
        summary="Who a referral link belongs to",
        description="For the sign up form after someone opens a link. `found` is false for a "
        "code that belongs to nobody active. A member who keeps their name from visitors is "
        "found, without a name. Throttled by address.",
        parameters=[OpenApiParameter("code", str, required=True)],
        responses={
            200: ReferrerByCodeSerializer,
            400: OpenApiResponse(description="Missing or too long"),
            429: OpenApiResponse(description="Too many lookups"),
        },
        tags=["referrals"],
    )
    def get(self, request: Request) -> Response:
        params = ReferrerByCodeQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        response = Response(selectors.referrer_for_link(params.validated_data["code"]))
        response["Cache-Control"] = "private, no-store"
        return response
