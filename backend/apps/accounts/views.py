from typing import cast

from django.conf import settings
from django.db.models import F
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.core import policies


class MeSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    email = serializers.EmailField()
    status = serializers.CharField()
    roles = serializers.ListField(child=serializers.CharField())
    community_invite_url = serializers.CharField(
        allow_null=True,
        help_text="WhatsApp community link to offer at sign-in; null when not to be shown.",
    )


class MeView(APIView):
    policy = policies.authenticated

    @extend_schema(summary="Current account", responses=MeSerializer, tags=["me"])
    def get(self, request: Request) -> Response:
        user = cast(User, request.user)
        return Response(
            MeSerializer(
                {
                    "id": user.pk,
                    "email": user.email,
                    "status": user.status,
                    "roles": sorted(user.role_names()),
                    "community_invite_url": _invite_url(user),
                }
            ).data
        )


def _invite_url(user: User) -> str | None:
    url = settings.WHATSAPP_COMMUNITY_URL
    if not url or user.status != "active" or user.community_invite_joined_at:
        return None
    if user.community_invite_shown >= settings.COMMUNITY_INVITE_SHOWINGS:
        return None
    return str(url)


class CommunityInviteShownView(APIView):
    policy = policies.authenticated

    @extend_schema(
        summary="Record that the WhatsApp community invitation was shown",
        request=None,
        responses={204: None},
        tags=["me"],
    )
    def post(self, request: Request) -> Response:
        user = cast(User, request.user)
        User.objects.filter(
            pk=user.pk, community_invite_shown__lt=settings.COMMUNITY_INVITE_SHOWINGS
        ).update(community_invite_shown=F("community_invite_shown") + 1)
        return Response(status=204)


class CommunityInviteJoinedView(APIView):
    policy = policies.authenticated

    @extend_schema(
        summary="Record that the member followed the WhatsApp community link",
        request=None,
        responses={204: None},
        tags=["me"],
    )
    def post(self, request: Request) -> Response:
        user = cast(User, request.user)
        User.objects.filter(pk=user.pk, community_invite_joined_at__isnull=True).update(
            community_invite_joined_at=timezone.now()
        )
        return Response(status=204)
