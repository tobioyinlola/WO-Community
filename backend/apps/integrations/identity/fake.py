from apps.core.identity import IdTokenVerifier, InvalidIdToken, VerifiedIdentity


class FakeGoogleVerifier(IdTokenVerifier):
    """Accepts ``fake|subject|email|1 (verified) or 0|name``. Never touches the network."""

    def verify(self, id_token: str, *, nonce: str = "") -> VerifiedIdentity:
        parts = id_token.split("|")
        if len(parts) != 5 or parts[0] != "fake" or not parts[1] or not parts[2]:
            raise InvalidIdToken()
        return VerifiedIdentity(
            subject=parts[1], email=parts[2], email_verified=parts[3] == "1", name=parts[4]
        )
