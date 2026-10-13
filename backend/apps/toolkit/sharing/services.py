"""Share links: made with an unguessable token, checked in constant time, revocable.

The token is shown once when the link is made. Only its SHA-256 is stored, so a database leak
does not hand out working links. A revoked, expired or unknown token all look the same to the
caller (404 with no detail).
"""

import hashlib
import hmac
import secrets
from datetime import datetime
from typing import Any
from uuid import UUID

from django.contrib.auth.hashers import check_password, make_password
from django.db.models import F
from django.utils import timezone
from rest_framework import exceptions

from apps.audit import services as audit
from apps.toolkit.sharing.models import SUBJECT_TYPES, ShareLink
from apps.toolkit.ventures.models import Venture

TOKEN_BYTES = 24  # 192 bits


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create(
    *,
    venture: Venture,
    owner_id: UUID,
    subject_type: str,
    subject_id: UUID,
    password: str = "",
    expires_at: datetime | None = None,
) -> tuple[ShareLink, str]:
    """Returns the link and the raw token, which is not recoverable afterwards."""
    if subject_type not in SUBJECT_TYPES:
        raise exceptions.ValidationError({"subject_type": ["Unknown kind of share."]})
    if expires_at is not None and expires_at <= timezone.now():
        raise exceptions.ValidationError({"expires_at": ["Choose a time in the future."]})
    if password and not 4 <= len(password) <= 72:
        raise exceptions.ValidationError({"password": ["Between 4 and 72 characters."]})
    token = secrets.token_urlsafe(TOKEN_BYTES)
    link = ShareLink.objects.create(
        owner_id=owner_id,
        venture=venture,
        subject_type=subject_type,
        subject_id=subject_id,
        token_hash=_hash(token),
        password_hash=make_password(password) if password else "",
        expires_at=expires_at,
    )
    audit.record(
        actor=None,
        action="toolkit.share_created",
        target_type=subject_type,
        target_id=subject_id,
        after={"link": str(link.pk), "password": bool(password)},
    )
    return link, token


def revoke(*, link: ShareLink) -> None:
    link.revoked_at = timezone.now()
    link.save(update_fields=["revoked_at", "updated_at"])
    audit.record(
        actor=None,
        action="toolkit.share_revoked",
        target_type=link.subject_type,
        target_id=link.subject_id,
        after={"link": str(link.pk)},
    )


def find(token: str) -> ShareLink | None:
    """The live link for a token, or None for anything else, without saying why."""
    candidate = ShareLink.objects.filter(token_hash=_hash(token)).select_related("venture").first()
    if candidate is None:
        return None
    # Equal hashes were matched by the database; compare again in constant time regardless.
    if not hmac.compare_digest(candidate.token_hash, _hash(token)):
        return None
    now = timezone.now()
    if candidate.revoked_at is not None or candidate.venture.deleted_at is not None:
        return None
    if candidate.expires_at is not None and candidate.expires_at <= now:
        return None
    return candidate


def needs_password(link: ShareLink) -> bool:
    return bool(link.password_hash)


def password_ok(link: ShareLink, password: str) -> bool:
    if not link.password_hash:
        return True
    return check_password(password, link.password_hash)


def record_view(link: ShareLink) -> None:
    ShareLink.objects.filter(pk=link.pk).update(
        view_count=F("view_count") + 1, last_viewed_at=timezone.now()
    )


def view(link: ShareLink) -> dict[str, Any]:
    return {
        "id": link.pk,
        "subject_type": link.subject_type,
        "subject_id": link.subject_id,
        "has_password": bool(link.password_hash),
        "expires_at": link.expires_at,
        "revoked_at": link.revoked_at,
        "view_count": link.view_count,
        "last_viewed_at": link.last_viewed_at,
        "created_at": link.created_at,
    }


def for_subject(owner_id: UUID, subject_type: str, subject_id: UUID) -> list[ShareLink]:
    return list(
        ShareLink.objects.filter(
            owner_id=owner_id, subject_type=subject_type, subject_id=subject_id
        ).order_by("-created_at")
    )
