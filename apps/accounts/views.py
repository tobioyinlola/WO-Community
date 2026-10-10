from typing import cast

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
                }
            ).data
        )
