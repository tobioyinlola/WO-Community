"""What an external identity provider tells us about a person who signed in with it."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


class InvalidIdToken(Exception):
    """The token is forged, expired, meant for another app or otherwise unusable."""


class IdentityProviderUnavailable(Exception):
    """The provider could not be reached, so the token could not be checked."""


@dataclass(frozen=True)
class VerifiedIdentity:
    subject: str
    email: str
    email_verified: bool
    name: str = ""


class IdTokenVerifier(ABC):
    @abstractmethod
    def verify(self, id_token: str, *, nonce: str = "") -> VerifiedIdentity:
        """Return who the token proves, or raise ``InvalidIdToken``.

        Raises ``IdentityProviderUnavailable`` when the check cannot be completed.
        """
