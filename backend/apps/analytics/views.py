from typing import Any, cast
from uuid import UUID

from django.conf import settings
from django.utils.module_loading import import_string
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, ScopedRateThrottle
from rest_framework.views import APIView

from apps.analytics import registry, services
from apps.analytics.serializers import (
    BatchResultSerializer,
    EventBatchSerializer,
    PreferenceSerializer,
)
from apps.core import policies


class EventIngestView(APIView):
    """Events only the browser can see: page views and clicks.

    Anyone may call it, signed in or not. The caller's identity comes from an
    optional login resolved through settings (a bad or expired token is treated
    as an anonymous visitor rather than an error, so a tracking call can never
    fail a page).
    """

    policy = policies.public
    authentication_classes = [import_string(path) for path in settings.ANALYTICS_AUTHENTICATION]
    throttle_classes = [AnonRateThrottle, ScopedRateThrottle]
    throttle_scope = "analytics"

    @extend_schema(
        summary="Report browser events",
        description="Up to 50 events per call. Only events marked as browser events in the "
        "registry are accepted, with only their listed properties. Invalid events are reported "
        "individually and the rest are kept. Send the visitor's `anonymous_id` only if they "
        "agreed to analytics; when signed in it is linked to the member.",
        request=EventBatchSerializer,
        responses={202: BatchResultSerializer, 400: OpenApiResponse(description="Malformed batch")},
        tags=["analytics"],
    )
    def post(self, request: Request) -> Response:
        serializer = EventBatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        anonymous_id: UUID | None = data["anonymous_id"]
        actor_id = cast(UUID, request.user.pk) if request.user.is_authenticated else None
        if actor_id is not None and anonymous_id is not None:
            services.identify(anonymous_id, actor_id)

        accepted = 0
        rejected: list[dict[str, Any]] = []
        for index, item in enumerate(data["events"]):
            try:
                registry.validate(item["name"], item["properties"], from_client=True)
            except registry.InvalidEvent as exc:
                rejected.append({"index": index, "reason": str(exc)})
                continue
            services.track(
                item["name"],
                actor_id=actor_id,
                anonymous_id=anonymous_id,
                properties=item["properties"],
                source="client",
                occurred_at=item.get("occurred_at"),
            )
            accepted += 1
        return Response(
            BatchResultSerializer({"accepted": accepted, "rejected": rejected}).data,
            status=status.HTTP_202_ACCEPTED,
        )


class MyPreferenceView(APIView):
    policy = policies.authenticated

    @extend_schema(
        summary="Whether you are left out of analytics",
        responses={200: PreferenceSerializer},
        tags=["analytics"],
    )
    def get(self, request: Request) -> Response:
        return Response({"opt_out": services.is_opted_out(cast(UUID, request.user.pk))})

    @extend_schema(
        summary="Leave analytics, or rejoin",
        description="While opted out nothing about you is recorded, by the browser or the server.",
        request=PreferenceSerializer,
        responses={200: PreferenceSerializer},
        tags=["analytics"],
    )
    def put(self, request: Request) -> Response:
        serializer = PreferenceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.set_opt_out(cast(UUID, request.user.pk), serializer.validated_data["opt_out"])
        return Response({"opt_out": serializer.validated_data["opt_out"]})
