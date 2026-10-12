"""The parts of a session's life that happen on their own: lapsing, reminders and finishing."""

from datetime import datetime, timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.analytics import services as analytics
from apps.core import events as domain_events
from apps.mentorship import cache, events
from apps.mentorship.models import MentorSession
from apps.notifications import notify

Status = MentorSession.Status
REMINDERS = (("24h", timedelta(hours=24)), ("1h", timedelta(hours=1)))


def expire_requests(now: datetime | None = None) -> int:
    """Close requests nobody answered in time, which frees their holds on the calendar."""
    now = now or timezone.now()
    due = MentorSession.objects.filter(status=Status.REQUESTED).filter(
        Q(created_at__lte=now - timedelta(hours=settings.MENTORSHIP_REQUEST_TTL_HOURS))
        | Q(starts_at__lte=now + timedelta(hours=settings.MENTORSHIP_DECIDE_BEFORE_START_HOURS))
    )
    expired = 0
    for pk in list(due.values_list("pk", flat=True)):
        with transaction.atomic():
            session = MentorSession.objects.select_for_update().filter(pk=pk).first()
            if session is None or session.status != Status.REQUESTED:
                continue
            session.status = Status.EXPIRED
            session.save(update_fields=["status", "updated_at"])
            domain_events.publish(events.SessionExpired(session_id=str(session.pk)))
            transaction.on_commit(cache.bump)
            expired += 1
    return expired


def send_reminders(now: datetime | None = None) -> int:
    """Remind both people 24 hours and 1 hour before a confirmed session starts.

    Each reminder is claimed on the row before anything is sent, so a restart never sends twice.
    Someone who confirmed inside a window is skipped for it: the confirmation said the same.
    """
    now = now or timezone.now()
    sent = 0
    for label, lead in REMINDERS:
        field = f"reminded_{label}_at"
        due = MentorSession.objects.filter(
            status=Status.CONFIRMED,
            starts_at__gt=now,
            starts_at__lte=now + lead,
            **{f"{field}__isnull": True},
        )
        for session in due:
            claimed = MentorSession.objects.filter(
                pk=session.pk, status=Status.CONFIRMED, **{f"{field}__isnull": True}
            ).update(**{field: now})
            if not claimed:
                continue
            if session.confirmed_at and session.confirmed_at > session.starts_at - lead:
                continue
            for user_id in (session.mentor_id, session.mentee_id):
                notify.notify(
                    user_id,
                    "session_reminder",
                    {"session_id": str(session.pk), "when": label},
                    dedupe_key=f"session-reminder:{session.pk}:{label}:{session.reschedule_count}",
                )
            sent += 1
    return sent


def complete_due(now: datetime | None = None) -> int:
    """Mark confirmed sessions that have ended as held, and ask both sides for feedback."""
    now = now or timezone.now()
    cutoff = now - timedelta(minutes=settings.MENTORSHIP_COMPLETE_AFTER_MINUTES)
    done = 0
    due = MentorSession.objects.filter(status=Status.CONFIRMED, ends_at__lte=cutoff)
    for pk in list(due.values_list("pk", flat=True)):
        with transaction.atomic():
            session = MentorSession.objects.select_for_update().filter(pk=pk).first()
            if session is None or session.status != Status.CONFIRMED:
                continue
            session.status = Status.COMPLETED
            session.completed_at = session.feedback_requested_at = now
            session.proposed_starts_at = session.proposed_ends_at = None
            session.proposed_by = None
            session.save()
            domain_events.publish(events.SessionCompleted(session_id=str(session.pk)))
            analytics.track("session_completed", actor_id=session.mentee_id)
            transaction.on_commit(cache.bump)
            done += 1
    return done
