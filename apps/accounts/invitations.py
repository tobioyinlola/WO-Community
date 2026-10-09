"""Admin invitations: create, bulk import, resend, revoke, inspect and redeem.

An invitation's token is made when its email is built and only the hash is
kept, so the raw link exists in the email alone. A valid token that matches
the invited address lets that person register without waiting for approval.
"""

import csv
import hashlib
import io
import secrets
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import exceptions

from apps.accounts import events
from apps.accounts.exceptions import InvalidToken
from apps.accounts.models import INVITABLE_ROLES, Invitation, InvitationStatus, User
from apps.audit import services as audit
from apps.core import events as domain_events
from apps.core.errors import ConflictError

OPEN_STATUSES = (InvitationStatus.SENT, InvitationStatus.OPENED)
CSV_COLUMNS = {"email", "role", "message"}


@dataclass(frozen=True)
class InvitationEmail:
    to: str
    token: str
    message: str
    expires_at: Any


@dataclass
class BulkReport:
    created: int = 0
    skipped: int = 0
    rows: list[dict[str, Any]] = field(default_factory=list)


def _new_nonce() -> str:
    return secrets.token_hex(8)


def _digest(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def effective_status(invitation: Invitation) -> str:
    """The status shown to admins: an unused invitation past its expiry is ``expired``."""
    if invitation.status in OPEN_STATUSES and invitation.expires_at <= timezone.now():
        return "expired"
    return str(invitation.status)


def clean_message(message: str) -> str:
    """Trim and drop control characters; keep line breaks."""
    cleaned = "".join(ch for ch in message if ch == "\n" or (ch >= " " and ch != "\x7f"))
    return cleaned.strip()


def _validate_role(role: str) -> str:
    if role not in INVITABLE_ROLES:
        allowed = ", ".join(INVITABLE_ROLES)
        raise exceptions.ValidationError({"role": [f"Choose one of: {allowed}."]})
    return role


def _validate_message(message: str) -> str:
    cleaned = clean_message(message)
    if len(cleaned) > settings.INVITATION_MAX_MESSAGE_LENGTH:
        raise exceptions.ValidationError(
            {"message": [f"Keep it under {settings.INVITATION_MAX_MESSAGE_LENGTH} characters."]}
        )
    return cleaned


def _validate_email(email: str) -> str:
    address = email.strip().lower()
    try:
        validate_email(address)
    except DjangoValidationError as exc:
        raise exceptions.ValidationError({"email": ["Enter a valid email address."]}) from exc
    return address


def _revoke(invitation: Invitation, reason: str) -> None:
    invitation.status = InvitationStatus.REVOKED
    invitation.revoked_at = timezone.now()
    invitation.token_hash = None
    invitation.save(update_fields=["status", "revoked_at", "token_hash", "updated_at"])
    audit.record(
        actor=None,
        action="invitation.revoked",
        target_type="invitation",
        target_id=invitation.pk,
        reason=reason,
    )


def create_invitation(
    *, actor: User, email: str, role: str = "member", message: str = "", ip: str = ""
) -> Invitation:
    address = _validate_email(email)
    role = _validate_role(role)
    message = _validate_message(message)
    try:
        with transaction.atomic():
            if User.objects.filter(email__iexact=address).exists():
                raise ConflictError(
                    "This address already has an account.", code="already_registered"
                )
            live = (
                Invitation.objects.select_for_update()
                .filter(email__iexact=address, status__in=OPEN_STATUSES)
                .first()
            )
            if live is not None:
                if live.expires_at > timezone.now():
                    raise ConflictError(
                        "This address already has a live invitation. Resend it instead.",
                        code="already_invited",
                    )
                _revoke(live, "superseded")
            invitation = Invitation.objects.create(
                email=address,
                role=role,
                message=message,
                invited_by=actor,
                expires_at=timezone.now() + settings.INVITATION_TTL,
                send_nonce=_new_nonce(),
            )
            domain_events.publish(
                events.InvitationRequested(
                    invitation_id=str(invitation.pk), nonce=invitation.send_nonce
                )
            )
            audit.record(
                actor=actor,
                action="invitation.created",
                target_type="invitation",
                target_id=invitation.pk,
                after={"role": role},
                ip=ip,
            )
            return invitation
    except IntegrityError as exc:  # a concurrent request created the live invitation first
        raise ConflictError(
            "This address already has a live invitation. Resend it instead.",
            code="already_invited",
        ) from exc


def _lock(invitation_id: UUID) -> Invitation:
    invitation = Invitation.objects.select_for_update().filter(pk=invitation_id).first()
    if invitation is None:
        raise exceptions.NotFound()
    return invitation


def resend_invitation(*, actor: User, invitation_id: UUID, ip: str = "") -> Invitation:
    """New link, fresh expiry. The previous link stops working immediately."""
    with transaction.atomic():
        invitation = _lock(invitation_id)
        if invitation.status not in OPEN_STATUSES:
            raise ConflictError(
                f"Cannot resend an invitation that is {invitation.status}.",
                code="invalid_transition",
            )
        if User.objects.filter(email__iexact=invitation.email).exists():
            raise ConflictError("This address already has an account.", code="already_registered")
        invitation.status = InvitationStatus.SENT
        invitation.token_hash = None
        invitation.opened_at = None
        invitation.expires_at = timezone.now() + settings.INVITATION_TTL
        invitation.send_nonce = _new_nonce()
        invitation.save(
            update_fields=[
                "status",
                "token_hash",
                "opened_at",
                "expires_at",
                "send_nonce",
                "updated_at",
            ]
        )
        domain_events.publish(
            events.InvitationRequested(
                invitation_id=str(invitation.pk), nonce=invitation.send_nonce
            )
        )
        audit.record(
            actor=actor,
            action="invitation.resent",
            target_type="invitation",
            target_id=invitation.pk,
            ip=ip,
        )
        return invitation


def revoke_invitation(*, actor: User, invitation_id: UUID, ip: str = "") -> Invitation:
    with transaction.atomic():
        invitation = _lock(invitation_id)
        if invitation.status not in OPEN_STATUSES:
            raise ConflictError(
                f"Cannot revoke an invitation that is {invitation.status}.",
                code="invalid_transition",
            )
        _revoke(invitation, "revoked by admin")
        audit.record(
            actor=actor,
            action="invitation.revoked_by_admin",
            target_type="invitation",
            target_id=invitation.pk,
            ip=ip,
        )
        return invitation


def issue_token(invitation_id: UUID, nonce: str) -> InvitationEmail | None:
    """Make the link for an invitation email. None when nothing should be sent.

    Call and send inside one transaction: if sending fails the link is rolled
    back and a retry makes it again. A request superseded by a newer resend, or
    one whose link already exists, sends nothing.
    """
    with transaction.atomic():
        invitation = Invitation.objects.select_for_update().filter(pk=invitation_id).first()
        if (
            invitation is None
            or invitation.send_nonce != nonce
            or invitation.token_hash is not None
            or invitation.status not in OPEN_STATUSES
            or invitation.expires_at <= timezone.now()
        ):
            return None
        raw = secrets.token_urlsafe(32)
        invitation.token_hash = _digest(raw)
        invitation.last_sent_at = timezone.now()
        invitation.save(update_fields=["token_hash", "last_sent_at", "updated_at"])
        return InvitationEmail(invitation.email, raw, invitation.message, invitation.expires_at)


def find_open(raw_token: str) -> Invitation | None:
    """A live invitation for this token, or None. Does not change anything."""
    if not raw_token:
        return None
    return Invitation.objects.filter(
        token_hash=_digest(raw_token),
        status__in=OPEN_STATUSES,
        expires_at__gt=timezone.now(),
    ).first()


def inspect(raw_token: str) -> Invitation:
    """What the registration page needs to prefill, and note that the link was opened."""
    with transaction.atomic():
        found = find_open(raw_token)
        if found is None:
            raise InvalidToken()
        invitation = Invitation.objects.select_for_update().get(pk=found.pk)
        if invitation.status == InvitationStatus.SENT:
            invitation.status = InvitationStatus.OPENED
            invitation.opened_at = timezone.now()
            invitation.save(update_fields=["status", "opened_at", "updated_at"])
        return invitation


def lock_for_registration(raw_token: str, address: str) -> Invitation | None:
    """Lock the invitation if the token is live and was issued to ``address``.

    Call inside the registration transaction. A token for a different address
    is treated as no invitation at all.
    """
    found = find_open(raw_token)
    if found is None or found.email.lower() != address:
        return None
    return (
        Invitation.objects.select_for_update()
        .filter(pk=found.pk, status__in=OPEN_STATUSES, expires_at__gt=timezone.now())
        .first()
    )


def mark_registered(invitation: Invitation, user: User) -> None:
    invitation.status = InvitationStatus.REGISTERED
    invitation.registered_at = timezone.now()
    invitation.accepted_by = user
    invitation.token_hash = None
    invitation.save(
        update_fields=["status", "registered_at", "accepted_by", "token_hash", "updated_at"]
    )


# --- bulk import ---------------------------------------------------------------------


def _read_rows(text: str) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    names = [(name or "").strip().lower() for name in (reader.fieldnames or [])]
    if "email" not in names:
        raise exceptions.ValidationError({"csv": ["The first row must name an email column."]})
    unknown = sorted(set(names) - CSV_COLUMNS)
    if unknown:
        raise exceptions.ValidationError(
            {"csv": [f"Unknown column(s): {', '.join(unknown)}. Use email, role, message."]}
        )
    reader.fieldnames = names
    rows: list[dict[str, Any]] = []
    for row in reader:
        rows.append(row)
        if len(rows) > settings.INVITATION_BULK_MAX_ROWS:
            raise exceptions.ValidationError(
                {"csv": [f"At most {settings.INVITATION_BULK_MAX_ROWS} rows per upload."]}
            )
    if not rows:
        raise exceptions.ValidationError({"csv": ["The file has no rows."]})
    return rows


def _message_of(error: exceptions.APIException) -> str:
    detail = error.detail
    if isinstance(detail, dict):
        first = next(iter(detail.values()))
        return str(first[0] if isinstance(first, list) else first)
    return str(detail[0]) if isinstance(detail, list) else str(detail)


def bulk_create(*, actor: User, csv_text: str, ip: str = "") -> BulkReport:
    """Invite everyone in a CSV. Bad rows are reported and do not stop the rest."""
    if len(csv_text.encode()) > settings.INVITATION_BULK_MAX_BYTES:
        raise exceptions.ValidationError({"csv": ["The file is too large."]})
    report = BulkReport()
    seen: set[str] = set()
    for number, row in enumerate(_read_rows(csv_text), start=2):  # row 1 is the header
        email = (row.get("email") or "").strip().lower()
        entry: dict[str, Any] = {"row": number, "email": email}
        try:
            if None in row:
                raise exceptions.ValidationError({"row": ["Too many columns."]})
            if email in seen:
                raise ConflictError("Duplicate address in this file.", code="duplicate_in_file")
            seen.add(email)
            create_invitation(
                actor=actor,
                email=email,
                role=(row.get("role") or "member").strip().lower(),
                message=row.get("message") or "",
                ip=ip,
            )
        except (exceptions.ValidationError, ConflictError) as exc:
            report.skipped += 1
            entry.update(result="skipped", reason=_message_of(exc))
        else:
            report.created += 1
            entry.update(result="created", reason="")
        report.rows.append(entry)
    audit.record(
        actor=actor,
        action="invitation.bulk_imported",
        after={"created": report.created, "skipped": report.skipped},
        ip=ip,
    )
    return report
