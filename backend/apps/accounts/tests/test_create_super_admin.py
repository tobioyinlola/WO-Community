import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.accounts.models import User, UserStatus

pytestmark = pytest.mark.django_db

GOOD = "a-long-enough-pass-phrase-9"


def test_creates_an_active_super_admin(monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", GOOD)
    call_command("create_super_admin", email="First@Example.com")
    user = User.objects.get(email="first@example.com")
    assert user.status == UserStatus.ACTIVE
    assert user.email_verified_at and user.approved_at
    assert user.check_password(GOOD)
    assert list(user.user_roles.values_list("role", flat=True)) == ["super_admin"]


def test_refuses_an_address_that_already_has_an_account(monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", GOOD)
    call_command("create_super_admin", email="first@example.com")
    with pytest.raises(CommandError, match="already exists"):
        call_command("create_super_admin", email="first@example.com")


def test_refuses_a_weak_password(monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "short")
    with pytest.raises(CommandError):
        call_command("create_super_admin", email="first@example.com")
    assert not User.objects.exists()


def test_refuses_something_that_is_not_an_email(monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", GOOD)
    with pytest.raises(CommandError, match="not an email"):
        call_command("create_super_admin", email="nobody")


def test_asks_twice_and_stops_when_they_differ(monkeypatch):
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    answers = iter([GOOD, GOOD + "x"])
    monkeypatch.setattr(
        "apps.accounts.management.commands.create_super_admin.getpass",
        lambda _prompt: next(answers),
    )
    with pytest.raises(CommandError, match="do not match"):
        call_command("create_super_admin", email="first@example.com")
