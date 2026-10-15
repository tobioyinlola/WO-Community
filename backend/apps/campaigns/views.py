from typing import cast

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import exceptions, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, BaseThrottle, ScopedRateThrottle
from rest_framework.views import APIView

from apps.campaigns import newsletter, services
from apps.campaigns.serializers import (
    NewsletterResultSerializer,
    NewsletterSignupSerializer,
    NewsletterTokenSerializer,
    UnsubscribeResultSerializer,
    UnsubscribeSerializer,
)
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


# --- the newsletter sign up on the website ---


class _NewsletterView(APIView):
    policy = policies.public
    authentication_classes: list[type] = []
    throttle_classes = [AnonRateThrottle, ScopedRateThrottle]
    throttle_scope = "newsletter"


def _link_error() -> exceptions.ValidationError:
    return exceptions.ValidationError({"token": ["This link is not valid or has expired."]})


class NewsletterSignupView(_NewsletterView):
    @extend_schema(
        summary="Sign up for the newsletter",
        description="Sends a confirmation link; nothing is sent until it is opened. The answer is "
        "the same whether or not the address is already on the list.",
        request=NewsletterSignupSerializer,
        responses={202: NewsletterResultSerializer, 400: OpenApiResponse(description="Invalid")},
        tags=["public"],
    )
    def post(self, request: Request) -> Response:
        serializer = NewsletterSignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not serializer.validated_data["website"]:  # the hidden field is only filled by bots
            newsletter.subscribe(serializer.validated_data["email"])
        response = Response(
            {"detail": "Check your inbox and open the link to confirm your subscription."},
            status=status.HTTP_202_ACCEPTED,
        )
        response["Cache-Control"] = "no-store"
        return response


class NewsletterConfirmView(_NewsletterView):
    @extend_schema(
        summary="Confirm a newsletter sign up",
        description="Opened from the link in the confirmation email. Safe to repeat.",
        request=NewsletterTokenSerializer,
        responses={200: NewsletterResultSerializer, 400: OpenApiResponse(description="Bad link")},
        tags=["public"],
    )
    def post(self, request: Request) -> Response:
        serializer = NewsletterTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            newsletter.confirm(serializer.validated_data["token"])
        except newsletter.InvalidLink as exc:
            raise _link_error() from exc
        return Response({"detail": "You're subscribed to the WO Community newsletter."})


class NewsletterUnsubscribeView(_NewsletterView):
    @extend_schema(
        summary="Leave the newsletter",
        description="For people who signed up on the website. Takes effect at once. Send the "
        "token as JSON, or in the query string as mail clients do (RFC 8058).",
        request=NewsletterTokenSerializer,
        responses={200: NewsletterResultSerializer, 400: OpenApiResponse(description="Bad link")},
        tags=["public"],
    )
    def post(self, request: Request) -> Response:
        data = dict(request.data) if request.data else {}
        if "token" not in data and request.query_params.get("token"):
            data = {"token": request.query_params["token"]}
        serializer = NewsletterTokenSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        try:
            newsletter.unsubscribe(serializer.validated_data["token"])
        except newsletter.InvalidLink as exc:
            raise _link_error() from exc
        response = Response({"detail": "You have left the newsletter."})
        response["Cache-Control"] = "no-store"
        return response
