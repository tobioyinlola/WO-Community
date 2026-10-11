from django.conf import settings
from django.utils.module_loading import import_string

from apps.integrations.meetings.base import (
    Meeting,
    MeetingMisconfigured,
    MeetingProvider,
    MeetingRejected,
    MeetingTemporarilyUnavailable,
)

__all__ = [
    "Meeting",
    "MeetingMisconfigured",
    "MeetingProvider",
    "MeetingRejected",
    "MeetingTemporarilyUnavailable",
    "get_meeting_provider",
    "provider_names",
]


def provider_names() -> list[str]:
    return sorted(settings.MEETING_PROVIDERS)


def get_meeting_provider(name: str = "") -> MeetingProvider:
    """The adapter for a provider name, or for the platform default when no name is given."""
    chosen = name or settings.MEETING_DEFAULT_PROVIDER
    path = settings.MEETING_PROVIDERS.get(chosen)
    if path is None:
        raise MeetingMisconfigured(f"No meeting provider called {chosen!r}.")
    provider: MeetingProvider = import_string(path)()
    provider.name = chosen
    return provider
