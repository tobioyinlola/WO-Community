"""Recent searches: the latest few terms per person and area, newest first."""

from uuid import UUID

from django.db import transaction
from django.db.models.functions import Lower
from django.utils import timezone

from apps.globalsearch.models import SearchRecent

KEEP = 8
SCOPES = ("member", "admin")


def recents(user_id: UUID, scope: str) -> list[str]:
    rows = SearchRecent.objects.filter(user_id=user_id, scope=scope).order_by("-last_used_at")
    return list(rows.values_list("term", flat=True)[:KEEP])


@transaction.atomic
def remember(user_id: UUID, scope: str, term: str) -> list[str]:
    """Store a term, moving it to the top if it is already there, and keep only the latest eight."""
    term = " ".join(term.split())
    now = timezone.now()
    existing = (
        SearchRecent.objects.annotate(folded=Lower("term"))
        .filter(user_id=user_id, scope=scope, folded=term.lower())
        .first()
    )
    if existing:
        existing.term = term
        existing.last_used_at = now
        existing.save(update_fields=["term", "last_used_at", "updated_at"])
    else:
        SearchRecent.objects.create(user_id=user_id, scope=scope, term=term, last_used_at=now)
    stale = SearchRecent.objects.filter(user_id=user_id, scope=scope).order_by("-last_used_at")[
        KEEP:
    ]
    SearchRecent.objects.filter(pk__in=[row.pk for row in stale]).delete()
    return recents(user_id, scope)


def clear(user_id: UUID, scope: str) -> None:
    SearchRecent.objects.filter(user_id=user_id, scope=scope).delete()
