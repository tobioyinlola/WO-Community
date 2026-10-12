from dataclasses import dataclass
from typing import ClassVar

from apps.core.events import DomainEvent


@dataclass(frozen=True)
class WebhookReceived(DomainEvent):
    """A signed delivery from the email provider is stored and waiting to be processed."""

    topic: ClassVar[str] = "notifications.webhook_received"
    delivery_id: str
