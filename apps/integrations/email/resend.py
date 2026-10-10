"""Resend (https://resend.com) as the email provider.

Sending uses the REST API with a bearer key. Every send carries an idempotency
key when the caller gave one, so a retry after a timeout cannot deliver the
message twice. Failures are sorted into three kinds the callers treat
differently: rejected for good, worth retrying, and our own configuration.

Webhooks are signed with Svix: the signature covers the delivery id, the
timestamp and the exact body, and the timestamp must be recent so a captured
delivery cannot be replayed later.
"""

import base64
import hashlib
import hmac
import time
from functools import lru_cache
from typing import Any, NoReturn

import httpx
import structlog
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from apps.integrations.email.base import (
    MARKETING,
    EmailAdapter,
    EmailEvent,
    EmailMessage,
    EmailMisconfigured,
    EmailRejected,
    EmailTemporarilyUnavailable,
)

logger = structlog.get_logger(__name__)

API_URL = "https://api.resend.com"
BATCH_SIZE = 100  # the most Resend accepts in one batch request
WEBHOOK_TOLERANCE_SECONDS = 300

EVENT_KINDS = {
    "email.sent": "sent",
    "email.delivered": "delivered",
    "email.delivery_delayed": "delayed",
    "email.complained": "complained",
    "email.opened": "opened",
    "email.clicked": "clicked",
    "email.failed": "failed",
}


@lru_cache(maxsize=4)
def _shared_client(api_key: str) -> httpx.Client:
    return httpx.Client(
        base_url=API_URL,
        headers={"Authorization": f"Bearer {api_key}", "User-Agent": "wo-community-backend"},
        timeout=httpx.Timeout(10.0, connect=5.0),
    )


class ResendEmailAdapter(EmailAdapter):
    provider_name = "resend"

    def __init__(self, client: httpx.Client | None = None) -> None:
        if client is None:
            if not settings.RESEND_API_KEY:
                raise ImproperlyConfigured("RESEND_API_KEY is not set")
            client = _shared_client(settings.RESEND_API_KEY)
        self.client = client

    # --- sending -------------------------------------------------------------------------------

    @staticmethod
    def _payload(message: EmailMessage) -> dict[str, Any]:
        sender = (
            settings.EMAIL_FROM_MARKETING
            if message.stream == MARKETING
            else settings.EMAIL_FROM_TRANSACTIONAL
        )
        payload: dict[str, Any] = {
            "from": sender,
            "to": [message.to],
            "subject": message.subject,
            "text": message.text_body,
        }
        if message.html_body:
            payload["html"] = message.html_body
        reply_to = message.reply_to or settings.EMAIL_REPLY_TO
        if reply_to:
            payload["reply_to"] = reply_to
        if message.headers:
            payload["headers"] = message.headers
        if message.tags:
            payload["tags"] = [{"name": k, "value": v} for k, v in message.tags.items()]
        return payload

    def _post(self, path: str, body: Any, idempotency_key: str = "") -> dict[str, Any]:
        headers = {"Idempotency-Key": idempotency_key[:256]} if idempotency_key else {}
        try:
            response = self.client.post(path, json=body, headers=headers)
        except httpx.TransportError as exc:
            raise EmailTemporarilyUnavailable(
                f"could not reach Resend: {type(exc).__name__}"
            ) from exc
        if response.status_code < 300:
            result: dict[str, Any] = response.json()
            return result
        self._raise_for(response)

    @staticmethod
    def _raise_for(response: httpx.Response) -> NoReturn:
        status = response.status_code
        try:
            detail = response.json()
        except ValueError:
            detail = {}
        name = str(detail.get("name", ""))
        reason = str(detail.get("message", f"Resend answered {status}"))
        if status in (401, 403):
            # A wrong key, a key without sending access, or a domain that is not verified.
            raise EmailMisconfigured(f"{name or status}: {reason}")
        if status == 429 or status >= 500:
            retry_after = response.headers.get("retry-after")
            raise EmailTemporarilyUnavailable(
                f"{name or status}: {reason}",
                float(retry_after) if retry_after and retry_after.isdigit() else None,
            )
        if status == 409 and name == "concurrent_idempotent_requests":
            raise EmailTemporarilyUnavailable("the same message is already being sent")
        raise EmailRejected(reason, code=name or str(status))

    def send(self, message: EmailMessage) -> str:
        result = self._post("/emails", self._payload(message), message.idempotency_key)
        return str(result["id"])

    def send_batch(self, messages: list[EmailMessage]) -> list[str]:
        ids: list[str] = []
        for start in range(0, len(messages), BATCH_SIZE):
            chunk = messages[start : start + BATCH_SIZE]
            result = self._post("/emails/batch", [self._payload(m) for m in chunk])
            ids.extend(str(item["id"]) for item in result["data"])
        return ids

    # --- webhooks ------------------------------------------------------------------------------

    def verify_webhook(self, body: bytes, headers: dict[str, str]) -> bool:
        secret = settings.RESEND_WEBHOOK_SECRET
        delivery_id = headers.get("svix-id", "")
        timestamp = headers.get("svix-timestamp", "")
        signatures = headers.get("svix-signature", "")
        if not (secret and delivery_id and timestamp and signatures):
            return False
        try:
            if abs(time.time() - int(timestamp)) > WEBHOOK_TOLERANCE_SECONDS:
                return False
            key = base64.b64decode(secret.removeprefix("whsec_"))
        except ValueError:
            return False
        signed = f"{delivery_id}.{timestamp}.".encode() + body
        expected = base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()
        for entry in signatures.split():
            version, _, candidate = entry.partition(",")
            if version == "v1" and hmac.compare_digest(candidate, expected):
                return True
        return False

    def webhook_event_id(self, headers: dict[str, str]) -> str:
        return headers.get("svix-id", "")

    def parse_event(self, payload: dict[str, Any]) -> list[EmailEvent]:
        kind = self._kind(payload)
        data = payload.get("data") or {}
        if kind is None or not data.get("email_id"):
            return []  # an event type we do not use; ignored so new ones never break us
        recipients = data.get("to") or []
        return [
            EmailEvent(
                kind=kind,
                provider_message_id=str(data["email_id"]),
                email=str(address).lower(),
                occurred_at=str(payload.get("created_at", "")),
                raw={"type": payload.get("type"), "bounce": data.get("bounce")},
            )
            for address in recipients
        ]

    @staticmethod
    def _kind(payload: dict[str, Any]) -> str | None:
        event_type = str(payload.get("type", ""))
        if event_type == "email.bounced":
            bounce = (payload.get("data") or {}).get("bounce") or {}
            return (
                "bounced" if str(bounce.get("type", "")).lower() == "permanent" else "soft_bounced"
            )
        return EVENT_KINDS.get(event_type)
