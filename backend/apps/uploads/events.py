from dataclasses import dataclass
from typing import ClassVar

from apps.core.events import DomainEvent


@dataclass(frozen=True)
class UploadConfirmed(DomainEvent):
    """The file arrived in quarantine and should now be checked and processed."""

    topic: ClassVar[str] = "uploads.upload_confirmed"
    upload_id: str
