from rest_framework import authentication, exceptions
from rest_framework.request import Request

from apps.accounts import tokens
from apps.accounts.models import BLOCKED_STATUSES, User


class JWTAuthentication(authentication.BaseAuthentication):
    """Bearer access token. Suspended and removed accounts are refused here."""

    keyword = "Bearer"

    def authenticate(self, request: Request) -> tuple[User, dict] | None:
        header = authentication.get_authorization_header(request).decode("latin-1")
        if not header:
            return None
        parts = header.split()
        if len(parts) != 2 or parts[0] != self.keyword:
            raise exceptions.AuthenticationFailed("Invalid authorization header.")
        try:
            claims = tokens.verify_access_token(parts[1])
        except tokens.InvalidToken as exc:
            raise exceptions.AuthenticationFailed("Invalid or expired token.") from exc
        try:
            user = User.objects.get(pk=claims["sub"])
        except (User.DoesNotExist, ValueError) as exc:
            raise exceptions.AuthenticationFailed("Invalid or expired token.") from exc
        if user.status in BLOCKED_STATUSES:
            raise exceptions.AuthenticationFailed("Account is not available.")
        if claims["tv"] != user.token_version:
            raise exceptions.AuthenticationFailed("Invalid or expired token.")
        return user, claims

    def authenticate_header(self, request: Request) -> str:
        return self.keyword


class OptionalJWTAuthentication(JWTAuthentication):
    """A signed-in member if the token is good, otherwise just an anonymous visitor.

    For endpoints that anyone may call but that behave better when they know who
    it is (analytics). A bad or expired token never turns into a 401 there.
    """

    def authenticate(self, request: Request) -> tuple[User, dict] | None:
        try:
            return super().authenticate(request)
        except exceptions.AuthenticationFailed:
            return None
