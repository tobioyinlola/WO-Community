from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


class MeetingRejected(Exception):
    """The provider will never accept this request (bad time, unknown meeting).

    Retrying cannot help, so the caller records the failure and tells a person.
    """


class MeetingTemporarilyUnavailable(Exception):
    """Rate limited, timed out or a provider error. The same request is safe to send again."""

    def __init__(self, reason: str, retry_after: float | None = None) -> None:
        super().__init__(reason)
        self.retry_after = retry_after


class MeetingMisconfigured(Exception):
    """Our credentials or app settings are not accepted. Needs a person, so it is not hidden."""


@dataclass(frozen=True)
class Meeting:
    provider: str
    external_id: str
    join_url: str


class MeetingProvider(ABC):
    """Everything the platform needs from a video meeting provider.

    Meetings are made by the platform account, with attendees named for the invitation only; the
    platform sends its own notices, so providers must not email attendees themselves.
    """

    name = "unknown"

    @abstractmethod
    def create(
        self,
        *,
        title: str,
        starts_at: datetime,
        ends_at: datetime,
        attendee_emails: list[str],
        idempotency_key: str,
    ) -> Meeting:
        """Make a meeting and return its address. ``idempotency_key`` is a repeat guard where
        the provider supports one."""

    @abstractmethod
    def reschedule(self, *, external_id: str, starts_at: datetime, ends_at: datetime) -> None:
        """Move a meeting. Its address does not change."""

    @abstractmethod
    def cancel(self, *, external_id: str) -> None:
        """Delete a meeting. A meeting that is already gone is not an error."""
