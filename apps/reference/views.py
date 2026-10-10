from typing import Any

from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core import policies
from apps.reference import selectors

CACHE_CONTROL = "public, max-age=3600"


class ItemSerializer(serializers.Serializer):
    slug = serializers.CharField()
    name = serializers.CharField()


class CountrySerializer(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()


class _ReferenceView(APIView):
    policy = policies.public
    authentication_classes: list[Any] = []

    def respond(self, data: Any) -> Response:
        response = Response(data)
        response["Cache-Control"] = CACHE_CONTROL
        return response


class SectorListView(_ReferenceView):
    @extend_schema(
        summary="Sectors",
        responses=ItemSerializer(many=True),
        tags=["reference"],
        operation_id="reference_sectors",
    )
    def get(self, request: Request) -> Response:
        return self.respond(ItemSerializer(selectors.sectors(), many=True).data)


class StageListView(_ReferenceView):
    @extend_schema(
        summary="Startup stages",
        responses=ItemSerializer(many=True),
        tags=["reference"],
        operation_id="reference_stages",
    )
    def get(self, request: Request) -> Response:
        return self.respond(ItemSerializer(selectors.stages(), many=True).data)


class SkillListView(_ReferenceView):
    @extend_schema(
        summary="Skills",
        responses=ItemSerializer(many=True),
        tags=["reference"],
        operation_id="reference_skills",
    )
    def get(self, request: Request) -> Response:
        return self.respond(ItemSerializer(selectors.skills(), many=True).data)


class CountryListView(_ReferenceView):
    @extend_schema(
        summary="Countries (ISO 3166-1 alpha-2)",
        responses=CountrySerializer(many=True),
        tags=["reference"],
        operation_id="reference_countries",
    )
    def get(self, request: Request) -> Response:
        return self.respond(CountrySerializer(selectors.countries(), many=True).data)
