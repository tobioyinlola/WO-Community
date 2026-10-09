from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    text_body: str
    html_body: str = ""
    stream: str = "transactional"  # or "marketing"
    headers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class EmailEvent:
    kind: str  # delivered, opened, clicked, bounced, complained, unsubscribed
    provider_message_id: str
    email: str
    raw: dict[str, Any] = field(default_factory=dict)


class EmailAdapter(ABC):
    """Everything the platform needs from an email provider."""

    @abstractmethod
    def send(self, message: EmailMessage) -> str:
        """Send one message and return the provider message id."""

    @abstractmethod
    def send_batch(self, messages: list[EmailMessage]) -> list[str]:
        """Send several messages and return their provider message ids in order."""

    @abstractmethod
    def verify_webhook(self, body: bytes, headers: dict[str, str]) -> bool:
        """True when the provider signature on a webhook delivery is valid."""

    @abstractmethod
    def parse_event(self, payload: dict[str, Any]) -> list[EmailEvent]:
        """Translate a provider webhook payload into platform events."""
