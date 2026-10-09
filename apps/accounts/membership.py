"""Admin commands that change a member's standing.

Every command locks the target row, checks the state machine, writes the
change, an audit entry with before and after values, and a domain event, all
in one transaction. Callers have already been authorised by a policy; the
checks here are business rules that hold whoever is asking.
"""

from typing import Any
from uuid import UUID

from django.db import transaction
from django.utils import timezone
from rest_framework import exceptions

from apps.accounts import events, sessions, tokens
from apps.accounts.models import ApprovalSource, User, UserRole, UserStatus
from apps.audit import services as audit
from apps.core import events as domain_events
from apps.core.errors import ConflictError
from apps.core.rbac import ADMIN_ROLES, Role, permissions_for

# action -> statuses the account may be in for the action to apply
_ALLOWED_FROM: dict[str, tuple[str, ...]] = {
    "approve": (UserStatus.PENDING,),
    "reject": (UserStatus.PENDING,),
    "suspend": (UserStatus.ACTIVE,),
    "reinstate": (UserStatus.SUSPENDED,),
    "remove": (
        UserStatus.PENDING,
        UserStatus.ACTIVE,
        UserStatus.SUSPENDED,
        UserStatus.REJECTED,
    ),
}


def _lock_target(actor: User, user_id: UUID) -> User:
    if actor.pk == user_id:
        raise exceptions.PermissionDenied("You cannot change your own account.")
    target = User.objects.select_for_update().filter(pk=user_id).first()
    if target is None:
        raise exceptions.NotFound()
    target_is_admin = set(target.role_names()) & {role.value for role in ADMIN_ROLES}
    if target_is_admin and "roles.manage" not in permissions_for(actor.role_names()):
        raise exceptions.PermissionDenied("Only a super admin can change an admin account.")
    return target


def _check_transition(action: str, target: User) -> None:
    if target.status not in _ALLOWED_FROM[action]:
        raise ConflictError(
            f"Cannot {action} an account that is {target.status}.", code="invalid_transition"
        )


def _require_reason(reason: str) -> str:
    cleaned = reason.strip()
    if not cleaned:
        raise exceptions.ValidationError({"reason": ["A reason is required."]})
    return cleaned


def _apply(
    action: str,
    actor: User,
    target: User,
    new_status: str,
    reason: str,
    ip: str,
    event: Any = None,
) -> User:
    before = {"status": target.status}
    target.status = new_status
    target.status_reason = reason
    target.status_changed_at = timezone.now()
    target.status_changed_by = actor
    target.save(
        update_fields=[
            "status",
            "status_reason",
            "status_changed_at",
            "status_changed_by",
            "updated_at",
        ]
    )
    audit.record(
        actor=actor,
        action=f"member.{action}",
        target_type="user",
        target_id=target.pk,
        before=before,
        after={"status": new_status},
        reason=reason,
        ip=ip,
    )
    if event is not None:
        domain_events.publish(event)
    return target


def _cut_off(target: User) -> None:
    """End every session and make issued access tokens stop working."""
    sessions.revoke_all(target, "account_status_changed")
    target.bump_token_version()
    tokens.revoke_older_tokens(target)


def approve_member(*, actor: User, user_id: UUID, ip: str = "") -> User:
    with transaction.atomic():
        target = _lock_target(actor, user_id)
        _check_transition("approve", target)
        if target.email_verified_at is None:
            raise ConflictError(
                "The member has not confirmed their email address yet.",
                code="email_not_verified",
            )
        target.approved_at = timezone.now()
        target.approved_by = actor
        target.approval_source = ApprovalSource.ADMIN
        target.save(update_fields=["approved_at", "approved_by", "approval_source", "updated_at"])
        UserRole.objects.get_or_create(user=target, role=Role.MEMBER)
        target.__dict__.pop("_role_names", None)
        return _apply(
            "approve",
            actor,
            target,
            UserStatus.ACTIVE,
            "",
            ip,
            events.MemberApproved(user_id=str(target.pk)),
        )


def reject_registration(*, actor: User, user_id: UUID, reason: str, ip: str = "") -> User:
    reason = _require_reason(reason)
    with transaction.atomic():
        target = _lock_target(actor, user_id)
        _check_transition("reject", target)
        _apply(
            "reject",
            actor,
            target,
            UserStatus.REJECTED,
            reason,
            ip,
            events.MemberRejected(user_id=str(target.pk), reason=reason),
        )
        _cut_off(target)
        return target


def suspend_member(*, actor: User, user_id: UUID, reason: str, ip: str = "") -> User:
    reason = _require_reason(reason)
    with transaction.atomic():
        target = _lock_target(actor, user_id)
        _check_transition("suspend", target)
        _apply(
            "suspend",
            actor,
            target,
            UserStatus.SUSPENDED,
            reason,
            ip,
            events.MemberSuspended(user_id=str(target.pk)),
        )
        _cut_off(target)
        return target


def reinstate_member(*, actor: User, user_id: UUID, ip: str = "") -> User:
    with transaction.atomic():
        target = _lock_target(actor, user_id)
        _check_transition("reinstate", target)
        return _apply(
            "reinstate",
            actor,
            target,
            UserStatus.ACTIVE,
            "",
            ip,
            events.MemberReinstated(user_id=str(target.pk)),
        )


def remove_member(*, actor: User, user_id: UUID, reason: str, ip: str = "") -> User:
    """Take a member off the platform. Public pages must come down at once."""
    reason = _require_reason(reason)
    with transaction.atomic():
        target = _lock_target(actor, user_id)
        _check_transition("remove", target)
        _apply(
            "remove",
            actor,
            target,
            UserStatus.REMOVED,
            reason,
            ip,
            events.MemberRemoved(user_id=str(target.pk)),
        )
        _cut_off(target)
        return target
