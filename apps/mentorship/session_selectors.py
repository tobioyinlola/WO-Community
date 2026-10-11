"""Read side of sessions: a member's list, one session, the admin list and the calendar file."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from django.conf import settings
from django.db.models import Q, QuerySet
from django.utils import timezone

from apps.accounts import services as accounts
from apps.core.keyset import paginate
from apps.mentorship import booking, feedback
from apps.mentorship.models import ACTIVE_SESSION_STATUSES, MentorSession, SessionFeedback
from apps.profiles import selectors as profiles

Status = MentorSession.Status

# What a member can ask their list to show.
FILTERS = ("upcoming", "pending", "past", "closed", "all")


def mine(user_id: UUID, *, role: str = "", state: str = "all") -> QuerySet[MentorSession]:
    queryset = MentorSession.objects.all()
    if role == "mentor":
        queryset = queryset.filter(mentor_id=user_id)
    elif role == "mentee":
        queryset = queryset.filter(mentee_id=user_id)
    else:
        queryset = queryset.filter(Q(mentor_id=user_id) | Q(mentee_id=user_id))
    now = timezone.now()
    if state == "upcoming":
        queryset = queryset.filter(status=Status.CONFIRMED, ends_at__gt=now)
    elif state == "pending":
        queryset = queryset.filter(status=Status.REQUESTED)
    elif state == "past":
        queryset = queryset.filter(
            Q(status__in=(Status.COMPLETED, Status.NO_SHOW))
            | Q(status=Status.CONFIRMED, ends_at__lte=now)
        )
    elif state == "closed":
        queryset = queryset.filter(status__in=(Status.DECLINED, Status.CANCELLED, Status.EXPIRED))
    return queryset


def _party(card: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": card["id"],
        "name": card["name"],
        "headline": card["headline"],
        "photo": card["photo"],
        "slug": card["slug"],
    }


def _feedback_view(row: SessionFeedback | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "stars": row.stars,
        "comment": row.comment,
        "outcome": row.outcome,
        "updated_at": row.updated_at,
    }


def views(
    viewer_id: UUID, rows: list[MentorSession], *, admin: bool = False, viewer: Any = None
) -> list[dict[str, Any]]:
    """Sessions ready to show. ``viewer_id`` decides which side the person is on."""
    ids = list({r.mentor_id for r in rows} | {r.mentee_id for r in rows})
    cards = profiles.cards_for(viewer or _Viewer(viewer_id), ids)
    notes: dict[UUID, dict[UUID, SessionFeedback]] = {}
    for item in SessionFeedback.objects.filter(session_id__in=[r.pk for r in rows]):
        notes.setdefault(item.session_id, {})[item.author_id] = item
    now = timezone.now()
    out = []
    for row in rows:
        is_mentor = row.mentor_id == viewer_id
        is_mentee = row.mentee_id == viewer_id
        given = notes.get(row.pk, {})
        mine_row = given.get(viewer_id)
        finished = row.status in (Status.COMPLETED, Status.NO_SHOW)
        has_proposal = row.proposed_starts_at is not None
        live = row.status == Status.CONFIRMED and row.starts_at > now
        view: dict[str, Any] = {
            "id": row.pk,
            "status": row.status,
            "role": "mentor" if is_mentor else "mentee" if is_mentee else "admin",
            "starts_at": row.starts_at,
            "ends_at": row.ends_at,
            "topic": row.topic,
            "message": row.message,
            "mentor": _party(cards[row.mentor_id]),
            "mentee": _party(cards[row.mentee_id]),
            "meeting": _meeting_view(row, show_link=admin or is_mentor or is_mentee),
            "proposal": (
                {
                    "starts_at": row.proposed_starts_at,
                    "ends_at": row.proposed_ends_at,
                    "proposed_by": row.proposed_by_id,
                    "note": row.proposed_note,
                    "by_me": row.proposed_by_id == viewer_id,
                }
                if has_proposal
                else None
            ),
            "reschedule_count": row.reschedule_count,
            "reason": row.closed_reason,
            "cancelled_by": row.cancelled_by_id,
            "late_cancel": row.late_cancel,
            "created_at": row.created_at,
            "responded_at": row.responded_at,
            "confirmed_at": row.confirmed_at,
            "feedback": {
                "mine": _feedback_view(mine_row),
                # The founder's comments are for the mentor and admins; the founder never sees
                # the mentor's private note.
                "from_mentee": (
                    _feedback_view(next((f for f in given.values() if f.role == "mentee"), None))
                    if (is_mentor or admin)
                    else None
                ),
                "from_mentor": (
                    _feedback_view(next((f for f in given.values() if f.role == "mentor"), None))
                    if admin
                    else None
                ),
                "can_give": (is_mentor or is_mentee)
                and finished
                and now <= feedback.window_closes_at(row),
                "closes_at": feedback.window_closes_at(row) if finished else None,
            },
            "actions": {
                "accept": is_mentor and row.status == Status.REQUESTED and row.starts_at > now,
                "decline": is_mentor and row.status == Status.REQUESTED,
                "cancel": (is_mentor and live)
                or (is_mentee and row.status in ACTIVE_SESSION_STATUSES and row.starts_at > now),
                "reschedule": (is_mentor or is_mentee)
                and live
                and row.reschedule_count < settings.MENTORSHIP_MAX_RESCHEDULES,
                "answer_reschedule": (is_mentor or is_mentee)
                and live
                and has_proposal
                and row.proposed_by_id != viewer_id,
                "add_link": is_mentor
                and row.status == Status.CONFIRMED
                and row.meeting_state == MentorSession.MeetingState.FAILED,
            },
        }
        out.append(view)
    return out


class _Viewer:
    """A minimal active member, for building cards from an id alone."""

    is_authenticated = True
    status = "active"

    def __init__(self, user_id: UUID) -> None:
        self.pk = user_id


def _meeting_view(row: MentorSession, *, show_link: bool) -> dict[str, Any]:
    ready = row.status == Status.CONFIRMED and row.meeting_state == "ready"
    return {
        "provider": row.meeting_provider,
        "state": row.meeting_state if row.status == Status.CONFIRMED else "",
        "url": row.meeting_url if (ready and show_link) else "",
    }


def page(user_id: UUID, *, role: str, state: str, cursor: str, limit: int) -> dict[str, Any]:
    ascending = state in ("upcoming", "pending")
    rows, next_cursor = paginate(
        mine(user_id, role=role, state=state),
        fields=("starts_at", "id"),
        sort=f"sessions-{state}",
        cursor=cursor,
        limit=limit,
        descending=not ascending,
    )
    return {"results": views(user_id, rows), "next_cursor": next_cursor}


def detail(user_id: UUID, session_id: UUID) -> dict[str, Any]:
    session = booking.get_for(user_id, session_id)
    return views(user_id, [session])[0]


# --- admin ---


def admin_sessions(
    *, status: str = "", mentor_id: UUID | None = None, mentee_id: UUID | None = None
) -> QuerySet[MentorSession]:
    queryset = MentorSession.objects.all()
    if status:
        queryset = queryset.filter(status=status)
    if mentor_id:
        queryset = queryset.filter(mentor_id=mentor_id)
    if mentee_id:
        queryset = queryset.filter(mentee_id=mentee_id)
    return queryset.order_by("-starts_at", "id")


def admin_views(viewer: Any, rows: list[MentorSession]) -> list[dict[str, Any]]:
    emails = accounts.emails_for(list({r.mentor_id for r in rows} | {r.mentee_id for r in rows}))
    out = views(viewer.pk, rows, admin=True, viewer=viewer)
    for view, row in zip(out, rows, strict=True):
        view["mentor_email"] = emails.get(row.mentor_id, "")
        view["mentee_email"] = emails.get(row.mentee_id, "")
    return out


# --- calendar file ---


def _text(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r", "")
        .replace("\n", "\\n")
    )


def _stamp(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def calendar_file(user_id: UUID, session_id: UUID) -> str:
    """An iCalendar file for a confirmed session, so it can go in any calendar app."""
    session = booking.get_for(user_id, session_id)
    view = views(user_id, [session])[0]
    other = view["mentee"] if session.mentor_id == user_id else view["mentor"]
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//WO Community//Mentoring//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:session-{session.pk}@wocommunity",
        f"DTSTAMP:{_stamp(timezone.now())}",
        f"DTSTART:{_stamp(session.starts_at)}",
        f"DTEND:{_stamp(session.ends_at)}",
        f"SUMMARY:{_text('Mentoring session with ' + other['name'])}",
        f"DESCRIPTION:{_text(session.topic)}",
        f"URL:{settings.FRONTEND_BASE_URL}/sessions/{session.pk}",
    ]
    if view["meeting"]["url"]:
        lines.append(f"LOCATION:{_text(view['meeting']['url'])}")
    if session.status in (Status.CANCELLED, Status.DECLINED, Status.EXPIRED):
        lines.append("STATUS:CANCELLED")
    elif session.status == Status.REQUESTED:
        lines.append("STATUS:TENTATIVE")
    lines += ["END:VEVENT", "END:VCALENDAR"]
    return "\r\n".join(lines) + "\r\n"
