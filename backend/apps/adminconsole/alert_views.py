"""Each admin's own switches for approval emails."""

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import exceptions, serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.adminconsole.views import _actor
from apps.core import policies
from apps.core.serializers import StrictSerializer
from apps.notifications import adminalerts

ACCESS = policies.admin_permission("admin.access")
ERRORS = {
    401: OpenApiResponse(description="Not authenticated"),
    403: OpenApiResponse(description="Not allowed, or MFA missing"),
}


class AlertPreferenceSerializer(serializers.Serializer):
    kind = serializers.CharField()
    title = serializers.CharField(source="label")
    enabled = serializers.BooleanField()


class SetAlertPreferenceSerializer(StrictSerializer):
    kind = serializers.ChoiceField(choices=list(adminalerts.KINDS))
    enabled = serializers.BooleanField()


class AlertPreferencesView(APIView):
    policy = ACCESS

    @extend_schema(
        summary="Which approval emails I get",
        description="Only the kinds this admin may approve are listed. All are on by default.",
        responses={200: AlertPreferenceSerializer(many=True), **ERRORS},
        tags=["admin"],
    )
    def get(self, request: Request) -> Response:
        return Response(
            AlertPreferenceSerializer(adminalerts.preferences_for(_actor(request)), many=True).data
        )

    @extend_schema(
        summary="Switch one kind of approval email on or off",
        request=SetAlertPreferenceSerializer,
        responses={200: AlertPreferenceSerializer(many=True), **ERRORS},
        tags=["admin"],
    )
    def put(self, request: Request) -> Response:
        serializer = SetAlertPreferenceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            adminalerts.set_preference(
                _actor(request),
                serializer.validated_data["kind"],
                serializer.validated_data["enabled"],
            )
        except KeyError as exc:
            raise exceptions.PermissionDenied("You cannot approve that kind of item.") from exc
        return Response(
            AlertPreferenceSerializer(adminalerts.preferences_for(_actor(request)), many=True).data
        )
