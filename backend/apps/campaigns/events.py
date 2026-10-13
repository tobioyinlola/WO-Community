"""Domain events published by the campaigns module."""

from dataclasses import dataclass
from typing import ClassVar

from apps.core.events import DomainEvent


@dataclass(frozen=True)
class CampaignStarted(DomainEvent):
    """A campaign has queued its recipients and is ready to send (or has been resumed)."""

    topic: ClassVar[str] = "campaigns.started"
    campaign_id: str
