from datetime import timedelta
from typing import Any
from uuid import UUID

from django.conf import settings
from django.utils import timezone
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import exceptions
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.core import policies, ratelimit
from apps.toolkit.sharing import content, services
from apps.toolkit.sharing.models import ShareLink
from apps.toolkit.sharing.serializers import (
    TkShareCreatedSerializer,
    TkShareCreateSerializer,
    TkSharedContentSerializer,
    TkSharePasswordSerializer,
    TkShareSerializer,
)
from apps.toolkit.ventures.permissions import member_policy, owned_venture, uid

ERRORS = {
    401: OpenApiResponse(description="Not authenticated"),
    403: OpenApiResponse(description="Not an approved member"),
    404: OpenApiResponse(description="Not found, or not yours, or the tool is off"),
}
FAILURES_PER_QUARTER_HOUR = 10
NOINDEX = "noindex, nofollow, noarchive"


def _private(response: Response) -> Response:
    response["Cache-Control"] = "private, no-store"
    return response


class SharesView(APIView):
    policy = member_policy()

    @extend_schema(
        summary="Share links for a venture",
        responses={200: TkShareSerializer(many=True), **ERRORS},
        tags=["toolkit"],
    )
    def get(self, request: Request, venture_id: UUID) -> Response:
        venture = owned_venture(request, venture_id)
        rows = [
            services.view(s)
            for s in ShareLink.objects.filter(venture=venture, owner_id=uid(request)).order_by(
                "-created_at"
            )
        ]
        return _private(Response(TkShareSerializer(rows, many=True).data))

    @extend_schema(
        summary="Create a share link",
        description="Read only, optionally with a password and an expiry. The token is in the "
        "answer once. Anyone with the link can see the content, so share it only with people "
        "you trust.",
        request=TkShareCreateSerializer,
        responses={201: TkShareCreatedSerializer, **ERRORS},
        tags=["toolkit"],
    )
    def post(self, request: Request, venture_id: UUID) -> Response:
        venture = owned_venture(request, venture_id)
        body = TkShareCreateSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        if not content.subject_exists(venture, data["subject_type"], data["subject_id"]):
            raise exceptions.NotFound()
        days = data.get("expires_in_days")
        link, token = services.create(
            venture=venture,
            owner_id=uid(request),
            subject_type=data["subject_type"],
            subject_id=data["subject_id"],
            password=data.get("password", ""),
            expires_at=timezone.now() + timedelta(days=days) if days else None,
        )
        base = settings.FRONTEND_BASE_URL.rstrip("/")
        out = {**services.view(link), "token": token, "url": f"{base}/share/{token}"}
        return _private(Response(TkShareCreatedSerializer(out).data, status=201))


class ShareView(APIView):
    policy = member_policy()

    @extend_schema(
        summary="Revoke a share link",
        description="The link stops working at once.",
        request=None,
        responses={204: OpenApiResponse(description="Revoked"), **ERRORS},
        tags=["toolkit"],
    )
    def delete(self, request: Request, venture_id: UUID, share_id: UUID) -> Response:
        venture = owned_venture(request, venture_id)
        link = ShareLink.objects.filter(
            pk=share_id, venture=venture, owner_id=uid(request), revoked_at__isnull=True
        ).first()
        if link is None:
            raise exceptions.NotFound()
        services.revoke(link=link)
        return Response(status=204)


class PublicShareView(APIView):
    """Anonymous. Every failure is the same 404, so a token cannot be probed for state."""

    policy = policies.public
    authentication_classes: list[Any] = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "toolkit_share"

    def _respond(self, link: ShareLink) -> Response:
        data = content.build(link)
        services.record_view(link)
        response = Response(TkSharedContentSerializer(data).data)
        response["Cache-Control"] = "private, no-store"
        response["X-Robots-Tag"] = NOINDEX
        response["Referrer-Policy"] = "no-referrer"
        return response

    def _link(self, token: str) -> ShareLink:
        link = services.find(token)
        if link is None:
            raise exceptions.NotFound()
        return link

    @extend_schema(
        summary="A shared deck, plan summary or score summary",
        description="Read only. A link with a password answers 401 with `password_required`; "
        "send the password with POST. Unknown, revoked and expired links are the same 404. "
        "Pages are marked noindex and are never cached.",
        responses={
            200: TkSharedContentSerializer,
            401: OpenApiResponse(description="This link needs a password"),
            404: OpenApiResponse(description="No such link"),
            429: OpenApiResponse(description="Too many requests"),
        },
        tags=["public"],
        auth=[],
    )
    def get(self, request: Request, token: str) -> Response:
        link = self._link(token)
        if services.needs_password(link):
            response = Response({"password_required": True}, status=401)
            response["X-Robots-Tag"] = NOINDEX
            response["Cache-Control"] = "private, no-store"
            return response
        return self._respond(link)

    @extend_schema(
        summary="Open a password protected share",
        request=TkSharePasswordSerializer,
        responses={
            200: TkSharedContentSerializer,
            404: OpenApiResponse(description="No such link, or the wrong password"),
            429: OpenApiResponse(description="Too many attempts"),
        },
        tags=["public"],
        auth=[],
    )
    def post(self, request: Request, token: str) -> Response:
        link = self._link(token)
        body = TkSharePasswordSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        address = request.META.get("REMOTE_ADDR", "")
        key = f"toolkit:share:fail:{link.pk}:{address}"
        if ratelimit.current(key) >= FAILURES_PER_QUARTER_HOUR:
            raise exceptions.Throttled(wait=900)
        if not services.password_ok(link, body.validated_data["password"]):
            ratelimit.hit(key, 900)
            raise exceptions.NotFound()
        return self._respond(link)
