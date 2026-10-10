from typing import cast

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, BaseThrottle, ScopedRateThrottle
from rest_framework.views import APIView

from apps.campaigns import services
from apps.campaigns.serializers import UnsubscribeResultSerializer, UnsubscribeSerializer
from apps.core import policies


class UnsubscribeView(APIView):
    """One-click unsubscribe, reachable from the link in every marketing email.

    Open to the internet but guarded by a signed token that only we can make, so it cannot be used
    to unsubscribe someone else. Mail clients call it with POST (RFC 8058); the web page the link
    opens calls the same endpoint.
    """

    policy = policies.public
    authentication_classes: list[type] = []
    throttle_classes = [AnonRateThrottle, ScopedRateThrottle]
    throttle_scope = "auth_token"

    @extend_schema(
        summary="Unsubscribe from marketing email",
        description="Takes effect immediately: marketing consent is withdrawn and the address is "
        "suppressed. Send the token as JSON, or in the query string as mail clients do. Safe to "
        "repeat. Transactional email (password resets, approvals) is not affected.",
        request=UnsubscribeSerializer,
        responses={
            200: UnsubscribeResultSerializer,
            400: OpenApiResponse(description="Invalid link"),
        },
        tags=["campaigns"],
    )
    def post(self, request: Request) -> Response:
        data = dict(request.data) if request.data else {}
        if "token" not in data and request.query_params.get("token"):
            data = {"token": request.query_params["token"]}
        serializer = UnsubscribeSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        ip = BaseThrottle().get_ident(request) or ""
        services.unsubscribe(serializer.validated_data["token"], ip=cast(str, ip))
        response = Response({"detail": "You have been unsubscribed from marketing email."})
        response["Cache-Control"] = "no-store"
        return response
