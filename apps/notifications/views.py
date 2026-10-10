from typing import Any

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import exceptions, serializers, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core import policies
from apps.integrations.email import get_email_adapter
from apps.notifications import services


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
