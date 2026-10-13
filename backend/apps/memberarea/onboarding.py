"""The first-login checklist: profile, startup, traction and notification preferences."""

from typing import Any
from uuid import UUID

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.analytics import services as analytics
from apps.memberarea.models import OnboardingState
from apps.notifications import preferences
from apps.profiles import selectors as profiles
from apps.startups import selectors as startups

PROFILE_COMPLETE_SCORE = 80


def _items(user_id: UUID, score: int) -> list[dict[str, Any]]:
    return [
        {"key": "complete_profile", "done": score >= PROFILE_COMPLETE_SCORE},
        {"key": "add_startup", "done": bool(startups.startup_ids_of_member(user_id))},
        {"key": "add_traction", "done": startups.has_traction(user_id)},
        {"key": "set_notification_preferences", "done": preferences.has_confirmed(user_id)},
    ]


def _mark_completed(user_id: UUID, started_at: Any) -> None:
    """Record completion once, however many requests notice it at the same time."""
    try:
        with transaction.atomic():
            state, _ = OnboardingState.objects.select_for_update().get_or_create(user_id=user_id)
            if state.completed_at is not None:
                return
            state.completed_at = timezone.now()
            state.save(update_fields=["completed_at", "updated_at"])
            hours = int((state.completed_at - started_at).total_seconds() // 3600)
            analytics.track(
                "onboarding_completed",
                actor_id=user_id,
                properties={"time_to_complete_hours": max(hours, 0)},
            )
    except IntegrityError:
        pass  # a concurrent request created the row and records the event


def checklist(user: Any) -> dict[str, Any]:
    """The member's checklist and profile score. Notices the moment it becomes complete."""
    _, own = profiles.own_profile(user.pk)
    score = own["completeness"]["score"]
    items = _items(user.pk, score)
    complete = all(item["done"] for item in items)
    if complete:
        _mark_completed(user.pk, user.created_at)
    return {
        "items": items,
        "complete": complete,
        "profile_completeness": {
            "score": score,
            "next_missing_field": own["completeness"]["next_missing_field"],
        },
    }
