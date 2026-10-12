from typing import cast
from uuid import UUID

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core import policies
from apps.core.serializers import StrictSerializer
from apps.globalsearch import services


class RecentsSerializer(serializers.Serializer):
    terms = serializers.ListField(child=serializers.CharField())


class RememberSerializer(StrictSerializer):
    term = serializers.CharField(min_length=2, max_length=100, trim_whitespace=True)
    scope = serializers.ChoiceField(choices=services.SCOPES, default="member")


class ScopeQuerySerializer(StrictSerializer):
    scope = serializers.ChoiceField(choices=services.SCOPES, default="member", required=False)


ERRORS = {401: OpenApiResponse(description="Not logged in")}


class RecentSearchesView(APIView):
    policy = policies.authenticated

    def _scope(self, request: Request) -> str:
        params = ScopeQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        return str(params.validated_data.get("scope", "member"))

    @extend_schema(
        summary="Your recent searches",
        parameters=[ScopeQuerySerializer],
        responses={200: RecentsSerializer, **ERRORS},
        tags=["search"],
    )
    def get(self, request: Request) -> Response:
        user_id = cast(UUID, request.user.pk)
        return Response({"terms": services.recents(user_id, self._scope(request))})

    @extend_schema(
        summary="Remember a search",
        description="Keeps the latest eight terms. A term already there moves to the top.",
        request=RememberSerializer,
        responses={
            200: RecentsSerializer,
            400: OpenApiResponse(description="Invalid term"),
            **ERRORS,
        },
        tags=["search"],
    )
    def post(self, request: Request) -> Response:
        data = RememberSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        user_id = cast(UUID, request.user.pk)
        terms = services.remember(
            user_id, data.validated_data["scope"], data.validated_data["term"]
        )
        return Response({"terms": terms})

    @extend_schema(
        summary="Clear your recent searches",
        parameters=[ScopeQuerySerializer],
        responses={204: OpenApiResponse(description="Cleared"), **ERRORS},
        tags=["search"],
    )
    def delete(self, request: Request) -> Response:
        services.clear(cast(UUID, request.user.pk), self._scope(request))
        return Response(status=status.HTTP_204_NO_CONTENT)
