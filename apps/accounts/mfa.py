"""TOTP multi-factor authentication for admin accounts.

Secrets are encrypted at rest. A code is accepted once: the highest time step
already used is stored, so a captured code cannot be replayed inside its
30 second window. Failures are counted per account and lock the account out of
code checks for a while.
"""

import hashlib
import hmac
import secrets
import time
from uuid import UUID

import pyotp
from django.conf import settings
from django.core import signing
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone
from rest_framework import exceptions

from apps.accounts import sessions
from apps.accounts.models import BLOCKED_STATUSES, MfaDevice, RecoveryCode, User
from apps.audit import services as audit
from apps.core import crypto, ratelimit
from apps.core.errors import ConflictError
from apps.core.rbac import ADMIN_ROLES

TIME_STEP = 30
CHALLENGE_SALT = "accounts.mfa.challenge"


class InvalidMfaCode(exceptions.ValidationError):
    def __init__(self) -> None:
        super().__init__({"code": ["That code is not valid."]}, code="invalid_mfa_code")


class InvalidMfaChallenge(exceptions.APIException):
    status_code = 401
    default_detail = "The sign-in step expired. Log in again."
    default_code = "invalid_mfa_challenge"


class NotEnrolling(exceptions.ValidationError):
    def __init__(self) -> None:
        super().__init__({"code": ["Start MFA enrolment first."]}, code="mfa_not_started")


# --- state ---


def has_confirmed_device(user: User) -> bool:
    return MfaDevice.objects.filter(user=user, confirmed_at__isnull=False).exists()


def is_admin(user: User) -> bool:
    return bool(set(user.role_names()) & {role.value for role in ADMIN_ROLES})


def enrolment_required(user: User) -> bool:
    """Admins must enrol before they can use any admin endpoint."""
    return is_admin(user) and not has_confirmed_device(user)


# --- code checking ---


def _failure_key(user: User) -> str:
    return f"mfafail:{user.pk}"


def _guard(user: User) -> None:
    if ratelimit.current(_failure_key(user)) >= settings.MFA_MAX_FAILURES:
        raise exceptions.Throttled(wait=settings.MFA_FAILURE_WINDOW_SECONDS)


def _is_totp_shape(code: str) -> bool:
    return len(code) == 6 and code.isdigit()


def _match_totp(device: MfaDevice, code: str) -> bool:
    """Check a code against the device. The caller holds a lock on the row."""
    totp = pyotp.TOTP(crypto.decrypt(device.secret_encrypted), interval=TIME_STEP)
    current = int(time.time()) // TIME_STEP
    matched: int | None = None
    for step in (current - 1, current, current + 1):
        # Compare every candidate so timing does not reveal which step matched.
        if hmac.compare_digest(totp.at(step * TIME_STEP), code) and step > device.last_used_step:
            matched = step
    if matched is None:
        return False
    device.last_used_step = matched
    device.save(update_fields=["last_used_step", "updated_at"])
    return True


def _normalise_recovery(code: str) -> str:
    return code.replace("-", "").replace(" ", "").lower()


def _recovery_digest(code: str) -> str:
    return hashlib.sha256(_normalise_recovery(code).encode()).hexdigest()


def _use_recovery_code(user: User, code: str) -> bool:
    updated = RecoveryCode.objects.filter(
        user=user, code_hash=_recovery_digest(code), used_at__isnull=True
    ).update(used_at=timezone.now())
    return updated == 1


def _record_failure(user: User, ip: str) -> None:
    ratelimit.hit(_failure_key(user), settings.MFA_FAILURE_WINDOW_SECONDS)
    audit.record(actor=user, action="mfa.failed", target_type="user", target_id=user.pk, ip=ip)


def verify_code(user: User, code: str, *, ip: str = "", allow_recovery: bool = True) -> str:
    """Accept a TOTP code or an unused recovery code. Returns the method used."""
    _guard(user)
    cleaned = code.strip().replace(" ", "")
    method: str | None = None
    if _is_totp_shape(cleaned):
        with transaction.atomic():
            device = (
                MfaDevice.objects.select_for_update()
                .filter(user=user, confirmed_at__isnull=False)
                .first()
            )
            if device is not None and _match_totp(device, cleaned):
                method = "totp"
    elif allow_recovery and _use_recovery_code(user, cleaned):
        method = "recovery"
    if method is None:
        _record_failure(user, ip)
        raise InvalidMfaCode()
    ratelimit.reset(_failure_key(user))
    if method == "recovery":
        audit.record(
            actor=user, action="mfa.recovery_used", target_type="user", target_id=user.pk, ip=ip
        )
    return method


# --- enrolment ---


def begin_enrolment(user: User, *, ip: str = "") -> tuple[str, str]:
    """Create (or restart) an unconfirmed device. Returns ``(secret, otpauth_uri)``."""
    secret = pyotp.random_base32()
    with transaction.atomic():
        device = MfaDevice.objects.select_for_update().filter(user=user).first()
        if device is not None and device.confirmed_at is not None:
            raise ConflictError("MFA is already set up.", code="mfa_already_enrolled")
        encrypted = crypto.encrypt(secret)
        if device is None:
            MfaDevice.objects.create(user=user, secret_encrypted=encrypted)
        else:
            device.secret_encrypted = encrypted
            device.last_used_step = 0
            device.save(update_fields=["secret_encrypted", "last_used_step", "updated_at"])
        audit.record(
            actor=user, action="mfa.enrolment_started", target_type="user", target_id=user.pk, ip=ip
        )
    uri = pyotp.TOTP(secret).provisioning_uri(name=user.email, issuer_name=settings.MFA_ISSUER)
    return secret, uri


def _issue_recovery_codes(user: User) -> list[str]:
    """Replace the user's recovery codes and return the new ones, shown once."""
    RecoveryCode.objects.filter(user=user).delete()
    codes: list[str] = []
    for _ in range(settings.MFA_RECOVERY_CODE_COUNT):
        raw = secrets.token_hex(6)
        codes.append(f"{raw[:6]}-{raw[6:]}")
    RecoveryCode.objects.bulk_create(
        RecoveryCode(user=user, code_hash=_recovery_digest(code)) for code in codes
    )
    return codes


def confirm_enrolment(user: User, code: str, *, session_id: UUID | None, ip: str = "") -> list[str]:
    """Prove the authenticator works, switch MFA on and return recovery codes."""
    _guard(user)
    cleaned = code.strip().replace(" ", "")
    codes: list[str] | None = None
    with transaction.atomic():
        device = (
            MfaDevice.objects.select_for_update()
            .filter(user=user, confirmed_at__isnull=True)
            .first()
        )
        if device is None:
            raise NotEnrolling()
        if _is_totp_shape(cleaned) and _match_totp(device, cleaned):
            device.confirmed_at = timezone.now()
            device.save(update_fields=["confirmed_at", "updated_at"])
            codes = _issue_recovery_codes(user)
            if session_id is not None:
                sessions.mark_mfa_verified(session_id, user)
            audit.record(
                actor=user, action="mfa.enrolled", target_type="user", target_id=user.pk, ip=ip
            )
    if codes is None:
        _record_failure(user, ip)
        raise InvalidMfaCode()
    ratelimit.reset(_failure_key(user))
    return codes


def regenerate_recovery_codes(user: User, code: str, *, ip: str = "") -> list[str]:
    """Issue a fresh set of recovery codes. Needs a current authenticator code."""
    verify_code(user, code, ip=ip, allow_recovery=False)
    with transaction.atomic():
        codes = _issue_recovery_codes(user)
        audit.record(
            actor=user,
            action="mfa.recovery_codes_regenerated",
            target_type="user",
            target_id=user.pk,
            ip=ip,
        )
    return codes


# --- login challenge ---


def issue_challenge(user: User) -> str:
    """A short lived signed token proving the password step succeeded."""
    return signing.dumps({"uid": str(user.pk), "n": secrets.token_hex(8)}, salt=CHALLENGE_SALT)


def redeem_challenge(token: str) -> tuple[User, str]:
    try:
        data = signing.loads(token, salt=CHALLENGE_SALT, max_age=settings.MFA_CHALLENGE_TTL_SECONDS)
        user = User.objects.filter(pk=data["uid"]).first()
    except (signing.BadSignature, KeyError, ValueError) as exc:
        raise InvalidMfaChallenge() from exc
    if user is None or user.status in BLOCKED_STATUSES:
        raise InvalidMfaChallenge()
    return user, str(data["n"])


def burn_challenge(nonce: str) -> None:
    """Make a challenge single use. Called only after the code was accepted."""
    ttl = settings.MFA_CHALLENGE_TTL_SECONDS + 60
    if not cache.add(f"mfa:nonce:{nonce}", 1, ttl):
        raise InvalidMfaChallenge()
