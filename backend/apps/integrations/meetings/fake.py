from datetime import datetime
from typing import ClassVar

from apps.integrations.meetings.base import Meeting, MeetingProvider, MeetingRejected


class FakeMeetingProvider(MeetingProvider):
    """Keeps meetings in memory for tests and local runs; nothing leaves the process."""

    meetings: ClassVar[dict[str, dict[str, object]]] = {}
    created: ClassVar[list[str]] = []
    # Set to an exception instance to make the next calls fail with it.
    failure: ClassVar[Exception | None] = None

    @classmethod
    def reset(cls) -> None:
        cls.meetings.clear()
        cls.created.clear()
        cls.failure = None

    def _maybe_fail(self) -> None:
        if self.failure is not None:
            raise self.failure

    def create(
        self,
        *,
        title: str,
        starts_at: datetime,
        ends_at: datetime,
        attendee_emails: list[str],
        idempotency_key: str,
    ) -> Meeting:
        self._maybe_fail()
        external_id = f"fake-{idempotency_key}"
        self.created.append(external_id)  # every call, so a test can see a repeat
        self.meetings[external_id] = {
            "title": title,
            "starts_at": starts_at,
            "ends_at": ends_at,
            "attendees": list(attendee_emails),
            "provider": self.name,
        }
        return Meeting(self.name, external_id, f"https://meet.test/{self.name}/{idempotency_key}")

    def reschedule(self, *, external_id: str, starts_at: datetime, ends_at: datetime) -> None:
        self._maybe_fail()
        if external_id not in self.meetings:
            raise MeetingRejected("No such meeting.")
        self.meetings[external_id].update(starts_at=starts_at, ends_at=ends_at)

    def cancel(self, *, external_id: str) -> None:
        self._maybe_fail()
        self.meetings.pop(external_id, None)
