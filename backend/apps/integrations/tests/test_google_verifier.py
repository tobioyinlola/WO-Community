from datetime import timedelta

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from django.conf import settings
from django.utils import timezone

from apps.core.identity import InvalidIdToken
from apps.integrations.identity import google

EMAIL = "ada@example.com"


class _Key:
    def __init__(self, key):
        self.key = key


class _Keys:
    def __init__(self, key):
        self._key = _Key(key)

    def get_signing_key_from_jwt(self, token):
        return self._key


@pytest.fixture
def signing(monkeypatch):
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(google, "_keys", _Keys(private.public_key()))
    return private


def mint(private, **claims):
    now = timezone.now()
    payload = {
        "iss": "https://accounts.google.com",
        "aud": settings.GOOGLE_CLIENT_ID,
        "sub": "123",
        "email": EMAIL,
        "email_verified": True,
        "name": "Ada Founder",
        "iat": now,
        "exp": now + timedelta(minutes=30),
    }
    payload.update(claims)
    return jwt.encode(payload, private, algorithm="RS256")


def test_a_genuine_google_token_is_accepted(signing):
    identity = google.GoogleTokenVerifier().verify(mint(signing))
    assert (identity.subject, identity.email, identity.email_verified, identity.name) == (
        "123",
        EMAIL,
        True,
        "Ada Founder",
    )


def test_the_older_issuer_spelling_is_also_accepted(signing):
    assert google.GoogleTokenVerifier().verify(mint(signing, iss="accounts.google.com"))


@pytest.mark.parametrize(
    "claims",
    [
        {"aud": "someone-elses-app"},
        {"iss": "https://evil.example.com"},
        {"exp": timezone.now() - timedelta(minutes=1)},
        {"email": None},
    ],
)
def test_tokens_that_are_not_for_us_or_not_current_are_refused(signing, claims):
    with pytest.raises(InvalidIdToken):
        google.GoogleTokenVerifier().verify(mint(signing, **claims))


def test_a_token_signed_by_someone_else_is_refused(signing):
    forger = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(InvalidIdToken):
        google.GoogleTokenVerifier().verify(mint(forger))


def test_an_unsigned_token_is_refused(signing):
    forged = jwt.encode({"sub": "1", "email": EMAIL}, key=None, algorithm="none")
    with pytest.raises(InvalidIdToken):
        google.GoogleTokenVerifier().verify(forged)


def test_the_nonce_is_checked_when_one_was_sent(signing):
    verifier = google.GoogleTokenVerifier()
    assert verifier.verify(mint(signing, nonce="abc"), nonce="abc")
    with pytest.raises(InvalidIdToken):
        verifier.verify(mint(signing, nonce="abc"), nonce="different")
    with pytest.raises(InvalidIdToken):
        verifier.verify(mint(signing), nonce="abc")


def test_unconfirmed_addresses_are_reported_as_such_not_hidden(signing):
    identity = google.GoogleTokenVerifier().verify(mint(signing, email_verified="true"))
    assert identity.email_verified is False  # only a real boolean true counts
