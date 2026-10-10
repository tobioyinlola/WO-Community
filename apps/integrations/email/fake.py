import uuid
from typing import Any, ClassVar

from apps.integrations.email.base import EmailAdapter, EmailEvent, EmailMessage


class FakeEmailAdapter(EmailAdapter):
    """In memory adapter for local development and tests. Nothing leaves the process."""

    provider_name = "fake"
    sent: ClassVar[list[EmailMessage]] = []

    @classmethod
    def reset(cls) -> None:
        cls.sent.clear()

    def send(self, message: EmailMessage) -> str:
        self.sent.append(message)
        return f"fake-{uuid.uuid4().hex}"

    def send_batch(self, messages: list[EmailMessage]) -> list[str]:
        return [self.send(message) for message in messages]

    def verify_webhook(self, body: bytes, headers: dict[str, str]) -> bool:
        return headers.get("x-fake-signature") == "valid"

    def webhook_event_id(self, headers: dict[str, str]) -> str:
        return headers.get("x-fake-event-id", "")

    def parse_event(self, payload: dict[str, Any]) -> list[EmailEvent]:
        return [
            EmailEvent(
                kind=item["kind"],
                provider_message_id=item["message_id"],
                email=item["email"],
                raw=item,
            )
            for item in payload.get("events", [])
        ]
