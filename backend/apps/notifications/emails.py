"""Transactional emails for account events and notifications.

Every message is multipart: the branded HTML and a plain text alternative built from the same
words (see ``mailtemplates``). The wording comes from the edited template if an admin changed it,
else from the built in copy.
"""

import hashlib
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import structlog
from django.conf import settings

from apps.integrations.email import (
    MARKETING,
    TRANSACTIONAL,
    EmailMessage,
    EmailRejected,
    get_email_adapter,
)
from apps.notifications import mailtemplates as mt
from apps.notifications import services, templatestore

logger = structlog.get_logger(__name__)


def _send(
    to: str,
    subject: str,
    body: str,
    *,
    category: str,
    stream: str = TRANSACTIONAL,
    no_reply: bool = False,
    html: str = "",
    headers: dict[str, str] | None = None,
    nonce: str = "",
) -> None:
    """Send one email.

    Marketing mail skips suppressed addresses. The idempotency key comes from
    the content, so a retry after a timeout cannot deliver the same message
    twice, and an identical message repeated within a day (for example a
    "you already have an account" notice someone keeps triggering) is sent once.
    A message the provider will never accept is dropped, since retrying cannot help.
    """
    if stream == MARKETING and services.is_suppressed(to):
        logger.info("email_skipped_suppressed", category=category)
        return
    key = hashlib.sha256(f"{to}\n{subject}\n{body}\n{nonce}".encode()).hexdigest()
    message = EmailMessage(
        to=to,
        subject=subject,
        text_body=body,
        html_body=html,
        stream=stream,
        headers=headers or {},
        idempotency_key=key,
        tags={"category": category},
        no_reply=no_reply,
    )
    try:
        get_email_adapter().send(message)
    except EmailRejected as exc:
        logger.warning(
            "email_rejected",
            category=category,
            code=exc.code,
            email_hash=services.hash_email(to)[:12],
        )


def preferences_url() -> str:
    return f"{settings.FRONTEND_BASE_URL}/app/settings"


def render_template(
    key: str,
    values: dict[str, Any],
    *,
    with_preferences: bool = True,
    copy: mt.Copy | None = None,
) -> mt.Rendered:
    """The email for a template, in the wording currently in force."""
    return mt.render(
        key,
        values,
        copy=copy or templatestore.effective_copy(key),
        preferences_url=preferences_url() if with_preferences else "",
    )


def send_rendered(
    to: str,
    rendered: mt.Rendered,
    *,
    category: str,
    subject_prefix: str = "",
    nonce: str = "",
    stream: str = TRANSACTIONAL,
    headers: dict[str, str] | None = None,
) -> None:
    """Send an email that was already rendered (a test, or a digest built elsewhere)."""
    _send(
        to,
        subject_prefix + rendered.subject,
        rendered.text,
        category=category,
        html=rendered.html,
        stream=stream,
        headers=headers,
        nonce=nonce,
    )


def send_templated(
    to: str,
    key: str,
    values: dict[str, Any],
    *,
    category: str,
    no_reply: bool = False,
    with_preferences: bool = False,
    copy: mt.Copy | None = None,
) -> None:
    tpl = mt.TEMPLATES.get(key)
    if tpl is not None and tpl.var("first_name") and not values.get("first_name"):
        values = {**values, "first_name": first_name_for(to)}
    rendered = render_template(key, values, with_preferences=with_preferences, copy=copy)
    _send(
        to,
        rendered.subject,
        rendered.text,
        category=category,
        no_reply=no_reply,
        html=rendered.html,
    )


def first_name_for(address: str) -> str:
    """The first word of the profile name of whoever owns ``address``; blank if unknown."""
    from apps.profiles.models import FounderProfile

    name = (
        FounderProfile.objects.filter(user__email__iexact=address)
        .values_list("full_name", flat=True)
        .first()
    )
    return (name or "").split()[0] if (name or "").strip() else ""


def _app(path: str) -> str:
    return f"{settings.FRONTEND_BASE_URL}{path}"


def send_verification(to: str, token: str) -> None:
    send_templated(
        to,
        "verification",
        {"verify_url": _app(f"/verify-email?token={token}")},
        category="verification",
    )


def send_already_registered(to: str) -> None:
    send_templated(
        to,
        "notice",
        {
            "title": "You already have a WO Community account",
            "detail": "Someone tried to apply with this address, but you already have an account. "
            f"If you forgot your password, you can choose a new one at {_app('/forgot-password')}. "
            "If this wasn't you, there's nothing to do.",
            "link_url": _app("/login"),
        },
        category="already_registered",
    )


def send_invitation(to: str, token: str, message: str, expires_at: datetime) -> None:
    send_templated(
        to,
        "invitation",
        {
            "note": message,
            "register_url": _app(f"/register?invitation={token}"),
            "expires_on": f"{expires_at:%d %B %Y}".lstrip("0"),
        },
        category="invitation",
    )


def send_approved(to: str) -> None:
    values = {"login_url": _app("/login"), "whatsapp_url": settings.WHATSAPP_COMMUNITY_URL}
    copy = templatestore.effective_copy("account_approved")
    if settings.WHATSAPP_COMMUNITY_URL and "{{whatsapp_url}}" not in copy.body:
        # Wording an admin edited before the invitation existed still carries it.
        copy = mt.Copy(
            copy.subject,
            copy.preheader,
            copy.body + "\n\n[Join our WhatsApp community]({{whatsapp_url}}) and say hello.",
        )
    send_templated(to, "account_approved", values, category="approved", copy=copy)


def send_rejected(to: str, reason: str) -> None:
    send_templated(to, "account_not_approved", {"reason": reason}, category="rejected")


def send_suspended(to: str, reason: str) -> None:
    send_templated(to, "account_suspended", {"reason": reason}, category="suspended")


def send_reinstated(to: str) -> None:
    send_templated(to, "account_reinstated", {"login_url": _app("/login")}, category="reinstated")


def send_application_received(to: str) -> None:
    send_templated(
        to, "application_received", {"profile_url": _app("/app/me")}, category="application"
    )


def send_password_changed(to: str, changed_at: datetime, tz_name: str = "UTC") -> None:
    moment = when(changed_at, tz_name)
    send_templated(
        to,
        "password_changed",
        {**moment, "reset_url": _app("/forgot-password")},
        category="password_changed",
    )


def send_quietly(to: str, key: str, values: dict[str, Any], *, category: str) -> None:
    """Send an email a member's own action asked for, without letting a mail fault fail it."""
    try:
        send_templated(to, key, values, category=category, with_preferences=True)
    except Exception:  # noqa: BLE001 - the action itself has already succeeded
        logger.exception("email_send_failed", key=key, category=category)


def when(moment: datetime, tz_name: str = "UTC") -> dict[str, str]:
    """A moment as the words an email shows: date, time and the time zone's name."""
    try:
        zone = ZoneInfo(tz_name or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        zone, tz_name = ZoneInfo("UTC"), "UTC"
    local = moment.astimezone(zone)
    hour = local.hour % 12 or 12
    return {
        "date": f"{local:%A} {local.day} {local:%B %Y}",
        "time": f"{hour}:{local:%M} {'AM' if local.hour < 12 else 'PM'}",
        "timezone": tz_name or "UTC",
    }


def send_removed(to: str, reason: str) -> None:
    send_templated(
        to,
        "notice",
        {
            "title": "Your WO Community account has been removed",
            "detail": f"Reason: {reason}. Your public pages are down. If you think this is a "
            "mistake, please send us a request through Contact support in the app.",
            "link_url": _app("/login"),
        },
        category="removed",
    )


def send_attendee_list(to: str, title: str, csv_text: str) -> None:
    """The attendee list of an event, as CSV text in the message, for its organiser."""
    _send(
        to,
        f"Attendees: {title}",
        f'The attendee list for "{title}", as sent by the WO Community team.\n\n'
        "It holds names and email addresses of members who registered. Keep it only as long as "
        "you need it for the event, and do not use it for anything else.\n\n"
        f"{csv_text}",
        category="attendee_list",
    )


def send_password_reset(to: str, token: str) -> None:
    send_templated(
        to,
        "password_reset",
        {"reset_url": _app(f"/reset-password?token={token}")},
        category="password_reset",
    )


def send_notice(
    to: str,
    subject: str,
    body: str,
    *,
    category: str,
    template: str = "",
    values: dict[str, Any] | None = None,
    link: str = "",
) -> None:
    """A notification delivered by email, with a pointer to the preferences that control it.

    With a ``template`` and its ``values`` the matching template is used; if those do not fit it,
    or none is given, the generic notice carries the same words.
    """
    # Support mail is answered inside the app, so it never invites a reply by email.
    no_reply = category.startswith("notification_ticket_")
    if link:
        attempts = [
            (template, values or {}),
            ("notice", {"title": subject, "detail": body, "link_url": link}),
        ]
        for key, data in attempts:
            if not key:
                continue
            try:
                send_templated(
                    to, key, data, category=category, no_reply=no_reply, with_preferences=True
                )
            except mt.TemplateError as exc:
                logger.warning("email_template_failed", key=key, reason=str(exc))
                continue
            return
    footer = f"\n\nYou can change which emails you get at {preferences_url()}"
    _send(to, subject, body + footer, category=category, no_reply=no_reply)


def send_support_mail(to: str, subject: str, body: str) -> None:
    """Mail for someone who asked for help without an account. It has no link and no Reply-To."""
    _send(to, subject, body, category="notification_ticket_public", no_reply=True)
