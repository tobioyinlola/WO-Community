"""Background work for sessions: notices, video meetings and the timed jobs."""

from typing import Any
from uuid import UUID

import structlog
from celery import shared_task

from apps.accounts import services as accounts
from apps.core.models import OutboxEvent
from apps.integrations import meetings
from apps.mentorship import booking, lifecycle
from apps.mentorship.models import MentorSession
from apps.notifications import notify

logger = structlog.get_logger(__name__)
Status = MentorSession.Status
MeetingState = MentorSession.MeetingState


def _payload(event_id: str) -> dict[str, Any] | None:
    event = OutboxEvent.objects.filter(pk=event_id).first()
    if event is None:
        logger.warning("outbox_event_missing", event_id=event_id)
        return None
    return dict(event.payload)


def _session(data: dict[str, Any] | None) -> MentorSession | None:
    if data is None:
        return None
    return MentorSession.objects.filter(pk=data["session_id"]).first()


def _other(session: MentorSession, user_id: str) -> UUID:
    """The person in the session who is not ``user_id``."""
    return session.mentee_id if str(session.mentor_id) == user_id else session.mentor_id


# --- notices ---


@shared_task(name="mentorship.notify_session_requested")
def notify_session_requested(event_id: str) -> None:
    session = _session(_payload(event_id))
    if session is None or session.status != Status.REQUESTED:
        return
    notify.notify(
        session.mentor_id,
        "session_requested",
        {"session_id": str(session.pk), "actor_id": str(session.mentee_id)},
        dedupe_key=f"{event_id}:requested",
    )


@shared_task(name="mentorship.notify_session_confirmed")
def notify_session_confirmed(event_id: str) -> None:
    session = _session(_payload(event_id))
    if session is None:
        return
    notify.notify(
        session.mentee_id,
        "session_confirmed",
        {"session_id": str(session.pk), "actor_id": str(session.mentor_id)},
        dedupe_key=f"{event_id}:confirmed",
    )


@shared_task(name="mentorship.notify_session_declined")
def notify_session_declined(event_id: str) -> None:
    data = _payload(event_id)
    session = _session(data)
    if session is None or data is None:
        return
    notify.notify(
        session.mentee_id,
        "session_declined",
        {
            "session_id": str(session.pk),
            "actor_id": str(session.mentor_id),
            "reason": data["reason"],
        },
        dedupe_key=f"{event_id}:declined",
    )


@shared_task(name="mentorship.notify_session_cancelled")
def notify_session_cancelled(event_id: str) -> None:
    data = _payload(event_id)
    session = _session(data)
    if session is None or data is None:
        return
    by = data["by"]
    body: dict[str, Any] = {"session_id": str(session.pk), "reason": data["reason"]}
    if by:  # a person cancelled: tell the other one
        body["actor_id"] = by
        recipients = [_other(session, by)]
    else:  # the platform did (an admin, or the mentor was withdrawn): tell both
        body["by"] = "platform"
        recipients = [session.mentor_id, session.mentee_id]
    for user_id in recipients:
        notify.notify(user_id, "session_cancelled", body, dedupe_key=f"{event_id}:{user_id}")


@shared_task(name="mentorship.notify_session_expired")
def notify_session_expired(event_id: str) -> None:
    session = _session(_payload(event_id))
    if session is None:
        return
    notify.notify(
        session.mentee_id,
        "session_expired",
        {"session_id": str(session.pk)},
        dedupe_key=f"{event_id}:expired",
    )


@shared_task(name="mentorship.notify_session_completed")
def notify_session_completed(event_id: str) -> None:
    session = _session(_payload(event_id))
    if session is None:
        return
    for user_id in (session.mentee_id, session.mentor_id):
        notify.notify(
            user_id,
            "session_feedback_request",
            {"session_id": str(session.pk)},
            dedupe_key=f"{event_id}:{user_id}",
        )


@shared_task(name="mentorship.notify_reschedule_proposed")
def notify_reschedule_proposed(event_id: str) -> None:
    data = _payload(event_id)
    session = _session(data)
    if session is None or data is None or session.proposed_starts_at is None:
        return
    notify.notify(
        _other(session, data["by"]),
        "session_reschedule_proposed",
        {"session_id": str(session.pk), "actor_id": data["by"]},
        dedupe_key=f"{event_id}:proposed",
    )


@shared_task(name="mentorship.notify_reschedule_accepted")
def notify_reschedule_accepted(event_id: str) -> None:
    data = _payload(event_id)
    session = _session(data)
    if session is None or data is None:
        return
    notify.notify(
        _other(session, data["by"]),
        "session_rescheduled",
        {"session_id": str(session.pk), "actor_id": data["by"]},
        dedupe_key=f"{event_id}:accepted",
    )


@shared_task(name="mentorship.notify_reschedule_closed")
def notify_reschedule_closed(event_id: str) -> None:
    data = _payload(event_id)
    session = _session(data)
    if session is None or data is None:
        return
    notify.notify(
        _other(session, data["by"]),
        "session_reschedule_closed",
        {
            "session_id": str(session.pk),
            "actor_id": data["by"],
            "withdrawn": bool(data["withdrawn"]),
        },
        dedupe_key=f"{event_id}:closed",
    )


@shared_task(name="mentorship.notify_meeting_link")
def notify_meeting_link(event_id: str) -> None:
    session = _session(_payload(event_id))
    if session is None:
        return
    notify.notify(
        session.mentee_id,
        "session_meeting_ready",
        {"session_id": str(session.pk), "actor_id": str(session.mentor_id)},
        dedupe_key=f"{event_id}:link",
    )


@shared_task(name="mentorship.cancel_revoked_sessions")
def cancel_revoked_sessions(event_id: str) -> None:
    data = _payload(event_id)
    if data is None:
        return
    booking.cancel_for_revoked_mentor(
        UUID(data["user_id"]), "The mentor is no longer available on the platform."
    )


@shared_task(name="mentorship.cancel_sessions_of_member")
def cancel_sessions_of_member(event_id: str) -> None:
    """A member was suspended or removed: their open sessions cannot go ahead."""
    data = _payload(event_id)
    if data is None:
        return
    booking.cancel_open_sessions(
        UUID(data["user_id"]), "A participant is no longer available on the platform."
    )


# --- meetings ---


def _meeting_failed(session_id: UUID, detail: str) -> None:
    """Record that no meeting could be made, and ask the mentor to add a link themselves."""
    changed = MentorSession.objects.filter(
        pk=session_id,
        status=Status.CONFIRMED,
        meeting_external_id="",
        meeting_state=MeetingState.PENDING,
    ).update(meeting_state=MeetingState.FAILED)
    logger.error("meeting_creation_failed", session_id=str(session_id), detail=detail[:200])
    session = MentorSession.objects.filter(pk=session_id).first()
    if changed and session is not None:
        notify.notify(
            session.mentor_id,
            "session_meeting_failed",
            {"session_id": str(session.pk)},
            dedupe_key=f"meeting-failed:{session.pk}:{session.reschedule_count}",
        )


def _quiet(call: Any, **kwargs: Any) -> None:
    try:
        call(**kwargs)
    except Exception:  # best effort clean up; nothing more can be done if it fails
        logger.warning("meeting_cleanup_failed")


@shared_task(bind=True, name="mentorship.create_meeting")
def create_meeting(self: Any, event_id: str) -> None:
    """Make the video meeting for a confirmed session. Safe to run twice."""
    session = _session(_payload(event_id))
    if (
        session is None
        or session.status != Status.CONFIRMED
        or session.meeting_state != MeetingState.PENDING
        or session.meeting_external_id
    ):
        return
    try:
        provider = meetings.get_meeting_provider(session.meeting_provider)
        emails = list(accounts.emails_for([session.mentor_id, session.mentee_id]).values())
        meeting = provider.create(
            title=f"WO Community mentoring: {session.topic}",
            starts_at=session.starts_at,
            ends_at=session.ends_at,
            attendee_emails=emails,
            idempotency_key=str(session.pk),
        )
    except (meetings.MeetingRejected, meetings.MeetingMisconfigured) as exc:
        _meeting_failed(session.pk, str(exc))
        return
    except meetings.MeetingTemporarilyUnavailable as exc:
        if self.request.retries >= self.max_retries:
            _meeting_failed(session.pk, str(exc))
            return
        raise
    saved = MentorSession.objects.filter(
        pk=session.pk,
        status=Status.CONFIRMED,
        meeting_external_id="",
        meeting_state=MeetingState.PENDING,
    ).update(
        meeting_external_id=meeting.external_id,
        meeting_url=meeting.join_url,
        meeting_state=MeetingState.READY,
    )
    if not saved:  # cancelled while it was being made: do not leave a meeting behind
        _quiet(provider.cancel, external_id=meeting.external_id)
        return
    current = MentorSession.objects.get(pk=session.pk)
    if (current.starts_at, current.ends_at) != (session.starts_at, session.ends_at):
        # Moved while the meeting was being made.
        provider.reschedule(
            external_id=meeting.external_id, starts_at=current.starts_at, ends_at=current.ends_at
        )


@shared_task(name="mentorship.reschedule_meeting")
def reschedule_meeting(event_id: str) -> None:
    session = _session(_payload(event_id))
    if (
        session is None
        or session.status != Status.CONFIRMED
        or not session.meeting_external_id
        or session.meeting_provider == "manual"
    ):
        return  # a meeting still being made reads the new time when it finishes
    try:
        meetings.get_meeting_provider(session.meeting_provider).reschedule(
            external_id=session.meeting_external_id,
            starts_at=session.starts_at,
            ends_at=session.ends_at,
        )
    except meetings.MeetingRejected as exc:
        logger.error("meeting_reschedule_rejected", session_id=str(session.pk), detail=str(exc))
        MentorSession.objects.filter(pk=session.pk).update(
            meeting_state=MeetingState.FAILED, meeting_external_id="", meeting_url=""
        )
        notify.notify(
            session.mentor_id,
            "session_meeting_failed",
            {"session_id": str(session.pk)},
            dedupe_key=f"meeting-failed:{session.pk}:{session.reschedule_count}",
        )


@shared_task(name="mentorship.cancel_meeting")
def cancel_meeting(event_id: str) -> None:
    session = _session(_payload(event_id))
    if session is None or not session.meeting_external_id or session.meeting_provider == "manual":
        return
    try:
        meetings.get_meeting_provider(session.meeting_provider).cancel(
            external_id=session.meeting_external_id
        )
    except meetings.MeetingRejected as exc:
        logger.warning("meeting_cancel_rejected", session_id=str(session.pk), detail=str(exc))
    MentorSession.objects.filter(pk=session.pk).update(meeting_external_id="", meeting_url="")


# --- on a schedule ---


@shared_task(name="mentorship.expire_requests")
def expire_requests() -> int:
    return lifecycle.expire_requests()


@shared_task(name="mentorship.send_reminders")
def send_reminders() -> int:
    return lifecycle.send_reminders()


@shared_task(name="mentorship.complete_due")
def complete_due() -> int:
    return lifecycle.complete_due()
