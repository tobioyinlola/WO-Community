"""Support requests: opening one, the conversation, and how it moves between states.

Every change that matters runs in one transaction with the ticket row locked, so two admins
answering at once, or a member replying while a request is being resolved, cannot leave it in a
state that does not match its messages. Members are told in the app and by email; admins in the
app. Nothing here is sent by email in the other direction: people reply inside the product.
"""

import html
import re
from datetime import timedelta
from typing import Any
from uuid import UUID

from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone
from rest_framework import exceptions

from apps.accounts import selectors as accounts
from apps.accounts.models import User
from apps.analytics import services as analytics
from apps.audit import services as audit
from apps.core.rbac import permissions_for
from apps.core.text import plain, rich_post, text_of
from apps.notifications import adminalerts, emails, notify
from apps.support import domain
from apps.support.models import SupportAttachment, SupportCannedReply, SupportMessage, SupportTicket
from apps.uploads import services as uploads
from apps.uploads.models import UploadPurpose

ADMIN_ROLES = ["community_admin", "super_admin"]
EXCERPT = 600


class Conflict(exceptions.APIException):
    status_code = 409
    default_code = "conflict"


def _fail(field: str, message: str) -> exceptions.ValidationError:
    return exceptions.ValidationError({field: [message]})


# --- text ---


def paragraphs(text: str) -> str:
    """A member's plain words as safe HTML: blank lines split paragraphs, others break lines."""
    blocks = [b for b in re.split(r"\n\s*\n", text.strip()) if b.strip()]
    return "".join(f"<p>{html.escape(b.strip()).replace(chr(10), '<br>')}</p>" for b in blocks)


def _excerpt(text: str) -> str:
    return text if len(text) <= EXCERPT else text[: EXCERPT - 1].rstrip() + "…"


# --- opening ---


def _next_number() -> int:
    with connection.cursor() as cursor:
        cursor.execute("SELECT nextval('support_ticket_number_seq')")
        return int(cursor.fetchone()[0])


def _attach(message: SupportMessage, owner_id: UUID, upload_ids: list[UUID]) -> None:
    if len(upload_ids) > domain.MAX_ATTACHMENTS:
        raise _fail("attachments", f"Attach at most {domain.MAX_ATTACHMENTS} files.")
    for upload_id in upload_ids:
        upload = uploads.claim(
            upload_id=upload_id, owner_id=owner_id, purpose=UploadPurpose.SUPPORT_ATTACHMENT.value
        )
        SupportAttachment.objects.create(
            message=message,
            upload=upload,
            storage_key=upload.base_key,
            filename=(upload.original_filename or "attachment")[:255],
            size=upload.size or upload.declared_size,
            content_type=upload.declared_content_type,
        )


def _tell_admins(ticket: SupportTicket, kind: str, *, only: list[UUID] | None = None) -> None:
    """Tell the admins who can act on it: the assignee if there is one, else everyone on support."""
    recipients = only or [UUID(str(i)) for i in accounts.ids_with_roles(ADMIN_ROLES).distinct()]
    for admin_id in recipients:
        notify.notify(
            admin_id,
            kind,
            {"ticket_id": str(ticket.pk), "reference": ticket.reference},
            dedupe_key=f"{kind}:{ticket.pk}:{int(ticket.last_activity_at.timestamp() * 1000)}",
        )


@transaction.atomic
def create_ticket(
    *,
    member: User | None,
    name: str,
    email: str,
    category: str,
    subject: str,
    message: str,
    upload_ids: list[UUID] | None = None,
    idempotency_key: str = "",
) -> SupportTicket:
    """Open a request. Sending the same form again (same key) returns the first request."""
    if idempotency_key and member is not None:
        first = SupportTicket.objects.filter(member=member, idempotency_key=idempotency_key).first()
        if first is not None:
            return first
    text = plain(message)
    now = timezone.now()
    ticket = SupportTicket.objects.create(
        number=_next_number(),
        member=member,
        name=plain(name)[:120],
        email=email,
        category=category,
        subject=plain(subject),
        last_activity_at=now,
        idempotency_key=idempotency_key,
    )
    first_message = SupportMessage.objects.create(
        ticket=ticket,
        author_type="member",
        author=member,
        body=paragraphs(text),
        body_text=text,
    )
    if upload_ids:
        if member is None:
            raise _fail("attachments", "Sign in to attach files.")
        _attach(first_message, member.pk, upload_ids)
    analytics.track(
        "support_ticket_created",
        actor_id=member.pk if member else None,
        properties={"category": category},
    )
    _tell_admins(ticket, "ticket_new")
    adminalerts.raise_alert(
        "support_ticket",
        item_key=f"ticket:{ticket.pk}",
        what=f"{ticket.reference}: {ticket.subject}",
        who=email,
        path=f"/admin/support?ticket={ticket.pk}",
        in_app=False,
    )
    if member is not None:
        emails.send_templated(
            email,
            "ticket_received",
            {
                "reference": ticket.reference,
                "subject": ticket.subject,
                "ticket_url": f"{settings.FRONTEND_BASE_URL}/support/{ticket.pk}",
            },
            category="notification_ticket_received",
            no_reply=True,
            with_preferences=True,
        )
    if member is None:
        emails.send_support_mail(
            email,
            f"We received your request {ticket.reference}",
            "Thank you for getting in touch. A member of the team will reply to this address.\n\n"
            "Please do not reply to this message; we will write to you from the team.",
        )
    return ticket


# --- the conversation ---


def _locked(ticket_id: UUID) -> SupportTicket:
    return SupportTicket.objects.select_for_update().get(pk=ticket_id)


@transaction.atomic
def add_member_message(
    *, ticket_id: UUID, member: User, message: str, upload_ids: list[UUID] | None = None
) -> SupportMessage:
    ticket = _locked(ticket_id)
    if ticket.member_id != member.pk:
        raise exceptions.NotFound()
    if ticket.status == "resolved":
        raise Conflict("This request is resolved. Reopen it to reply.")
    text = plain(message)
    row = SupportMessage.objects.create(
        ticket=ticket, author_type="member", author=member, body=paragraphs(text), body_text=text
    )
    if upload_ids:
        _attach(row, member.pk, upload_ids)
    # Once support has answered, a reply puts it back in front of them as work in progress.
    ticket.status = "in_progress" if ticket.first_response_at else "open"
    ticket.last_activity_at = row.created_at
    ticket.save(update_fields=["status", "last_activity_at", "updated_at"])
    _tell_admins(
        ticket,
        "ticket_member_reply",
        only=[ticket.assignee_id] if ticket.assignee_id else None,
    )
    return row


def _can_support(user_id: UUID | None) -> bool:
    user = User.objects.filter(pk=user_id, status="active").first() if user_id else None
    return user is not None and "support.manage" in permissions_for(user.role_names())


@transaction.atomic
def add_admin_message(
    *,
    ticket_id: UUID,
    admin: User,
    body: str,
    internal: bool = False,
    status: str = "awaiting_member",
    upload_ids: list[UUID] | None = None,
) -> SupportMessage:
    """A reply to the member, or (with ``internal``) a note only admins see."""
    ticket = _locked(ticket_id)
    cleaned = rich_post(body)
    words = text_of(cleaned)
    if not words:
        raise _fail("body", "Write something first.")
    if len(words) > domain.MESSAGE_MAX:
        raise _fail("body", f"Keep it under {domain.MESSAGE_MAX} characters.")
    if not internal and status not in ("in_progress", "awaiting_member", "resolved"):
        raise _fail("status", "Choose in progress, awaiting the member, or resolved.")
    row = SupportMessage.objects.create(
        ticket=ticket,
        author_type="admin",
        author=admin,
        body=cleaned,
        body_text=words,
        is_internal=internal,
    )
    if upload_ids:
        _attach(row, admin.pk, upload_ids)
    if internal:
        return row
    if ticket.status == "resolved" and status != "resolved":
        ticket.resolved_at = None
        ticket.resolved_by = None
    now = row.created_at
    before = ticket.status
    ticket.status = status
    ticket.last_activity_at = now
    if ticket.first_response_at is None:
        ticket.first_response_at = now
    if ticket.assignee_id is None:
        ticket.assignee = admin
    if status == "resolved":
        ticket.resolved_at, ticket.resolved_by = now, admin
    ticket.save()
    if before != status:
        audit.record(
            actor=admin,
            action="support.ticket.status_changed",
            target_type="support_ticket",
            target_id=ticket.pk,
            before={"status": before},
            after={"status": status},
        )
    if ticket.member_id is None:
        # Nobody to open the request in the app, so the answer itself goes by email.
        emails.send_support_mail(
            ticket.email,
            f"{ticket.reference}: "
            + ("marked as resolved" if status == "resolved" else "a reply from WO Community"),
            words,
        )
    else:
        notify.notify(
            ticket.member_id,
            "ticket_resolved" if status == "resolved" else "ticket_reply",
            {
                "ticket_id": str(ticket.pk),
                "reference": ticket.reference,
                "actor_id": str(admin.pk),
                "excerpt": _excerpt(words),
            },
            dedupe_key=f"ticket-reply:{row.pk}",
        )
    if status == "resolved":
        _record_resolved(ticket)
    return row


def _record_resolved(ticket: SupportTicket) -> None:
    hours = (
        int((ticket.resolved_at - ticket.created_at).total_seconds() // 3600)
        if ticket.resolved_at
        else 0
    )
    analytics.track(
        "support_ticket_resolved",
        actor_id=ticket.resolved_by_id,
        properties={"category": ticket.category, "hours": min(hours, 100_000)},
    )


# --- state changes ---


@transaction.atomic
def update_ticket(*, ticket_id: UUID, admin: User, changes: dict[str, Any]) -> SupportTicket:
    """Change status, assignee, priority or category. Status and assignee are audited."""
    ticket = _locked(ticket_id)
    before = {"status": ticket.status, "assignee": str(ticket.assignee_id or "")}
    now = timezone.now()
    if "category" in changes:
        ticket.category = changes["category"]
    if "priority" in changes:
        ticket.priority = changes["priority"]
    if "assignee" in changes:
        assignee_id = changes["assignee"]
        if assignee_id is not None and not _can_support(assignee_id):
            raise _fail("assignee", "Choose someone who handles support.")
        ticket.assignee_id = assignee_id
    if "status" in changes and changes["status"] != ticket.status:
        new = changes["status"]
        if new == "resolved":
            ticket.resolved_at, ticket.resolved_by = now, admin
        elif ticket.status == "resolved":
            ticket.resolved_at, ticket.resolved_by = None, None
        ticket.status = new
        ticket.last_activity_at = now
    ticket.save()
    after = {"status": ticket.status, "assignee": str(ticket.assignee_id or "")}
    if before != after:
        audit.record(
            actor=admin,
            action="support.ticket.updated",
            target_type="support_ticket",
            target_id=ticket.pk,
            before=before,
            after=after,
        )
    if before["status"] != "resolved" and ticket.status == "resolved":
        _record_resolved(ticket)
        if ticket.member_id:
            notify.notify(
                ticket.member_id,
                "ticket_resolved",
                {
                    "ticket_id": str(ticket.pk),
                    "reference": ticket.reference,
                    "actor_id": str(admin.pk),
                },
                dedupe_key=f"ticket-resolved:{ticket.pk}:{int(now.timestamp())}",
            )
    return ticket


def resolve(*, ticket_id: UUID, admin: User) -> SupportTicket:
    return update_ticket(ticket_id=ticket_id, admin=admin, changes={"status": "resolved"})


@transaction.atomic
def reopen(*, ticket_id: UUID, actor: User, by_member: bool) -> SupportTicket:
    """A member may reopen within 14 days of resolution; an admin may reopen any time."""
    ticket = _locked(ticket_id)
    if by_member and ticket.member_id != actor.pk:
        raise exceptions.NotFound()
    if ticket.status != "resolved" or ticket.resolved_at is None:
        raise Conflict("This request is not resolved.")
    if by_member and timezone.now() - ticket.resolved_at > timedelta(days=domain.REOPEN_DAYS):
        raise Conflict(
            f"Requests can be reopened for {domain.REOPEN_DAYS} days after they are resolved."
        )
    ticket.status = "in_progress" if ticket.first_response_at else "open"
    ticket.resolved_at, ticket.resolved_by = None, None
    ticket.reopened_count += 1
    ticket.last_activity_at = timezone.now()
    ticket.save()
    audit.record(
        actor=actor,
        action="support.ticket.reopened",
        target_type="support_ticket",
        target_id=ticket.pk,
        before={"status": "resolved"},
        after={"status": ticket.status},
    )
    if by_member:
        _tell_admins(
            ticket, "ticket_member_reply", only=[ticket.assignee_id] if ticket.assignee_id else None
        )
    return ticket


@transaction.atomic
def give_feedback(
    *, ticket_id: UUID, member: User, satisfaction: str, comment: str
) -> SupportTicket:
    ticket = _locked(ticket_id)
    if ticket.member_id != member.pk:
        raise exceptions.NotFound()
    if ticket.status != "resolved":
        raise Conflict("You can rate a request once it is resolved.")
    ticket.satisfaction = satisfaction
    ticket.satisfaction_comment = plain(comment)[:500]
    ticket.save(update_fields=["satisfaction", "satisfaction_comment", "updated_at"])
    return ticket


# --- attachments ---


def attachment_link(attachment: SupportAttachment) -> tuple[str, int]:
    """A short lived address that downloads the file as an attachment."""
    return uploads.document_link(
        key=attachment.storage_key,
        filename=attachment.filename,
        content_type=attachment.content_type,
    )


# --- canned replies ---


def save_canned(*, reply: SupportCannedReply | None, data: dict[str, Any]) -> SupportCannedReply:
    body = rich_post(data["body"])
    if not text_of(body):
        raise _fail("body", "Write the reply.")
    fields = {
        "title": plain(data["title"]),
        "body": body,
        "category": data.get("category", ""),
        "active": data.get("active", True),
    }
    if reply is None:
        return SupportCannedReply.objects.create(**fields)
    for key, value in fields.items():
        setattr(reply, key, value)
    reply.save()
    return reply


def sla_hours() -> int:
    return int(settings.SUPPORT_SLA_HOURS)
