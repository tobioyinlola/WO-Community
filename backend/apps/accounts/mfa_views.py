from typing import Any
from uuid import UUID

from django.conf import settings
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.accounts import services
from apps.accounts.auth_views import PublicAuthView, _token_response, client_ip, user_agent
from apps.accounts.serializers import (
    AccessTokenSerializer,
    CodeSerializer,
    MfaConfirmedSerializer,
    MfaEnrolmentSerializer,
    MfaVerifySerializer,
    RecoveryCodesSerializer,
)
from apps.core import policies

ERRORS = {
    400: OpenApiResponse(description="Invalid code"),
    401: OpenApiResponse(description="Not authenticated or sign-in step expired"),
    403: OpenApiResponse(description="Not an admin account"),
    409: OpenApiResponse(description="MFA is already set up"),
    429: OpenApiResponse(description="Too many wrong codes"),
}


def _session_id(request: Request) -> UUID | None:
    claims = request.auth if isinstance(request.auth, dict) else {}
    try:
        return UUID(str(claims["sid"])) if claims.get("sid") else None
    except ValueError:
        return None


def _access_body(token: str) -> dict[str, Any]:
    return {
        "access_token": token,
        "token_type": "Bearer",
        "expires_in": int(settings.JWT_ACCESS_LIFETIME.total_seconds()),
    }


def _no_store(response: Response) -> Response:
    response["Cache-Control"] = "no-store"
    return response


class MfaVerifyView(PublicAuthView):
    throttle_scope = "auth_mfa"

    @extend_schema(
        summary="Finish logging in with an MFA code",
        description="Takes the `mfa_token` from the login response and a code from the "
        "authenticator app or an unused recovery code. Sets the refresh cookie.",
        request=MfaVerifySerializer,
        responses={200: AccessTokenSerializer, **ERRORS},
        tags=["auth"],
    )
    def post(self, request: Request) -> Response:
        serializer = MfaVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = services.complete_mfa_login(
            mfa_token=serializer.validated_data["mfa_token"],
            code=serializer.validated_data["code"],
            ip=client_ip(request),
            user_agent=user_agent(request),
        )
        return _token_response(result)


class _AdminMfaView(APIView):
    policy = policies.admin_account
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_mfa"


class MfaEnrolView(_AdminMfaView):
    @extend_schema(
        summary="Start MFA enrolment",
        description="Returns the secret and an otpauth URI to show as a QR code. "
        "Calling it again before confirming replaces the pending secret.",
        request=None,
        responses={200: MfaEnrolmentSerializer, **ERRORS},
        tags=["auth"],
    )
    def post(self, request: Request) -> Response:
        secret, uri = services.begin_mfa_enrolment(
            request.user,  # type: ignore[arg-type]
            ip=client_ip(request),
        )
        return _no_store(
            Response(MfaEnrolmentSerializer({"secret": secret, "otpauth_uri": uri}).data)
        )


class MfaConfirmView(_AdminMfaView):
    @extend_schema(
        summary="Confirm MFA enrolment",
        description="Proves the authenticator works. Returns an access token that already "
        "counts as MFA-verified, and the recovery codes, which are shown only this once.",
        request=CodeSerializer,
        responses={200: MfaConfirmedSerializer, **ERRORS},
        tags=["auth"],
    )
    def post(self, request: Request) -> Response:
        serializer = CodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        token, codes = services.confirm_mfa_enrolment(
            request.user,  # type: ignore[arg-type]
            code=serializer.validated_data["code"],
            session_id=_session_id(request),
            ip=client_ip(request),
        )
        body = {**_access_body(token), "recovery_codes": codes}
        return _no_store(Response(MfaConfirmedSerializer(body).data))


class MfaStepUpView(_AdminMfaView):
    @extend_schema(
        summary="Re-check MFA for a destructive action",
        description="Returns a new access token whose MFA check is fresh.",
        request=CodeSerializer,
        responses={200: AccessTokenSerializer, **ERRORS},
        tags=["auth"],
    )
    def post(self, request: Request) -> Response:
        serializer = CodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        token = services.step_up(
            request.user,  # type: ignore[arg-type]
            code=serializer.validated_data["code"],
            session_id=_session_id(request),
            ip=client_ip(request),
        )
        return _no_store(Response(_access_body(token)))


class RecoveryCodesView(_AdminMfaView):
    @extend_schema(
        summary="Replace recovery codes",
        description="Needs a current authenticator code. The old codes stop working.",
        request=CodeSerializer,
        responses={200: RecoveryCodesSerializer, **ERRORS},
        tags=["auth"],
    )
    def post(self, request: Request) -> Response:
        serializer = CodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        codes = services.regenerate_recovery_codes(
            request.user,  # type: ignore[arg-type]
            code=serializer.validated_data["code"],
            ip=client_ip(request),
        )
        return _no_store(Response(RecoveryCodesSerializer({"recovery_codes": codes}).data))
