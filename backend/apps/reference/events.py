from dataclasses import dataclass
from typing import ClassVar

from apps.core.events import DomainEvent


@dataclass(frozen=True)
class ReferenceChanged(DomainEvent):
    """A list entry was added, edited, retired, removed or the list was reordered.

    ``slug`` is empty when the whole list changed (a reorder). Pages that show
    an entry's name rebuild from this, and cached public lists are purged.
    """

    topic: ClassVar[str] = "reference.changed"
    kind: str
    slug: str
