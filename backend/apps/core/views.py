import uuid

from django.core.cache import cache
from django.db import connection
from django.http import Http404, HttpResponse
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


class HealthView(_PublicView):
    """The one address a platform health check needs: is the database up, and is Redis."""

    # A platform probe, not part of the public API description.
    @extend_schema(exclude=True)
    def get(self, request: Request) -> Response:
        database = redis = "ok"
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
        except Exception:
            database = "unavailable"
        try:
            key = f"health:{uuid.uuid4().hex}"
            cache.set(key, "1", 5)
            if cache.get(key) != "1":
                raise RuntimeError("cache round trip failed")
        except Exception:
            redis = "unavailable"
        healthy = database == "ok" and redis == "ok"
        return Response(
            {"status": "ok" if healthy else "unavailable", "database": database, "redis": redis},
            status=status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE,
        )


class PingView(_PublicView):
    throttle_classes = _PublicView.throttle_classes

    @extend_schema(summary="API availability check", responses=PingSerializer, tags=["health"])
    def get(self, request: Request) -> Response:
        from django.conf import settings

        return Response({"status": "ok", "release": settings.RELEASE})


class SchemaView(SpectacularAPIView):
    policy = policies.public
    authentication_classes: list = []


class MetricsView(_PublicView):
    """Prometheus scrape endpoint. 404 unless METRICS_TOKEN is set, then bearer token only."""

    @extend_schema(exclude=True)
    def get(self, request: Request) -> HttpResponse:
        import hmac

        from django.conf import settings

        from apps.core import metrics

        token = settings.METRICS_TOKEN
        if not token:
            raise Http404
        supplied = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
        if not hmac.compare_digest(supplied.encode(), token.encode()):
            return HttpResponse(status=401, headers={"WWW-Authenticate": "Bearer"})
        response = HttpResponse(metrics.render(), content_type=metrics.CONTENT_TYPE)
        response["Cache-Control"] = "no-store"
        return response
