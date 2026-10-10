from typing import Any, cast
from uuid import UUID

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import exceptions, serializers, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core import policies
from apps.core.serializers import StrictSerializer
from apps.integrations.email import get_email_adapter
from apps.notifications import preferences, services


class InvalidSignature(exceptions.APIException):
    # Not AuthenticationFailed: DRF turns that into a 403 on views with no authenticators.
    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = "Invalid signature."
    default_code = "invalid_signature"


class WebhookAckSerializer(serializers.Serializer):
    status = serializers.CharField()


class EmailWebhookView(APIView):
    """Delivery reports from the email provider.

    Open to the internet but guarded by the provider's signature, which is
    checked against the exact bytes received before anything is parsed. It is
    not rate limited: the provider decides its own volume.
    """

    policy = policies.public
    authentication_classes: list[Any] = []
    throttle_classes: list[Any] = []
    parser_classes: list[Any] = []  # the body is read raw; it must not be consumed by a parser

    @extend_schema(
        summary="Receive an email delivery report",
        description="Called by the email provider. The signature headers are required.",
        request=None,
        responses={
            200: WebhookAckSerializer,
            401: OpenApiResponse(description="Signature missing or wrong"),
            404: OpenApiResponse(description="Not the configured provider"),
        },
        tags=["webhooks"],
    )
    def post(self, request: Request, provider: str) -> Response:
        adapter = get_email_adapter()
        if provider != adapter.provider_name:
            raise exceptions.NotFound()
        headers = {name.lower(): value for name, value in request.headers.items()}
        try:
            fresh = services.accept_webhook(adapter, request.body, headers)
        except services.InvalidWebhook as exc:
            if str(exc) == "signature":
                raise InvalidSignature() from exc
            raise exceptions.ParseError("Malformed delivery.") from exc
        return Response({"status": "accepted" if fresh else "duplicate"}, status=status.HTTP_200_OK)


class PreferencesSerializer(serializers.Serializer):
    preferences = serializers.DictField(
        child=serializers.DictField(child=serializers.BooleanField())
    )
    confirmed = serializers.BooleanField()


class PreferencesUpdateSerializer(StrictSerializer):
    preferences = serializers.DictField(
        child=serializers.DictField(child=serializers.BooleanField(), allow_empty=False),
        allow_empty=True,
    )


class NotificationPreferencesView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="Your notification preferences",
        description="Every type and channel with its current value. `confirmed` turns true once "
        "you have saved your choices.",
        responses={200: PreferencesSerializer, 401: OpenApiResponse(description="Not logged in")},
        tags=["notifications"],
    )
    def get(self, request: Request) -> Response:
        matrix, confirmed = preferences.get(cast(UUID, request.user.pk))
        return Response({"preferences": matrix, "confirmed": confirmed})

    @extend_schema(
        summary="Change your notification preferences",
        description="Send only what changes, as `{type: {channel: true|false}}`. Saving an empty "
        "object confirms the defaults.",
        request=PreferencesUpdateSerializer,
        responses={
            200: PreferencesSerializer,
            400: OpenApiResponse(description="Unknown type or channel, or a locked message"),
            401: OpenApiResponse(description="Not logged in"),
        },
        tags=["notifications"],
    )
    def put(self, request: Request) -> Response:
        serializer = PreferencesUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            matrix = preferences.update(
                cast(UUID, request.user.pk), serializer.validated_data["preferences"]
            )
        except preferences.InvalidPreferences as invalid:
            raise exceptions.ValidationError(invalid.errors) from None
        return Response({"preferences": matrix, "confirmed": True})
