import pytest
from cryptography.fernet import Fernet
from django.core.exceptions import ImproperlyConfigured

from apps.core import crypto


def test_round_trip_and_ciphertext_hides_the_value():
    token = crypto.encrypt("JBSWY3DPEHPK3PXP")
    assert "JBSWY3DPEHPK3PXP" not in token
    assert crypto.decrypt(token) == "JBSWY3DPEHPK3PXP"


def test_encrypting_twice_gives_different_ciphertext():
    assert crypto.encrypt("same") != crypto.encrypt("same")


def test_a_value_encrypted_under_an_old_key_still_decrypts_and_can_be_rotated(settings):
    old = settings.FIELD_ENCRYPTION_KEYS[0]
    token = crypto.encrypt("secret")
    new = Fernet.generate_key().decode()
    settings.FIELD_ENCRYPTION_KEYS = [new, old]
    assert crypto.decrypt(token) == "secret"
    rotated = crypto.rotate(token)
    settings.FIELD_ENCRYPTION_KEYS = [new]
    assert crypto.decrypt(rotated) == "secret"
    with pytest.raises(crypto.DecryptionError):
        crypto.decrypt(token)


def test_wrong_key_cannot_decrypt(settings):
    token = crypto.encrypt("secret")
    settings.FIELD_ENCRYPTION_KEYS = [Fernet.generate_key().decode()]
    with pytest.raises(crypto.DecryptionError):
        crypto.decrypt(token)


def test_missing_keys_fail_loudly(settings):
    settings.FIELD_ENCRYPTION_KEYS = []
    with pytest.raises(ImproperlyConfigured):
        crypto.encrypt("x")
