from uuid import UUID

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.toolkit.ventures import grants
from apps.toolkit.ventures.permissions import member_policy, owned_venture, uid

ERRORS = {
    401: OpenApiResponse(description="Not authenticated"),
    403: OpenApiResponse(description="Not an approved member"),
    404: OpenApiResponse(description="Not found, or not yours"),
}


class TkGrantSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    mentor_id = serializers.UUIDField()
    name = serializers.CharField(allow_blank=True)
    can_comment = serializers.BooleanField()
    expires_at = serializers.DateTimeField(allow_null=True)
    created_at = serializers.DateTimeField()


class TkGrantCreateSerializer(serializers.Serializer):
    mentor_id = serializers.UUIDField(help_text="The mentor's user id from the mentor directory")
    can_comment = serializers.BooleanField(required=False, default=False)
    expires_in_days = serializers.IntegerField(required=False, min_value=1, max_value=365)


class TkSharedVentureSerializer(serializers.Serializer):
    venture_id = serializers.UUIDField()
    name = serializers.CharField()
    can_comment = serializers.BooleanField()
    expires_at = serializers.DateTimeField(allow_null=True)
    shared_at = serializers.DateTimeField()


def _private(response: Response) -> Response:
    response["Cache-Control"] = "private, no-store"
    return response


class GrantsView(APIView):
    policy = member_policy()

    @extend_schema(
        summary="Who can read this venture",
        responses={200: TkGrantSerializer(many=True), **ERRORS},
        tags=["toolkit"],
    )
    def get(self, request: Request, venture_id: UUID) -> Response:
        venture = owned_venture(request, venture_id)
        return _private(Response(TkGrantSerializer(grants.given(venture), many=True).data))

    @extend_schema(
        summary="Let a mentor read this venture",
        description="Read only: the mentor sees what you see (profile, score, plan, forecast, "
        "decks) and can change nothing. Revoke at any time. Only listed mentors can be chosen.",
        request=TkGrantCreateSerializer,
        responses={201: TkGrantSerializer, **ERRORS},
        tags=["toolkit"],
    )
    def post(self, request: Request, venture_id: UUID) -> Response:
        venture = owned_venture(request, venture_id)
        body = TkGrantCreateSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        row = grants.grant(
            venture=venture,
            owner_id=uid(request),
            mentor_id=body.validated_data["mentor_id"],
            can_comment=body.validated_data.get("can_comment", False),
            expires_in_days=body.validated_data.get("expires_in_days"),
        )
        shown = next(g for g in grants.given(venture) if g["id"] == row.pk)
        return _private(Response(TkGrantSerializer(shown).data, status=201))


class GrantView(APIView):
    policy = member_policy()

    @extend_schema(
        summary="Take access back",
        request=None,
        responses={204: OpenApiResponse(description="Revoked"), **ERRORS},
        tags=["toolkit"],
    )
    def delete(self, request: Request, venture_id: UUID, grant_id: UUID) -> Response:
        venture = owned_venture(request, venture_id)
        grants.revoke(venture=venture, grant_id=grant_id)
        return Response(status=204)


class SharedWithMeView(APIView):
    policy = member_policy()

    @extend_schema(
        summary="Ventures shared with you",
        description="For a mentor: founders who gave you read access. Open one with the usual "
        "read endpoints (`profile`, `score/latest`, `plan`, ...); writes are refused.",
        responses={200: TkSharedVentureSerializer(many=True), **ERRORS},
        tags=["toolkit"],
    )
    def get(self, request: Request) -> Response:
        return _private(
            Response(TkSharedVentureSerializer(grants.shared_with(uid(request)), many=True).data)
        )
