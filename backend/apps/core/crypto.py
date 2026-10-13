"""Application level encryption for secrets stored in the database.

Keys come from ``FIELD_ENCRYPTION_KEYS`` (comma separated Fernet keys). The
first key encrypts; every key can decrypt, so a key is rotated by prepending
the new one, re-encrypting rows, then dropping the old one.
"""

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class DecryptionError(Exception):
    pass


def _cipher() -> MultiFernet:
    keys = [key for key in settings.FIELD_ENCRYPTION_KEYS if key]
    if not keys:
        raise ImproperlyConfigured("FIELD_ENCRYPTION_KEYS is not set")
    return MultiFernet([Fernet(key.encode()) for key in keys])


def encrypt(plaintext: str) -> str:
    return _cipher().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    try:
        return _cipher().decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise DecryptionError("value cannot be decrypted with the configured keys") from exc


def rotate(token: str) -> str:
    """Re-encrypt a value with the current primary key."""
    try:
        return _cipher().rotate(token.encode()).decode()
    except InvalidToken as exc:
        raise DecryptionError("value cannot be decrypted with the configured keys") from exc
