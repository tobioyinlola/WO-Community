"""Requesting, confirming, moving and cancelling mentoring sessions.

A session is one row from the founder's request to the held meeting. Asking for a time puts a
hold on it (the database refuses overlapping holds for the mentor and for the founder), the
mentor then confirms or declines, and either side can propose another time or cancel. The mentor
profile row is locked while a request is checked, so the weekly capacity count is exact.
"""

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import exceptions

from apps.accounts import services as accounts
from apps.analytics import services as analytics
from apps.audit import services as audit
from apps.core import events as domain_events
from apps.core import ratelimit
from apps.core.text import clean_url
from apps.mentorship import cache, domain, events, scheduling
from apps.mentorship.applications import Conflict, Forbidden, NotFound
from apps.mentorship.models import ACTIVE_SESSION_STATUSES, MentorProfile, MentorSession

Status = MentorSession.Status
MIN_REASON = 3


def _bump_after_commit() -> None:
    transaction.on_commit(cache.bump)


def _hours_since(start: datetime, end: datetime) -> int:
    return max(0, round((end - start).total_seconds() / 3600))


def _conflict_for(exc: IntegrityError) -> Conflict:
    """A clear message for whichever database guard refused the booking."""
    text = str(exc)
    if "mentorsession_mentee_no_overlap" in text:
        return Conflict("You already have a mentoring session at that time.")
    if "mentorsession_one_request_per_pair" in text:
        return Conflict("You already have a request waiting with this mentor.")
    return Conflict("That time was just taken. Choose another.")


# --- finding sessions ---


def get_for(user_id: UUID, session_id: UUID, *, lock: bool = False) -> MentorSession:
    """A session the user takes part in. Everyone else gets 404, never 403."""
    queryset = MentorSession.objects.filter(
        Q(mentor_id=user_id) | Q(mentee_id=user_id), pk=session_id
    )
    if lock:
        queryset = queryset.select_for_update()
    session = queryset.first()
    if session is None:
        raise NotFound()
    return session


def _profile(mentor_id: UUID, *, lock: bool = False) -> MentorProfile | None:
    queryset = MentorProfile.objects.filter(user_id=mentor_id, status=MentorProfile.Status.ACTIVE)
    return (queryset.select_for_update() if lock else queryset).first()


# --- requesting ---


def request(
    *, user_id: UUID, mentor_id: UUID, starts_at: datetime, topic: str, message: str
) -> MentorSession:
    """Ask a mentor for one of their bookable times."""
    topic = domain.text("topic", topic, limit=120, minimum=3)
    message = domain.text("message", message, limit=1000, minimum=20)
    if mentor_id == user_id:
        raise domain.invalid("mentor_id", "You cannot book a session with yourself.")
    today = timezone.now().date().isoformat()
    if (
        ratelimit.hit(f"mentorship:requests:{user_id}:{today}", 86400)
        > settings.MENTORSHIP_REQUESTS_PER_DAY
    ):
        raise exceptions.Throttled(wait=3600, detail="Daily request limit reached.")
    now = timezone.now()
    try:
        with transaction.atomic():
            profile = _profile(mentor_id, lock=True)
            if profile is None or profile.paused or not accounts.is_active(mentor_id):
                raise NotFound()
            waiting = MentorSession.objects.filter(mentee_id=user_id, status=Status.REQUESTED)
            if waiting.count() >= settings.MENTORSHIP_MAX_OPEN_REQUESTS:
                raise Conflict(
                    f"You can have {settings.MENTORSHIP_MAX_OPEN_REQUESTS} requests waiting at a "
                    "time. Wait for answers or withdraw one."
                )
            if waiting.filter(mentor_id=mentor_id).exists():
                raise Conflict("You already have a request waiting with this mentor.")
            if not scheduling.is_bookable(profile, starts_at, now=now):
                raise Conflict("That time is no longer available. Choose another.")
            ends_at = starts_at + timedelta(minutes=profile.session_minutes)
            session = MentorSession.objects.create(
                mentor_id=mentor_id,
                mentee_id=user_id,
                starts_at=starts_at,
                ends_at=ends_at,
                time_span=(starts_at, ends_at),
                topic=topic,
                message=message,
            )
            domain_events.publish(events.SessionRequested(session_id=str(session.pk)))
            analytics.track("mentorship_requested", actor_id=user_id)
            _bump_after_commit()
    except IntegrityError as exc:
        raise _conflict_for(exc) from exc
    return session


# --- the mentor answers ---


def accept(*, user_id: UUID, session_id: UUID) -> MentorSession:
    now = timezone.now()
    with transaction.atomic():
        session = get_for(user_id, session_id, lock=True)
        if session.mentor_id != user_id:
            raise Forbidden("Only the mentor can answer a request.")
        if session.status != Status.REQUESTED:
            raise Conflict("This request has already been answered.")
        if session.starts_at <= now:
            raise Conflict("The time for this session has passed.")
        profile = _profile(user_id)
        if profile is None:
            raise Forbidden("You are not an active mentor.")
        session.status = Status.CONFIRMED
        session.responded_at = session.confirmed_at = now
        session.meeting_provider = profile.meeting_provider or settings.MEETING_DEFAULT_PROVIDER
        session.meeting_state = MentorSession.MeetingState.PENDING
        session.save()
        domain_events.publish(events.SessionConfirmed(session_id=str(session.pk)))
        hours = _hours_since(session.created_at, now)
        analytics.track(
            "mentorship_accepted", actor_id=user_id, properties={"response_hours": hours}
        )
        analytics.track("session_booked", actor_id=session.mentee_id)
        _bump_after_commit()
    return session


def decline(*, user_id: UUID, session_id: UUID, reason: str) -> MentorSession:
    note = domain.text("reason", reason, limit=1000, minimum=MIN_REASON)
    now = timezone.now()
    with transaction.atomic():
        session = get_for(user_id, session_id, lock=True)
        if session.mentor_id != user_id:
            raise Forbidden("Only the mentor can answer a request.")
        if session.status != Status.REQUESTED:
            raise Conflict("This request has already been answered.")
        session.status = Status.DECLINED
        session.responded_at = now
        session.closed_reason = note
        session.save()
        domain_events.publish(events.SessionDeclined(session_id=str(session.pk), reason=note))
        analytics.track(
            "mentorship_declined",
            actor_id=user_id,
            properties={"response_hours": _hours_since(session.created_at, now)},
        )
        _bump_after_commit()
    return session


# --- cancelling ---


def _close(session: MentorSession, *, by: UUID | None, reason: str, now: datetime) -> None:
    """Cancel a requested or confirmed session. The caller holds the row lock."""
    was_confirmed = session.status == Status.CONFIRMED
    session.status = Status.CANCELLED
    session.cancelled_by_id = by
    session.cancelled_at = now
    session.closed_reason = reason
    session.late_cancel = was_confirmed and (
        session.starts_at - now < timedelta(hours=settings.MENTORSHIP_LATE_CANCEL_HOURS)
    )
    session.meeting_state = MentorSession.MeetingState.NONE
    session.proposed_starts_at = session.proposed_ends_at = None
    session.proposed_by = None
    session.proposed_note = ""
    session.save()
    domain_events.publish(
        events.SessionCancelled(session_id=str(session.pk), by=str(by) if by else "", reason=reason)
    )
    _bump_after_commit()


def cancel(*, user_id: UUID, session_id: UUID, reason: str = "") -> MentorSession:
    """Either person cancels. A founder can also withdraw a request that is still waiting."""
    now = timezone.now()
    with transaction.atomic():
        session = get_for(user_id, session_id, lock=True)
        if session.status not in ACTIVE_SESSION_STATUSES:
            raise Conflict("This session is already closed.")
        if session.status == Status.REQUESTED and session.mentor_id == user_id:
            raise Conflict("Decline the request instead.")
        if session.starts_at <= now:
            raise Conflict("This session has already started.")
        note = domain.text(
            "reason",
            reason,
            limit=1000,
            minimum=MIN_REASON if session.status == Status.CONFIRMED else 0,
        )
        _close(session, by=user_id, reason=note, now=now)
        analytics.track(
            "session_cancelled",
            actor_id=user_id,
            properties={"cancelled_by": "mentor" if user_id == session.mentor_id else "founder"},
        )
    return session


def cancel_by_admin(*, actor: Any, session_id: UUID, reason: str, ip: str = "") -> MentorSession:
    note = domain.text("reason", reason, limit=1000, minimum=MIN_REASON)
    now = timezone.now()
    with transaction.atomic():
        session = MentorSession.objects.select_for_update().filter(pk=session_id).first()
        if session is None:
            raise NotFound()
        if session.status not in ACTIVE_SESSION_STATUSES:
            raise Conflict("This session is already closed.")
        _close(session, by=None, reason=note, now=now)
        audit.record(
            actor=actor,
            action="sessions.cancel",
            target_type="mentor_session",
            target_id=session.pk,
            reason=note,
            ip=ip,
        )
    return session


def cancel_open_sessions(
    user_id: UUID, reason: str, *, as_mentor: bool = True, as_mentee: bool = True
) -> int:
    """Close every open session someone takes part in, for the platform. Returns how many.

    Used when a mentor is withdrawn (as mentor only) and when a member is suspended or removed
    (both sides). Both people are told, with the reason.
    """
    closed = 0
    now = timezone.now()
    role = Q(pk__in=[])
    if as_mentor:
        role |= Q(mentor_id=user_id)
    if as_mentee:
        role |= Q(mentee_id=user_id)
    ids = list(
        MentorSession.objects.filter(
            role, status__in=ACTIVE_SESSION_STATUSES, starts_at__gt=now
        ).values_list("pk", flat=True)
    )
    for pk in ids:
        with transaction.atomic():
            session = MentorSession.objects.select_for_update().filter(pk=pk).first()
            if session is None or session.status not in ACTIVE_SESSION_STATUSES:
                continue
            _close(session, by=None, reason=reason or "A participant is unavailable.", now=now)
            closed += 1
    return closed


def cancel_for_revoked_mentor(mentor_id: UUID, reason: str) -> int:
    return cancel_open_sessions(mentor_id, reason, as_mentee=False)


# --- moving ---


def propose_reschedule(
    *, user_id: UUID, session_id: UUID, starts_at: datetime, note: str = ""
) -> MentorSession:
    """Suggest another time. It takes effect only when the other person accepts."""
    cleaned = domain.text("note", note, limit=500, minimum=0)
    now = timezone.now()
    with transaction.atomic():
        session = get_for(user_id, session_id, lock=True)
        if session.status != Status.CONFIRMED:
            raise Conflict("Only a confirmed session can be moved.")
        if session.starts_at <= now:
            raise Conflict("This session has already started.")
        if session.reschedule_count >= settings.MENTORSHIP_MAX_RESCHEDULES:
            raise Conflict(
                f"A session can be moved {settings.MENTORSHIP_MAX_RESCHEDULES} times. "
                "Cancel it and ask for a new time instead."
            )
        profile = _profile(session.mentor_id)
        if profile is None:
            raise Conflict("The mentor is no longer available.")
        if starts_at == session.starts_at:
            raise domain.invalid("starts_at", "Choose a different time.")
        if not scheduling.is_bookable(profile, starts_at, now=now, exclude=session.pk):
            raise Conflict("That time is not available. Choose one of the mentor's times.")
        session.proposed_starts_at = starts_at
        session.proposed_ends_at = starts_at + timedelta(minutes=profile.session_minutes)
        session.proposed_by_id = user_id
        session.proposed_note = cleaned
        session.save()
        domain_events.publish(
            events.RescheduleProposed(session_id=str(session.pk), by=str(user_id))
        )
    return session


def _clear_proposal(session: MentorSession) -> None:
    session.proposed_starts_at = session.proposed_ends_at = None
    session.proposed_by = None
    session.proposed_note = ""


def accept_reschedule(*, user_id: UUID, session_id: UUID) -> MentorSession:
    now = timezone.now()
    try:
        with transaction.atomic():
            session = get_for(user_id, session_id, lock=True)
            if session.status != Status.CONFIRMED or session.proposed_starts_at is None:
                raise Conflict("There is no new time waiting for an answer.")
            if session.proposed_by_id == user_id:
                raise Forbidden("The other person has to accept your suggestion.")
            if session.starts_at <= now:
                raise Conflict("This session has already started.")
            profile = _profile(session.mentor_id)
            start = session.proposed_starts_at
            if profile is None or not scheduling.is_bookable(
                profile, start, now=now, exclude=session.pk
            ):
                raise Conflict("That time is no longer available. Suggest another.")
            assert session.proposed_ends_at is not None  # nosec B101
            session.starts_at, session.ends_at = start, session.proposed_ends_at
            session.time_span = (session.starts_at, session.ends_at)
            _clear_proposal(session)
            session.reschedule_count += 1
            session.reminded_24h_at = session.reminded_1h_at = None
            session.save()
            domain_events.publish(
                events.RescheduleAccepted(session_id=str(session.pk), by=str(user_id))
            )
            analytics.track("session_rescheduled", actor_id=user_id)
            _bump_after_commit()
    except IntegrityError as exc:
        raise _conflict_for(exc) from exc
    return session


def close_reschedule(*, user_id: UUID, session_id: UUID) -> MentorSession:
    """The proposer takes the suggestion back, or the other person keeps the original time."""
    with transaction.atomic():
        session = get_for(user_id, session_id, lock=True)
        if session.status != Status.CONFIRMED or session.proposed_starts_at is None:
            raise Conflict("There is no new time waiting for an answer.")
        withdrawn = session.proposed_by_id == user_id
        _clear_proposal(session)
        session.save()
        domain_events.publish(
            events.RescheduleClosed(
                session_id=str(session.pk), by=str(user_id), withdrawn=withdrawn
            )
        )
    return session


# --- the meeting link ---


def set_meeting_link(*, user_id: UUID, session_id: UUID, url: str) -> MentorSession:
    """The mentor supplies their own link when the platform could not make one."""
    try:
        link = clean_url(url)
    except exceptions.ValidationError as exc:
        raise domain.invalid("url", " ".join(str(m) for m in exc.detail)) from exc
    if not link:
        raise domain.invalid("url", "This field may not be blank.")
    with transaction.atomic():
        session = get_for(user_id, session_id, lock=True)
        if session.mentor_id != user_id:
            raise Forbidden("Only the mentor can add a meeting link.")
        if session.status != Status.CONFIRMED:
            raise Conflict("Only a confirmed session has a meeting.")
        if session.meeting_state != MentorSession.MeetingState.FAILED:
            raise Conflict("This session already has a meeting link.")
        session.meeting_provider = "manual"
        session.meeting_url = link
        session.meeting_external_id = ""
        session.meeting_state = MentorSession.MeetingState.READY
        session.save()
        domain_events.publish(events.MeetingLinkAdded(session_id=str(session.pk)))
    return session
