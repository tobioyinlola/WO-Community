from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

TRANSACTIONAL = "transactional"
MARKETING = "marketing"


class EmailRejected(Exception):
    """The provider will never accept this message (bad address, invalid content).

    Retrying cannot help, so callers drop the message and carry on.
    """

    def __init__(self, reason: str, code: str = "") -> None:
        super().__init__(reason)
        self.code = code


class EmailTemporarilyUnavailable(Exception):
    """Rate limited, timed out or a provider error. The same message is safe to send again."""

    def __init__(self, reason: str, retry_after: float | None = None) -> None:
        super().__init__(reason)
        self.retry_after = retry_after


class EmailMisconfigured(Exception):
    """Our credentials or sending domain are not accepted. Needs a person, so it is not hidden."""


@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    text_body: str
    html_body: str = ""
    stream: str = TRANSACTIONAL
    headers: dict[str, str] = field(default_factory=dict)
    reply_to: str = ""
    # Lets a provider recognise a repeat of the same message and send it only once.
    idempotency_key: str = ""
    tags: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class EmailEvent:
    # sent, delivered, delayed, bounced (permanent), soft_bounced, complained, opened,
    # clicked, failed
    kind: str
    provider_message_id: str
    email: str
    occurred_at: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


class EmailAdapter(ABC):
    """Everything the platform needs from an email provider."""

    provider_name = "unknown"

    @abstractmethod
    def send(self, message: EmailMessage) -> str:
        """Send one message and return the provider message id."""

    @abstractmethod
    def send_batch(self, messages: list[EmailMessage]) -> list[str]:
        """Send several messages and return their provider message ids in order."""

    @abstractmethod
    def verify_webhook(self, body: bytes, headers: dict[str, str]) -> bool:
        """True when the provider signature on a webhook delivery is valid.

        ``headers`` has lower case names.
        """

    @abstractmethod
    def webhook_event_id(self, headers: dict[str, str]) -> str:
        """The provider's unique id for a delivery, used to ignore repeats."""

    @abstractmethod
    def parse_event(self, payload: dict[str, Any]) -> list[EmailEvent]:
        """Translate a provider webhook payload into platform events."""
