"""Check a Google ID token against Google's published signing keys.

The browser obtains the token with Google Identity Services and sends it to us. We accept it
only if the signature is Google's, it was issued for our client id, it has not expired, and
(when the caller supplied one) the nonce matches.
"""

import jwt
import structlog
from django.conf import settings

from apps.core.identity import (
    IdentityProviderUnavailable,
    IdTokenVerifier,
    InvalidIdToken,
    VerifiedIdentity,
)

logger = structlog.get_logger(__name__)

JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
ISSUERS = ("https://accounts.google.com", "accounts.google.com")
TIMEOUT_SECONDS = 3

_keys = jwt.PyJWKClient(JWKS_URL, cache_keys=True, lifespan=3600, timeout=TIMEOUT_SECONDS)


class GoogleTokenVerifier(IdTokenVerifier):
    def verify(self, id_token: str, *, nonce: str = "") -> VerifiedIdentity:
        try:
            key = _keys.get_signing_key_from_jwt(id_token)
            claims = jwt.decode(
                id_token,
                key.key,
                algorithms=["RS256"],
                audience=settings.GOOGLE_CLIENT_ID,
                issuer=list(ISSUERS),
                options={"require": ["exp", "iat", "iss", "aud", "sub"]},
            )
        except jwt.PyJWKClientConnectionError as exc:
            logger.warning("google_keys_unreachable", error=str(exc))
            raise IdentityProviderUnavailable() from exc
        except jwt.PyJWTError as exc:
            raise InvalidIdToken() from exc
        if nonce and claims.get("nonce") != nonce:
            raise InvalidIdToken()
        email = claims.get("email")
        if not isinstance(email, str) or not email:
            raise InvalidIdToken()
        return VerifiedIdentity(
            subject=str(claims["sub"]),
            email=email,
            email_verified=claims.get("email_verified") is True,
            name=str(claims.get("name", "")),
        )
