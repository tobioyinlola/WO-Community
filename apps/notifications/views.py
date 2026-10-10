from typing import Any, cast
from uuid import UUID

from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import exceptions, serializers, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import BaseThrottle
from rest_framework.views import APIView

from apps.accounts import services as accounts
from apps.core import policies
from apps.core.serializers import StrictSerializer
from apps.integrations.email import get_email_adapter
from apps.notifications import centre, preferences, services


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


class NotificationItemSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    type = serializers.CharField()
    title = serializers.CharField()
    link = serializers.CharField(help_text="Path in the web app")
    meta = serializers.DictField(help_text="Ids to route on; no personal text")
    read = serializers.BooleanField()
    created_at = serializers.DateTimeField()


class NotificationListSerializer(serializers.Serializer):
    results = NotificationItemSerializer(many=True)
    next_cursor = serializers.CharField(allow_null=True)
    unread_count = serializers.IntegerField()


class NotificationQuerySerializer(StrictSerializer):
    unread = serializers.BooleanField(required=False, default=False)
    cursor = serializers.CharField(required=False, allow_blank=True, max_length=400, default="")
    limit = serializers.IntegerField(required=False, min_value=1, max_value=100, default=20)


class MarkReadSerializer(StrictSerializer):
    ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, max_length=100, allow_empty=False
    )
    all = serializers.BooleanField(required=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if ("ids" in attrs) == bool(attrs.get("all")):
            raise serializers.ValidationError("Send either ids or all=true.")
        return attrs


class MarkReadResultSerializer(serializers.Serializer):
    updated = serializers.IntegerField()
    unread_count = serializers.IntegerField()


class NotificationsView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="Your notifications, newest first",
        description="Meant to be polled about every 30 seconds. Send the last `ETag` in "
        "`If-None-Match`; if nothing changed the answer is 304 with no body.",
        parameters=[
            NotificationQuerySerializer,
            OpenApiParameter("If-None-Match", str, OpenApiParameter.HEADER),
        ],
        responses={
            200: NotificationListSerializer,
            304: OpenApiResponse(description="Nothing changed"),
            401: OpenApiResponse(description="Not logged in"),
            403: OpenApiResponse(description="Not an active member"),
        },
        tags=["notifications"],
    )
    def get(self, request: Request) -> Response:
        params = NotificationQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        data = params.validated_data
        user_id = cast(UUID, request.user.pk)
        tag = centre.fingerprint(
            user_id, unread_only=data["unread"], cursor=data["cursor"], limit=data["limit"]
        )
        candidates = [t.strip() for t in request.headers.get("If-None-Match", "").split(",")]
        if tag in [c.removeprefix("W/") for c in candidates]:
            not_modified = Response(status=status.HTTP_304_NOT_MODIFIED)
            not_modified["ETag"] = tag
            return not_modified
        page = centre.page(
            user_id, unread_only=data["unread"], cursor=data["cursor"], limit=data["limit"]
        )
        response = Response(NotificationListSerializer(page).data)
        response["ETag"] = tag
        response["Cache-Control"] = "private, no-cache"
        return response


class MarkReadView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="Mark notifications as read",
        description="Send `ids` (up to 100) or `all: true`. Ids that are not yours are ignored.",
        request=MarkReadSerializer,
        responses={
            200: MarkReadResultSerializer,
            400: OpenApiResponse(description="Neither or both of ids and all"),
            401: OpenApiResponse(description="Not logged in"),
        },
        tags=["notifications"],
    )
    def post(self, request: Request) -> Response:
        serializer = MarkReadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user_id = cast(UUID, request.user.pk)
        updated = centre.mark_read(user_id, ids=data.get("ids"), everything=bool(data.get("all")))
        body = {"updated": updated, "unread_count": centre.unread_count(user_id)}
        return Response(MarkReadResultSerializer(body).data)


class MarketingConsentSerializer(StrictSerializer):
    granted = serializers.BooleanField()


class MarketingConsentView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="Whether you agreed to receive news and marketing email",
        responses={
            200: MarketingConsentSerializer,
            401: OpenApiResponse(description="Not logged in"),
        },
        tags=["notifications"],
    )
    def get(self, request: Request) -> Response:
        granted = accounts.has_marketing_consent(cast(UUID, request.user.pk))
        return Response({"granted": granted})

    @extend_schema(
        summary="Agree to, or stop, marketing email",
        description="Separate from account emails, which always continue. Stopping takes effect "
        "at once, including for a campaign already sending. Agreeing again lifts an earlier "
        "unsubscribe, but never a bounce or complaint block.",
        request=MarketingConsentSerializer,
        responses={
            200: MarketingConsentSerializer,
            401: OpenApiResponse(description="Not logged in"),
        },
        tags=["notifications"],
    )
    def put(self, request: Request) -> Response:
        serializer = MarketingConsentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        granted = serializer.validated_data["granted"]
        user_id = cast(UUID, request.user.pk)
        ip = BaseThrottle().get_ident(request) or ""
        services.change_marketing_consent(
            user_id, cast(Any, request.user).email, granted, ip=str(ip)
        )
        return Response({"granted": granted})
