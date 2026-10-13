from typing import cast
from uuid import UUID

from django.db import transaction
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import exceptions, serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import referrals as accounts_referrals
from apps.accounts import selectors as accounts
from apps.accounts.models import User
from apps.adminconsole import selectors as queues
from apps.adminconsole.serializers import ApplicantReferralSerializer
from apps.audit import services as audit
from apps.core import policies
from apps.core.serializers import StrictSerializer
from apps.referrals import selectors

ERRORS = {
    401: OpenApiResponse(description="Not authenticated"),
    403: OpenApiResponse(description="Not allowed, or MFA missing"),
}


class WindowSerializer(serializers.Serializer):
    signups = serializers.IntegerField()
    referred = serializers.IntegerField()
    approved = serializers.IntegerField()


class SourceCountSerializer(serializers.Serializer):
    kind = serializers.CharField()
    kind_label = serializers.CharField()
    count = serializers.IntegerField()


class ReferralSummarySerializer(serializers.Serializer):
    this_month = WindowSerializer()
    last_month = WindowSerializer()
    referred_share = serializers.IntegerField(
        help_text="Percent of this month's sign ups that were referred"
    )
    sources = SourceCountSerializer(many=True)


class TopReferrerSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    approved = serializers.IntegerField()


class TopQuerySerializer(StrictSerializer):
    limit = serializers.IntegerField(required=False, min_value=1, max_value=50, default=10)


class ReferralEditSerializer(StrictSerializer):
    kind = serializers.ChoiceField(
        choices=accounts_referrals.SOURCES, required=False, allow_blank=True
    )
    detail = serializers.CharField(
        required=False, allow_blank=True, max_length=accounts_referrals.DETAIL_MAX
    )
    referred_by = serializers.UUIDField(required=False, allow_null=True)


class ReferralSummaryView(APIView):
    policy = policies.admin_permission("dashboard.view")

    @extend_schema(
        summary="Referrals this month against last month",
        description="Sign ups, how many named a member, and where people say they heard of us.",
        responses={200: ReferralSummarySerializer, **ERRORS},
        tags=["admin"],
    )
    def get(self, request: Request) -> Response:
        return Response(ReferralSummarySerializer(selectors.summary()).data)


class TopReferrersView(APIView):
    policy = policies.admin_permission("dashboard.view")

    @extend_schema(
        summary="Members with the most approved referrals",
        parameters=[TopQuerySerializer],
        responses={200: TopReferrerSerializer(many=True), **ERRORS},
        tags=["admin"],
    )
    def get(self, request: Request) -> Response:
        params = TopQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        return Response(
            TopReferrerSerializer(
                selectors.top_referrers(params.validated_data["limit"]), many=True
            ).data
        )


class MemberReferralView(APIView):
    policy = policies.admin_permission("members.approve")

    @extend_schema(
        summary="Correct how someone says they heard of us",
        description="An admin can change the source, the detail and the referring member. "
        "A member cannot be their own referrer.",
        parameters=[OpenApiParameter("user_id", str, OpenApiParameter.PATH)],
        request=ReferralEditSerializer,
        responses={
            200: ApplicantReferralSerializer,
            400: OpenApiResponse(description="Invalid"),
            404: OpenApiResponse(description="Member not found"),
            **ERRORS,
        },
        tags=["admin"],
    )
    def patch(self, request: Request, user_id: UUID) -> Response:
        data = ReferralEditSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        member = accounts.get_member(user_id)
        if member is None:
            raise exceptions.NotFound()
        values = data.validated_data
        merged = {
            "kind": values.get("kind", member.referral_source),
            "detail": values.get("detail", member.referral_detail),
            "referred_by": (
                values["referred_by"] if "referred_by" in values else member.referred_by_id
            ),
            "code": member.referral_code_used,
        }
        if merged["kind"] != "member":  # only "a member" can name a member
            merged["referred_by"] = None
        before = {"source": member.referral_source, "referrer": str(member.referred_by_id or "")}
        with transaction.atomic():
            fields = accounts_referrals.clean(merged, own_id=member.pk)
            for name, value in fields.items():
                setattr(member, name, value)
            member.save(update_fields=[*fields, "updated_at"])
            audit.record(
                actor=cast(User, request.user),
                action="member.referral_edited",
                target_type="user",
                target_id=member.pk,
                before=before,
                after={
                    "source": member.referral_source,
                    "referrer": str(member.referred_by_id or ""),
                },
            )
        return Response(ApplicantReferralSerializer(queues.application_of(member)["referral"]).data)
