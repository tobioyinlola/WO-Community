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


@dataclass(frozen=True)
class MemberApproved(DomainEvent):
    topic: ClassVar[str] = "accounts.member_approved"
    user_id: str


@dataclass(frozen=True)
class MemberRejected(DomainEvent):
    topic: ClassVar[str] = "accounts.member_rejected"
    user_id: str
    reason: str


@dataclass(frozen=True)
class MemberSuspended(DomainEvent):
    topic: ClassVar[str] = "accounts.member_suspended"
    user_id: str


@dataclass(frozen=True)
class MemberReinstated(DomainEvent):
    topic: ClassVar[str] = "accounts.member_reinstated"
    user_id: str


@dataclass(frozen=True)
class MemberRemoved(DomainEvent):
    """Consumers must take the member's public pages down immediately."""

    topic: ClassVar[str] = "accounts.member_removed"
    user_id: str


@dataclass(frozen=True)
class InvitationRequested(DomainEvent):
    """An invitation email should be sent (first send or resend)."""

    topic: ClassVar[str] = "accounts.invitation_requested"
    invitation_id: str
    nonce: str
