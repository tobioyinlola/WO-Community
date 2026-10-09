"""Domain events published by the accounts module."""

from dataclasses import dataclass
from typing import ClassVar

from apps.core.events import DomainEvent


@dataclass(frozen=True)
class UserRegistered(DomainEvent):
    topic: ClassVar[str] = "accounts.user_registered"
    user_id: str


@dataclass(frozen=True)
class RegistrationRepeated(DomainEvent):
    """Someone registered with an address that already has an account."""

    topic: ClassVar[str] = "accounts.registration_repeated"
    user_id: str


@dataclass(frozen=True)
class PasswordResetRequested(DomainEvent):
    topic: ClassVar[str] = "accounts.password_reset_requested"
    user_id: str
