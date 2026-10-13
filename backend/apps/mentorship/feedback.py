"""What each side says once a session has finished.

The founder gives stars and a comment (kept for the mentor and admins, never shown publicly) or
says the mentor did not turn up. The mentor records whether the session was held or the founder
missed it. Stars feed the mentor rating, and editing them corrects the rating rather than adding
a second one.
"""

from datetime import timedelta
from typing import Any
from uuid import UUID

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.analytics import services as analytics
from apps.mentorship import booking, cache, domain
from apps.mentorship.applications import Conflict
from apps.mentorship.models import MentorProfile, MentorSession, SessionFeedback

MENTEE_OUTCOMES = ("held", "mentor_no_show")
MENTOR_OUTCOMES = ("held", "mentee_no_show")


def window_closes_at(session: MentorSession) -> Any:
    closed_from = session.completed_at or session.ends_at
    return closed_from + timedelta(days=settings.MENTORSHIP_FEEDBACK_WINDOW_DAYS)


def _rate(mentor_id: UUID, old: int | None, new: int | None) -> None:
    """Move the mentor rating from one founder's old stars to their new stars."""
    if old == new:
        return
    profile = MentorProfile.objects.select_for_update().filter(user_id=mentor_id).first()
    if profile is None:
        return
    if old is None and new is not None:
        profile.rating_count += 1
        profile.rating_total += new
    elif old is not None and new is None:
        profile.rating_count = max(0, profile.rating_count - 1)
        profile.rating_total = max(0, profile.rating_total - old)
    elif old is not None and new is not None:
        profile.rating_total = max(0, profile.rating_total - old + new)
    profile.save(update_fields=["rating_count", "rating_total", "updated_at"])


def submit(*, user_id: UUID, session_id: UUID, data: dict[str, Any]) -> SessionFeedback:
    now = timezone.now()
    with transaction.atomic():
        session = booking.get_for(user_id, session_id, lock=True)
        if session.status not in (
            MentorSession.Status.COMPLETED,
            MentorSession.Status.NO_SHOW,
        ):
            raise Conflict("Feedback opens once the session has finished.")
        if now > window_closes_at(session):
            raise Conflict("The time for feedback on this session has passed.")
        is_mentor = session.mentor_id == user_id
        comment = domain.text("comment", data.get("comment", ""), limit=1000, minimum=0)
        outcome = data.get("outcome", "held")
        if outcome not in (MENTOR_OUTCOMES if is_mentor else MENTEE_OUTCOMES):
            raise domain.invalid("outcome", "Choose one of the listed outcomes.")
        existing = SessionFeedback.objects.filter(session=session, author_id=user_id).first()
        if is_mentor:
            stars = None
            session.status = (
                MentorSession.Status.NO_SHOW
                if outcome == "mentee_no_show"
                else MentorSession.Status.COMPLETED
            )
            session.save(update_fields=["status", "updated_at"])
        else:
            stars = data.get("stars")
            if outcome == "mentor_no_show":
                stars = None  # nothing to rate when the mentor did not come
            elif stars is None:
                raise domain.invalid("stars", "Give 1 to 5 stars.")
            elif not 1 <= stars <= 5:
                raise domain.invalid("stars", "Give 1 to 5 stars.")
            _rate(session.mentor_id, existing.stars if existing else None, stars)
        feedback = existing or SessionFeedback(
            session=session,
            author_id=user_id,
            role=SessionFeedback.Role.MENTOR if is_mentor else SessionFeedback.Role.MENTEE,
        )
        feedback.stars, feedback.comment, feedback.outcome = stars, comment, outcome
        feedback.save()
        if stars is not None:
            analytics.track(
                "session_feedback_submitted", actor_id=user_id, properties={"rating": stars}
            )
        transaction.on_commit(cache.bump)
    return feedback
