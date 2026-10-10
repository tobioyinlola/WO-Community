from typing import Any
from uuid import UUID

from django.conf import settings
from django.http import HttpResponse
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import exceptions, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, BaseThrottle, ScopedRateThrottle
from rest_framework.views import APIView

from apps.accounts import services
from apps.accounts.serializers import (
    AccessTokenSerializer,
    ForgotPasswordSerializer,
    InvitationPreviewSerializer,
    LoginSerializer,
    MessageSerializer,
    MfaChallengeSerializer,
    RegisteredSerializer,
    RegisterSerializer,
    ResetPasswordSerializer,
    SessionSerializer,
    TokenSerializer,
)
from apps.core import policies


def client_ip(request: Request) -> str:
    return BaseThrottle().get_ident(request) or ""


def user_agent(request: Request) -> str:
    return str(request.META.get("HTTP_USER_AGENT", ""))


class PublicAuthView(APIView):
    """Unauthenticated endpoint with its own rate limit scope."""

    policy = policies.public
    authentication_classes: list[Any] = []
    throttle_classes = [AnonRateThrottle, ScopedRateThrottle]


def _set_refresh_cookie(response: HttpResponse, token: str, max_age: int) -> None:
    response.set_cookie(
        settings.REFRESH_COOKIE_NAME,
        token,
        max_age=max_age,
        path=settings.REFRESH_COOKIE_PATH,
        secure=settings.REFRESH_COOKIE_SECURE,
        httponly=True,
        samesite="Lax",
    )


def _clear_refresh_cookie(response: HttpResponse) -> None:
    response.delete_cookie(
        settings.REFRESH_COOKIE_NAME, path=settings.REFRESH_COOKIE_PATH, samesite="Lax"
    )


def _token_response(result: services.LoginResult) -> Response:
    body = {
        "access_token": result.access_token,
        "token_type": "Bearer",
        "expires_in": int(settings.JWT_ACCESS_LIFETIME.total_seconds()),
        "user": {
            "id": result.user.pk,
            "email": result.user.email,
            "status": result.user.status,
        },
        "mfa_enrolment_required": services.mfa_enrolment_required(result.user),
    }
    response = Response(AccessTokenSerializer(body).data)
    response["Cache-Control"] = "no-store"
    max_age = int(settings.REFRESH_SLIDING_LIFETIME.total_seconds())
    _set_refresh_cookie(response, result.refresh_token, max_age)
    return response


def _require_ajax_header(request: Request) -> None:
    """Cookie authenticated endpoints need a header a cross-site form cannot send."""
    if not request.headers.get("X-Requested-With"):
        raise exceptions.PermissionDenied("Missing X-Requested-With header.")


class RegisterView(PublicAuthView):
    throttle_scope = "auth_register"

    @extend_schema(
        summary="Register an account",
        description="Always answers 202, whether or not the address is already registered. "
        "The account stays pending until an admin approves it. With a valid "
        "`invitation_token` for the same address the account is approved at once and the "
        "answer is 201 instead.",
        request=RegisterSerializer,
        responses={202: MessageSerializer, 201: RegisteredSerializer},
        tags=["auth"],
    )
    def post(self, request: Request) -> Response:
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        approved = services.register(
            email=data["email"],
            password=data["password"],
            consents={
                "terms": data["accepted_terms"],
                "privacy": data["accepted_privacy"],
                "conduct": data["accepted_conduct"],
                "marketing": data["marketing_consent"],
            },
            ip=client_ip(request),
            invitation_token=data["invitation_token"],
            signup={"profile": data["profile"], "startup": data["startup"]},
        )
        if approved:
            return Response(
                {"detail": "Your account is ready. You can log in.", "approved": True},
                status=status.HTTP_201_CREATED,
            )
        return Response(
            {"detail": "Check your email to confirm your address."},
            status=status.HTTP_202_ACCEPTED,
        )


class InspectInvitationView(PublicAuthView):
    throttle_scope = "auth_token"

    @extend_schema(
        summary="Look up an invitation link",
        description="Lets the registration page prefill the invited address. Marks the "
        "invitation as opened.",
        request=TokenSerializer,
        responses={200: InvitationPreviewSerializer, 400: OpenApiResponse(description="Invalid")},
        tags=["auth"],
    )
    def post(self, request: Request) -> Response:
        serializer = TokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invitation = services.inspect_invitation(serializer.validated_data["token"])
        response = Response(InvitationPreviewSerializer(invitation).data)
        response["Cache-Control"] = "no-store"
        return response


class VerifyEmailView(PublicAuthView):
    throttle_scope = "auth_token"

    @extend_schema(
        summary="Confirm an email address",
        request=TokenSerializer,
        responses={200: MessageSerializer, 400: OpenApiResponse(description="Invalid token")},
        tags=["auth"],
    )
    def post(self, request: Request) -> Response:
        serializer = TokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.verify_email(serializer.validated_data["token"])
        return Response({"detail": "Email address confirmed."})


class LoginView(PublicAuthView):
    throttle_scope = "auth_login"

    @extend_schema(
        summary="Log in",
        description="Returns a short lived access token and sets the refresh token cookie. "
        "Accounts with MFA get a 202 with an `mfa_token` instead; finish with "
        "`POST /auth/mfa/verify`.",
        request=LoginSerializer,
        responses={
            200: AccessTokenSerializer,
            202: MfaChallengeSerializer,
            401: OpenApiResponse(description="Invalid credentials"),
            403: OpenApiResponse(description="Email not verified"),
            429: OpenApiResponse(description="Too many attempts"),
        },
        tags=["auth"],
    )
    def post(self, request: Request) -> Response:
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = services.login(
            email=serializer.validated_data["email"],
            password=serializer.validated_data["password"],
            ip=client_ip(request),
            user_agent=user_agent(request),
        )
        if isinstance(result, services.MfaChallenge):
            challenge = Response(
                {"mfa_required": True, "mfa_token": result.mfa_token},
                status=status.HTTP_202_ACCEPTED,
            )
            challenge["Cache-Control"] = "no-store"
            return challenge
        return _token_response(result)


class RefreshView(PublicAuthView):
    throttle_scope = "auth_refresh"

    @extend_schema(
        summary="Rotate the refresh token and get a new access token",
        description="Reads the refresh cookie and requires an X-Requested-With header. "
        "Reusing an old refresh token revokes the whole session.",
        request=None,
        responses={200: AccessTokenSerializer, 401: OpenApiResponse(description="Invalid")},
        tags=["auth"],
    )
    def post(self, request: Request) -> Response:
        _require_ajax_header(request)
        raw = request.COOKIES.get(settings.REFRESH_COOKIE_NAME, "")
        try:
            result = services.refresh(raw_refresh_token=raw, ip=client_ip(request))
        except services.InvalidRefreshToken:
            response = Response(
                {
                    "type": "https://api.wocommunity.example/problems/invalid_refresh_token",
                    "title": "Authentication required",
                    "status": 401,
                    "detail": "The session is no longer valid. Log in again.",
                    "code": "invalid_refresh_token",
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )
            response.content_type = "application/problem+json"
            _clear_refresh_cookie(response)
            return response
        return _token_response(result)


class LogoutView(PublicAuthView):
    throttle_scope = "auth_refresh"

    @extend_schema(
        summary="Log out of this session",
        request=None,
        responses={204: None},
        tags=["auth"],
    )
    def post(self, request: Request) -> Response:
        _require_ajax_header(request)
        raw = request.COOKIES.get(settings.REFRESH_COOKIE_NAME, "")
        if raw:
            services.logout(raw_refresh_token=raw)
        response = Response(status=status.HTTP_204_NO_CONTENT)
        _clear_refresh_cookie(response)
        return response


class ForgotPasswordView(PublicAuthView):
    throttle_scope = "auth_forgot"

    @extend_schema(
        summary="Ask for a password reset email",
        description="Always answers 202 so it cannot be used to find registered addresses.",
        request=ForgotPasswordSerializer,
        responses={202: MessageSerializer},
        tags=["auth"],
    )
    def post(self, request: Request) -> Response:
        serializer = ForgotPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.request_password_reset(email=serializer.validated_data["email"])
        return Response(
            {"detail": "If that address has an account, a reset link is on its way."},
            status=status.HTTP_202_ACCEPTED,
        )


class ResetPasswordView(PublicAuthView):
    throttle_scope = "auth_token"

    @extend_schema(
        summary="Choose a new password with a reset token",
        description="Revokes every session of the account.",
        request=ResetPasswordSerializer,
        responses={200: MessageSerializer, 400: OpenApiResponse(description="Invalid input")},
        tags=["auth"],
    )
    def post(self, request: Request) -> Response:
        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.reset_password(
            raw_token=serializer.validated_data["token"],
            new_password=serializer.validated_data["password"],
            ip=client_ip(request),
        )
        return Response({"detail": "Password updated. Log in with your new password."})


class SessionListView(APIView):
    policy = policies.authenticated

    @extend_schema(
        summary="List your active sessions",
        responses=SessionSerializer(many=True),
        tags=["me"],
    )
    def get(self, request: Request) -> Response:
        sessions = services.list_sessions(request.user)  # type: ignore[arg-type]
        return Response(SessionSerializer(sessions, many=True).data)


class SessionDetailView(APIView):
    policy = policies.authenticated

    @extend_schema(
        summary="Revoke one of your sessions",
        responses={204: None, 404: OpenApiResponse(description="Not found")},
        tags=["me"],
    )
    def delete(self, request: Request, session_id: UUID) -> Response:
        if not services.revoke_session(request.user, session_id):  # type: ignore[arg-type]
            raise exceptions.NotFound()
        return Response(status=status.HTTP_204_NO_CONTENT)
