"""A published event as a share card: what, when and where, but never the link to join."""

from uuid import UUID
from zoneinfo import ZoneInfo

from apps.core import shareables
from apps.core.text import plain
from apps.events.models import Event

TYPES = {
    "demo_day": "Demo day",
    "workshop": "Workshop",
    "meetup": "Meetup",
    "announcement": "Announcement",
}


def _when(event: Event) -> str:
    try:
        zone = ZoneInfo(event.timezone)
    except (KeyError, ValueError):
        zone = ZoneInfo("UTC")
    start = event.starts_at.astimezone(zone)
    return f"{start.day} {start:%b %Y}, {start:%H:%M} {start.tzname()}"


def event_card(ref: str) -> shareables.Card | None:
    try:
        event_id = UUID(ref)
    except ValueError:
        return None
    event = Event.objects.filter(pk=event_id, status=Event.Status.PUBLISHED).first()
    if event is None:
        return None
    summary = plain(event.summary) if event.summary else ""
    return shareables.Card(
        kind="event",
        ref=str(event.pk),
        title=event.title,
        excerpt=shareables.excerpt(summary or event.description_text),
        url=f"/app/events/{event.pk}",
        badge=TYPES.get(event.type, "Event"),
        action="See the event",
        facts=[_when(event), event.location or "Online"],
    )
