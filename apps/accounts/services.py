"""Public commands of the accounts module.

Other modules call these functions; they do not import the models.
"""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

import structlog
from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import exceptions

from apps.accounts import events, sessions, tokens
from apps.accounts.models import (
    BLOCKED_STATUSES,
    ConsentDocument,
    ConsentRecord,
    EmailToken,
    EmailTokenPurpose,
    RefreshTokenFamily,
    User,
)
from apps.audit import services as audit
from apps.core import events as domain_events
from apps.core import ratelimit

logger = structlog.get_logger(__name__)

VERIFY_EMAIL = EmailTokenPurpose.VERIFY_EMAIL
PASSWORD_RESET = EmailTokenPurpose.PASSWORD_RESET

InvalidRefreshToken = sessions.InvalidRefreshToken


class InvalidToken(exceptions.ValidationError):
    default_code = "invalid_token"

    def __init__(self) -> None:
        super().__init__({"token": ["This link is invalid or has expired."]}, code="invalid_token")


class EmailNotVerified(exceptions.PermissionDenied):
    default_code = "email_not_verified"
    default_detail = "Confirm your email address before logging in."


class InvalidCredentials(exceptions.APIException):
    # Not AuthenticationFailed: DRF downgrades that to 403 on views that send no
    # WWW-Authenticate challenge, and login is not a bearer-authenticated view.
    status_code = 401
    default_code = "invalid_credentials"
    default_detail = "Invalid email or password."


@dataclass(frozen=True)
class Contact:
    email: str
    status: str


@dataclass(frozen=True)
class LoginResult:
    user: User
    access_token: str
    refresh_token: str


def _token_digest(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def normalise_email(email: str) -> str:
    return email.strip().lower()


# --- Registration and email verification ----------------------------------------


def register(*, email: str, password: str, consents: dict[str, bool], ip: str = "") -> None:
    """Create a pending account, or quietly notify the owner of an existing one.

    Both paths look identical to the caller, in content and in timing, so the
    endpoint cannot be used to discover which addresses are registered.
    """
    address = normalise_email(email)
    existing = User.objects.filter(email__iexact=address).first()
    if existing is not None:
        make_password(password)  # keep the cost of both paths comparable
        domain_events.publish(events.RegistrationRepeated(user_id=str(existing.pk)))
        return
    try:
        with transaction.atomic():
            user = User.objects.create_user(address, password)
            versions = settings.CONSENT_DOCUMENT_VERSIONS
            ConsentRecord.objects.bulk_create(
                ConsentRecord(
                    user=user,
                    document=document,
                    version=versions[document],
                    granted=bool(consents.get(document, False)),
                    ip_hash=audit.hash_value(ip),
                )
                for document in ConsentDocument.values
            )
            domain_events.publish(events.UserRegistered(user_id=str(user.pk)))
            audit.record(
                actor=user, action="auth.registered", target_type="user", target_id=user.pk, ip=ip
            )
    except IntegrityError:
        # A concurrent request registered the same address first.
        logger.info("registration_race")


def issue_email_token(user_id: UUID, purpose: str) -> tuple[str, str] | None:
    """Create a single use token and return ``(email, raw_token)``.

    Returns None when no email should be sent, for example the address is
    already verified or the account is gone. The raw token is returned to the
    caller once and never stored.
    """
    user = User.objects.filter(pk=user_id).first()
    if user is None or user.status in BLOCKED_STATUSES:
        return None
    if purpose == VERIFY_EMAIL:
        if user.email_verified_at is not None:
            return None
        ttl = settings.EMAIL_VERIFY_TTL
    else:
        ttl = settings.PASSWORD_RESET_TTL
    raw = secrets.token_urlsafe(32)
    EmailToken.objects.create(
        user=user,
        purpose=purpose,
        token_hash=_token_digest(raw),
        expires_at=timezone.now() + ttl,
    )
    return user.email, raw


def get_contact(user_id: UUID) -> Contact | None:
    user = User.objects.filter(pk=user_id).first()
    return Contact(email=user.email, status=user.status) if user else None


def _consume_token(raw: str, purpose: str) -> User:
    """Mark a token used and return its user, or raise ``InvalidToken``."""
    token = (
        EmailToken.objects.select_for_update()
        .select_related("user")
        .filter(token_hash=_token_digest(raw), purpose=purpose)
        .first()
    )
    if token is None or token.used_at is not None or token.expires_at <= timezone.now():
        raise InvalidToken()
    token.used_at = timezone.now()
    token.save(update_fields=["used_at", "updated_at"])
    return token.user


def verify_email(raw_token: str) -> None:
    with transaction.atomic():
        user = _consume_token(raw_token, VERIFY_EMAIL)
        if user.email_verified_at is None:
            user.email_verified_at = timezone.now()
            user.save(update_fields=["email_verified_at", "updated_at"])
        audit.record(
            actor=user, action="auth.email_verified", target_type="user", target_id=user.pk
        )


# --- Password reset --------------------------------------------------------------


def request_password_reset(*, email: str) -> None:
    """Queue a reset email when the address has an account. Always silent."""
    address = normalise_email(email)
    key = f"pwreset:{_token_digest(address)}"
    if ratelimit.hit(key, 3600) > settings.PASSWORD_RESET_MAX_PER_EMAIL_PER_HOUR:
        return
    user = User.objects.filter(email__iexact=address).first()
    if user is None or user.status in BLOCKED_STATUSES:
        return
    domain_events.publish(events.PasswordResetRequested(user_id=str(user.pk)))


def reset_password(*, raw_token: str, new_password: str, ip: str = "") -> None:
    with transaction.atomic():
        user = _consume_token(raw_token, PASSWORD_RESET)
        user.set_password(new_password)
        if user.email_verified_at is None:  # the reset link proves control of the mailbox
            user.email_verified_at = timezone.now()
        user.save(update_fields=["password", "email_verified_at", "updated_at"])
        EmailToken.objects.filter(user=user, purpose=PASSWORD_RESET, used_at__isnull=True).update(
            used_at=timezone.now()
        )
        sessions.revoke_all(user, "password_reset")
        user.bump_token_version()
        audit.record(
            actor=user, action="auth.password_reset", target_type="user", target_id=user.pk, ip=ip
        )
    tokens.revoke_older_tokens(user)


# --- Login, refresh, logout ------------------------------------------------------

_dummy_hash: str | None = None


def _burn_password_check(password: str) -> None:
    """Spend the same time as a real check when the account does not exist."""
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = make_password("not-a-real-password")
    check_password(password, _dummy_hash)


def _failure_keys(address: str, ip: str) -> tuple[str, str]:
    return f"loginfail:acct:{_token_digest(address)}", f"loginfail:ip:{_token_digest(ip)}"


def login(*, email: str, password: str, ip: str, user_agent: str) -> LoginResult:
    address = normalise_email(email)
    account_key, ip_key = _failure_keys(address, ip)
    window = settings.LOGIN_FAILURE_WINDOW_SECONDS
    if (
        ratelimit.current(account_key) >= settings.LOGIN_MAX_FAILURES_PER_ACCOUNT
        or ratelimit.current(ip_key) >= settings.LOGIN_MAX_FAILURES_PER_IP
    ):
        raise exceptions.Throttled(wait=window)

    user = User.objects.filter(email__iexact=address).first()
    if user is not None:
        password_ok = user.check_password(password)
    else:
        _burn_password_check(password)
        password_ok = False
    usable = user is not None and user.status not in BLOCKED_STATUSES
    if not (user and password_ok and usable):
        ratelimit.hit(account_key, window)
        ratelimit.hit(ip_key, window)
        audit.record(
            actor=None,
            action="auth.login_failed",
            target_type="email_hash",
            target_id=_token_digest(address)[:32],
            ip=ip,
            user_agent=user_agent,
        )
        raise InvalidCredentials()
    if user.email_verified_at is None:
        raise EmailNotVerified()

    ratelimit.reset(account_key)
    user.mark_login()
    refresh_token, family = sessions.start(user, user_agent=user_agent, ip=ip)
    audit.record(
        actor=user,
        action="auth.login",
        target_type="session",
        target_id=family.pk,
        ip=ip,
        user_agent=user_agent,
    )
    return LoginResult(user, tokens.issue_access_token(user), refresh_token)


def refresh(*, raw_refresh_token: str, ip: str) -> LoginResult:
    user, new_refresh = sessions.rotate(raw_refresh_token, ip=ip)
    return LoginResult(user, tokens.issue_access_token(user), new_refresh)


def logout(*, raw_refresh_token: str) -> None:
    family = sessions.family_for_token(raw_refresh_token)
    if family is not None:
        sessions.revoke(family, "logout")


# --- Sessions --------------------------------------------------------------------


def list_sessions(user: User) -> Any:
    now = timezone.now()
    return RefreshTokenFamily.objects.filter(
        user=user, revoked_at__isnull=True, expires_at__gt=now
    ).order_by("-last_used_at")


def revoke_session(user: User, session_id: UUID) -> bool:
    """Revoke one of the user's own sessions. False when it is not theirs."""
    family = RefreshTokenFamily.objects.filter(pk=session_id, user=user).first()
    if family is None:
        return False
    sessions.revoke(family, "revoked_by_user")
    return True


def session_expiry(raw_refresh_token: str) -> datetime | None:
    family = sessions.family_for_token(raw_refresh_token)
    return family.expires_at if family else None


# Admin member commands live in ``membership``; re-exported so other modules use one facade.
from apps.accounts.membership import (  # noqa: E402
    approve_member,
    reinstate_member,
    reject_registration,
    remove_member,
    suspend_member,
)

__all__ = [
    "approve_member",
    "reinstate_member",
    "reject_registration",
    "remove_member",
    "suspend_member",
]
