import hashlib
from io import BytesIO
from urllib.error import URLError

import pytest
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from apps.integrations.passwords import get_breach_checker
from apps.integrations.passwords.fake import FakeBreachChecker
from apps.integrations.passwords.hibp import HibpBreachChecker

PASSWORD = "correct-horse-battery-staple"
DIGEST = hashlib.sha1(PASSWORD.encode(), usedforsecurity=False).hexdigest().upper()  # noqa: S324


class FakeResponse(BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def respond_with(monkeypatch, body: str, capture: list | None = None):
    def fake_urlopen(request, timeout):
        if capture is not None:
            capture.append((request, timeout))
        return FakeResponse(body.encode())

    monkeypatch.setattr("apps.integrations.passwords.hibp.urlopen", fake_urlopen)


def test_settings_select_the_fake_checker_in_tests():
    assert isinstance(get_breach_checker(), FakeBreachChecker)


def test_validator_rejects_a_breached_password():
    with pytest.raises(ValidationError) as caught:
        validate_password("Password123!456")
    assert any(e.code == "password_breached" for e in caught.value.error_list)


def test_validator_accepts_an_unknown_password():
    validate_password(PASSWORD)


def test_only_the_hash_prefix_is_sent(monkeypatch):
    seen: list = []
    respond_with(monkeypatch, "0018A45C4D1DEF81644B54AB7F969B88D65:3\r\n", seen)
    HibpBreachChecker().is_breached(PASSWORD)
    request, timeout = seen[0]
    assert request.full_url == f"https://api.pwnedpasswords.com/range/{DIGEST[:5]}"
    assert DIGEST[5:] not in request.full_url
    assert PASSWORD not in request.full_url
    assert request.get_header("Add-padding") == "true"
    assert timeout <= 5


def test_listed_suffix_means_breached(monkeypatch):
    respond_with(monkeypatch, f"AAAA:1\r\n{DIGEST[5:]}:12345\r\nBBBB:2\r\n")
    assert HibpBreachChecker().is_breached(PASSWORD) is True


def test_unlisted_suffix_is_not_breached(monkeypatch):
    respond_with(monkeypatch, "AAAA:1\r\nBBBB:2\r\n")
    assert HibpBreachChecker().is_breached(PASSWORD) is False


def test_padding_entries_with_zero_count_are_ignored(monkeypatch):
    respond_with(monkeypatch, f"{DIGEST[5:]}:0\r\n")
    assert HibpBreachChecker().is_breached(PASSWORD) is False


@pytest.mark.parametrize("error", [URLError("down"), TimeoutError(), OSError("reset")])
def test_lookup_failures_fail_open(monkeypatch, error):
    def broken(request, timeout):
        raise error

    monkeypatch.setattr("apps.integrations.passwords.hibp.urlopen", broken)
    assert HibpBreachChecker().is_breached(PASSWORD) is False
