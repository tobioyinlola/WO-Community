import uuid

from django.core.cache import cache
from django.db import connection
from drf_spectacular.utils import extend_schema
from drf_spectacular.views import SpectacularAPIView
from rest_framework import serializers, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core import policies


class StatusSerializer(serializers.Serializer):
    status = serializers.CharField()


class PingSerializer(serializers.Serializer):
    status = serializers.CharField()
    release = serializers.CharField()


class _PublicView(APIView):
    policy = policies.public
    authentication_classes: list = []
    throttle_classes: list = []


class HealthLiveView(_PublicView):
    @extend_schema(summary="Liveness probe", responses=StatusSerializer, tags=["health"])
    def get(self, request: Request) -> Response:
        return Response({"status": "ok"})


class HealthReadyView(_PublicView):
    @extend_schema(
        summary="Readiness probe: database and cache reachable",
        responses={200: StatusSerializer, 503: StatusSerializer},
        tags=["health"],
    )
    def get(self, request: Request) -> Response:
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            key = f"ready:{uuid.uuid4().hex}"
            cache.set(key, "1", 5)
            if cache.get(key) != "1":
                raise RuntimeError("cache round trip failed")
        except Exception:
            return Response({"status": "unavailable"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response({"status": "ok"})


class PingView(_PublicView):
    throttle_classes = _PublicView.throttle_classes

    @extend_schema(summary="API availability check", responses=PingSerializer, tags=["health"])
    def get(self, request: Request) -> Response:
        from django.conf import settings

        return Response({"status": "ok", "release": settings.RELEASE})


class SchemaView(SpectacularAPIView):
    policy = policies.public
    authentication_classes: list = []
