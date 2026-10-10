from typing import Any
from uuid import UUID

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.adminconsole.views import _actor, _ip
from apps.core import policies
from apps.startups import services

FEATURE = policies.admin_permission("directory.feature")


class FeaturedSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    slug = serializers.CharField()
    featured = serializers.BooleanField()


def _body(startup: Any) -> dict[str, Any]:
    return {"id": startup.pk, "slug": startup.slug, "featured": startup.featured_at is not None}


ERRORS = {
    403: OpenApiResponse(description="Not allowed, or MFA missing"),
    404: OpenApiResponse(description="No such startup"),
    409: OpenApiResponse(description="Only listed startups can be featured"),
}


class FeatureStartupView(APIView):
    policy = FEATURE

    @extend_schema(
        summary="Pin a listed startup to the top of the directory",
        request=None,
        responses={200: FeaturedSerializer, **ERRORS},
        tags=["admin"],
    )
    def post(self, request: Request, startup_id: UUID) -> Response:
        startup = services.set_featured(
            actor=_actor(request), startup_id=startup_id, featured=True, ip=_ip(request)
        )
        return Response(FeaturedSerializer(_body(startup)).data)


class UnfeatureStartupView(APIView):
    policy = FEATURE

    @extend_schema(
        summary="Remove a startup's pin",
        request=None,
        responses={200: FeaturedSerializer, **ERRORS},
        tags=["admin"],
    )
    def post(self, request: Request, startup_id: UUID) -> Response:
        startup = services.set_featured(
            actor=_actor(request), startup_id=startup_id, featured=False, ip=_ip(request)
        )
        return Response(FeaturedSerializer(_body(startup)).data)
