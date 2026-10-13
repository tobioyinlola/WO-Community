"""Sends through a plain SMTP server. For trying the real sending path on a laptop with a mail
catcher such as Mailpit; it is not a production provider (no delivery reports, no webhooks)."""

import smtplib
import uuid
from email.message import EmailMessage as MimeMessage
from email.utils import formatdate, make_msgid
from typing import Any

from django.conf import settings

from apps.integrations.email.base import (
    MARKETING,
    EmailAdapter,
    EmailEvent,
    EmailMessage,
    EmailTemporarilyUnavailable,
)


class SmtpEmailAdapter(EmailAdapter):
    provider_name = "smtp"

    @staticmethod
    def _mime(message: EmailMessage) -> MimeMessage:
        sender = (
            settings.EMAIL_FROM_MARKETING
            if message.stream == MARKETING
            else settings.EMAIL_FROM_TRANSACTIONAL
        )
        mime = MimeMessage()
        mime["From"] = sender
        mime["To"] = message.to
        mime["Subject"] = message.subject
        mime["Date"] = formatdate(localtime=False)
        mime["Message-ID"] = make_msgid(domain="wo-community.local")
        reply_to = "" if message.no_reply else message.reply_to or settings.EMAIL_REPLY_TO
        if reply_to:
            mime["Reply-To"] = reply_to
        for name, value in message.headers.items():
            mime[name] = value
        mime.set_content(message.text_body)
        if message.html_body:
            mime.add_alternative(message.html_body, subtype="html")
        return mime

    def send(self, message: EmailMessage) -> str:
        mime = self._mime(message)
        try:
            with smtplib.SMTP(settings.EMAIL_SMTP_HOST, settings.EMAIL_SMTP_PORT, timeout=10) as s:
                s.send_message(mime)
        except (OSError, smtplib.SMTPException) as exc:
            raise EmailTemporarilyUnavailable(f"SMTP failed: {type(exc).__name__}") from exc
        return str(mime["Message-ID"]) or f"smtp-{uuid.uuid4().hex}"

    def send_batch(self, messages: list[EmailMessage]) -> list[str]:
        return [self.send(message) for message in messages]

    def verify_webhook(self, body: bytes, headers: dict[str, str]) -> bool:
        return False

    def webhook_event_id(self, headers: dict[str, str]) -> str:
        return ""

    def parse_event(self, payload: dict[str, Any]) -> list[EmailEvent]:
        return []
