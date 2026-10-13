"""The one way any module tells a member something.

``notify(user_id, type, payload)`` checks the member's preferences for each channel, writes the
in-app notification and, if wanted, sends the email. Delivery is idempotent when a ``dedupe_key``
is given, so a retried event never notifies twice. Wording lives here, not in the data: the
payload carries ids, and titles are produced when a notification is read or emailed.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import structlog
from django.conf import settings
from django.db import IntegrityError, transaction

from apps.accounts import services as accounts
from apps.core import ratelimit
from apps.notifications import emails, preferences
from apps.notifications.models import Notification
from apps.profiles import selectors as profiles

logger = structlog.get_logger(__name__)

EMAIL_BURST_LIMIT = 10  # emails of one kind to one member per hour; the rest stay in-app only
EMAIL_BURST_WINDOW = 3600


@dataclass(frozen=True)
class Spec:
    preference: str  # the preference type that switches it on and off
    title: Callable[[str, dict[str, Any]], str]  # (actor name, payload) -> sentence
    link: Callable[[dict[str, Any]], str]  # frontend path
    email: bool = False
    rate_limited_email: bool = False  # members can trigger these for each other
    # Extra words for the email (for example the reply itself), from the payload.
    body: Callable[[dict[str, Any]], str] | None = None


def _outcome_title(payload: dict[str, Any]) -> str:
    what = str(payload.get("target_type", "content")).replace("news_comment", "comment")
    if payload.get("outcome") == "actioned":
        return f"A moderator removed or hid the {what} you reported"
    if payload.get("outcome") == "reviewed":
        return f"A moderator reviewed your report and took no action on the {what}"
    return "A moderator handled your report"


def _mentor_decision_title(payload: dict[str, Any]) -> str:
    reason = payload.get("reason", "")
    if payload.get("decision") == "approved":
        return "Your mentor application was approved. Welcome as a mentor!"
    if payload.get("decision") == "declined":
        return f"Your mentor application was declined: {reason}"
    return f"We need more information for your mentor application: {reason}"


def _session_link(payload: dict[str, Any]) -> str:
    return f"/sessions/{payload['session_id']}"


def _session_cancelled_title(who: str, payload: dict[str, Any]) -> str:
    reason = payload.get("reason", "")
    suffix = f": {reason}" if reason else ""
    if payload.get("by") == "platform":
        return f"Your mentoring session was cancelled{suffix}"
    return f"{who} cancelled your mentoring session{suffix}"


def _reschedule_closed_title(who: str, payload: dict[str, Any]) -> str:
    if payload.get("withdrawn"):
        return f"{who} withdrew the suggested new time for your session"
    return f"{who} kept the original time for your session"


def _post_link(payload: dict[str, Any]) -> str:
    return f"/posts/{payload['post_id']}"


def _arranged(p: dict[str, Any]) -> str:
    """Paid sessions are settled between the two while online payment is off, and say so."""
    return ". Payment arranged directly" if p.get("payment") == "arranged" else ""


TYPES: dict[str, Spec] = {
    "comment": Spec(
        "comments",
        lambda who, p: f"{who} commented on your post",
        _post_link,
        email=True,
        rate_limited_email=True,
    ),
    "reply": Spec(
        "comments",
        lambda who, p: f"{who} replied to your comment",
        _post_link,
        email=True,
        rate_limited_email=True,
    ),
    "mention": Spec(
        "mentions",
        lambda who, p: f"{who} mentioned you in a {p.get('target_type', 'post')}",
        _post_link,
        email=True,
        rate_limited_email=True,
    ),
    "new_follower": Spec(
        "follows",
        lambda who, p: (
            f"{who} started following {p['startup_name']}"
            if p.get("kind") == "startup"
            else f"{who} started following you"
        ),
        lambda p: f"/members/{p['actor_id']}",
    ),
    "news_featuring_followed": Spec(
        "news",
        lambda who, p: f"In the news: {p.get('title', 'a story about someone you follow')}",
        lambda p: f"/news/{p['slug']}",
    ),
    "job_alert": Spec(
        "jobs",
        lambda who, p: f"New job matching your alert: {p.get('title', 'a new job')}",
        lambda p: f"/jobs/{p['job_id']}",
        email=True,
        rate_limited_email=True,
    ),
    "job_digest": Spec(
        "jobs",
        lambda who, p: f"{p.get('count', 0)} new jobs match your alert",
        lambda p: f"/jobs?alert={p['alert_id']}",
        email=True,
    ),
    "job_approved": Spec(
        "jobs",
        lambda who, p: f"Your job \"{p.get('title', '')}\" is now live",
        lambda p: f"/jobs/{p['job_id']}",
        email=True,
    ),
    "job_rejected": Spec(
        "jobs",
        lambda who, p: f"Your job \"{p.get('title', '')}\" was not approved: {p.get('reason', '')}",
        lambda p: f"/jobs/{p['job_id']}",
        email=True,
    ),
    "job_changed": Spec(
        "jobs",
        lambda who, p: (
            f"Your job \"{p.get('title', '')}\" was {p.get('what', 'changed')} by an admin"
            + (f": {p['reason']}" if p.get("reason") else "")
        ),
        lambda p: f"/jobs/{p['job_id']}",
        email=True,
    ),
    "job_expiring": Spec(
        "jobs",
        lambda who, p: f"Your job \"{p.get('title', '')}\" expires in 3 days: renew or close",
        lambda p: f"/jobs/{p['job_id']}",
        email=True,
    ),
    "win_approved": Spec(
        "moderation",
        lambda who, p: f"Your win \"{p.get('title', '')}\" was accepted. Congratulations!",
        lambda p: "/news",
        email=True,
    ),
    "win_rejected": Spec(
        "moderation",
        lambda who, p: f"Your win submission was not accepted: {p.get('reason', '')}",
        lambda p: "/news",
        email=True,
    ),
    "event_registered": Spec(
        "event_reminders",
        lambda who, p: f"You are registered for {p.get('title', 'the event')}",
        lambda p: f"/events/{p['event_id']}",
        email=True,
    ),
    "event_reminder": Spec(
        "event_reminders",
        lambda who, p: f"{p.get('title', 'Your event')} starts in "
        f"{'1 hour' if p.get('when') == '1h' else '24 hours'}",
        lambda p: f"/events/{p['event_id']}",
        email=True,
    ),
    "event_cancelled": Spec(
        "event_reminders",
        lambda who, p: f"{p.get('title', 'An event')} you registered for was cancelled",
        lambda p: f"/events/{p['event_id']}",
        email=True,
    ),
    "event_rescheduled": Spec(
        "event_reminders",
        lambda who, p: f"{p.get('title', 'An event')} you registered for has new times",
        lambda p: f"/events/{p['event_id']}",
        email=True,
    ),
    "certificate_ready": Spec(
        "learning",
        lambda who, p: f"Your certificate for \"{p.get('title', 'your course')}\" is ready",
        lambda p: f"/learn/certificates/{p['certificate_id']}",
        email=True,
    ),
    "course_granted": Spec(
        "learning",
        lambda who, p: f"You now have access to \"{p.get('title', 'a course')}\"",
        lambda p: f"/learn/courses/{p['course_id']}",
        email=True,
    ),
    "mentor_application_received": Spec(
        "mentorship",
        lambda who, p: "A new mentor application is waiting for review",
        lambda p: "/admin/mentor-applications",
        email=True,
    ),
    "mentor_application_decision": Spec(
        "mentorship",
        lambda who, p: _mentor_decision_title(p),
        lambda p: "/mentoring/application",
        email=True,
    ),
    "mentor_revoked": Spec(
        "mentorship",
        lambda who, p: "Your mentor status was withdrawn",
        lambda p: "/home",
        email=True,
    ),
    "session_requested": Spec(
        "mentorship",
        lambda who, p: f"{who} asked you for a mentoring session{_arranged(p)}",
        _session_link,
        email=True,
        rate_limited_email=True,
    ),
    "session_confirmed": Spec(
        "mentorship",
        lambda who, p: f"{who} confirmed your mentoring session{_arranged(p)}",
        _session_link,
        email=True,
    ),
    "session_declined": Spec(
        "mentorship",
        lambda who, p: f"{who} cannot take your session request: {p.get('reason', '')}",
        _session_link,
        email=True,
    ),
    "session_cancelled": Spec("mentorship", _session_cancelled_title, _session_link, email=True),
    "session_expired": Spec(
        "mentorship",
        lambda who, p: "Your mentoring request was not answered in time",
        _session_link,
        email=True,
    ),
    "session_reschedule_proposed": Spec(
        "mentorship",
        lambda who, p: f"{who} suggested a new time for your mentoring session",
        _session_link,
        email=True,
        rate_limited_email=True,
    ),
    "session_rescheduled": Spec(
        "mentorship",
        lambda who, p: f"{who} accepted the new time: your mentoring session has moved",
        _session_link,
        email=True,
    ),
    "session_reschedule_closed": Spec(
        "mentorship", _reschedule_closed_title, _session_link, email=True
    ),
    "session_reminder": Spec(
        "mentorship",
        lambda who, p: "Your mentoring session starts in "
        f"{'1 hour' if p.get('when') == '1h' else '24 hours'}",
        _session_link,
        email=True,
    ),
    "session_feedback_request": Spec(
        "mentorship",
        lambda who, p: "How was your mentoring session? Share your feedback",
        _session_link,
        email=True,
    ),
    "session_meeting_failed": Spec(
        "mentorship",
        lambda who, p: "We could not create a video meeting for your session. Add a link",
        _session_link,
        email=True,
    ),
    "session_meeting_ready": Spec(
        "mentorship",
        lambda who, p: f"{who} added a meeting link for your mentoring session",
        _session_link,
    ),
    "member_approved": Spec(
        "approvals", lambda who, p: "Your registration was approved. Welcome!", lambda p: "/home"
    ),
    "report_outcome": Spec("moderation", lambda who, p: _outcome_title(p), lambda p: "/home"),
    # Learning: asking for access, answers, announcements.
    "course_request": Spec(
        "learning",
        lambda who, p: f"New access request for \"{p.get('title', 'a course')}\"",
        lambda p: f"/admin/courses?course={p['course_id']}&tab=requests",
    ),
    "course_request_declined": Spec(
        "learning",
        lambda who, p: f"Your request for \"{p.get('title', 'a course')}\" was not approved",
        lambda p: f"/learn/courses/{p['course_id']}",
        email=True,
    ),
    "lecture_answer": Spec(
        "learning",
        lambda who, p: f"{who} answered your question in \"{p.get('title', 'a course')}\"",
        lambda p: f"/learn/courses/{p['course_id']}/lecture/{p['lesson_id']}?tab=qa",
    ),
    "course_announcement": Spec(
        "learning",
        lambda who, p: f"New in \"{p.get('title', 'your course')}\": {p.get('announcement', '')}",
        lambda p: f"/learn/courses/{p['course_id']}?tab=announcements",
        email=True,
    ),
    # Support: members are told in the app and by email; admins only in the app.
    "ticket_reply": Spec(
        "support",
        lambda who, p: f"Support replied to {p.get('reference', 'your request')}",
        lambda p: f"/support/{p['ticket_id']}",
        email=True,
        body=lambda p: str(p.get("excerpt", "")),
    ),
    "ticket_resolved": Spec(
        "support",
        lambda who, p: f"Support marked {p.get('reference', 'your request')} as resolved",
        lambda p: f"/support/{p['ticket_id']}",
        email=True,
        body=lambda p: str(p.get("excerpt", "")),
    ),
    "ticket_new": Spec(
        "support",
        lambda who, p: f"New support request {p.get('reference', '')}".strip(),
        lambda p: f"/admin/support?ticket={p['ticket_id']}",
    ),
    "ticket_member_reply": Spec(
        "support",
        lambda who, p: f"{p.get('reference', 'A request')} has a new reply from the member",
        lambda p: f"/admin/support?ticket={p['ticket_id']}",
    ),
}


def actor_names(viewer_id: UUID, actor_ids: list[UUID]) -> dict[UUID, str]:
    """Names as the recipient may see them: someone hidden from them is "Community member"."""
    if not actor_ids:
        return {}

    class _Viewer:
        pk = viewer_id
        is_authenticated = True
        status = "active"

    cards = profiles.cards_for(_Viewer(), actor_ids)
    return {uid: card["name"] for uid, card in cards.items()}


def _actor_id(payload: dict[str, Any]) -> UUID | None:
    raw = payload.get("actor_id")
    return UUID(raw) if raw else None


def notify(
    user_id: UUID, type_: str, payload: dict[str, Any], *, dedupe_key: str = ""
) -> Notification | None:
    """Notify one member. Returns the in-app notification, or None if none was created.

    Nothing is sent to the person who caused it, to anyone who is not an active member, or
    again for a ``dedupe_key`` that was already used.
    """
    spec = TYPES[type_]
    actor_id = _actor_id(payload)
    if actor_id == user_id or not accounts.is_active(user_id):
        return None
    if dedupe_key and Notification.objects.filter(user_id=user_id, dedupe_key=dedupe_key).exists():
        return None

    created: Notification | None = None
    if preferences.allows(user_id, spec.preference, "in_app"):
        try:
            with transaction.atomic():
                created = Notification.objects.create(
                    user_id=user_id,
                    type=type_,
                    payload=payload,
                    dedupe_key=dedupe_key,
                    channels_sent=["in_app"],
                )
        except IntegrityError:  # a concurrent delivery of the same event won
            return None
    if spec.email and preferences.allows(user_id, spec.preference, "email"):
        _email(user_id, type_, spec, payload, created)
    return created


def mail_template_for(
    type_: str, title: str, extra: str, link: str, payload: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    """The email template that suits a notification, with its values; the generic one otherwise."""
    when = "in 1 hour" if payload.get("when") == "1h" else "in 24 hours"
    match type_:
        case "job_approved":
            return "job_approved", {"job_title": payload.get("title"), "job_url": link}
        case "job_rejected":
            return "job_rejected", {
                "job_title": payload.get("title"),
                "reason": payload.get("reason"),
                "job_url": link,
            }
        case "mentor_application_decision":
            approved = str(payload.get("decision", "")) == "approved"
            return "mentor_decision", {
                "outcome": "approved" if approved else "not approved",
                "note": extra,
                "url": link,
            }
        case "ticket_reply" | "ticket_resolved":
            return "ticket_reply", {
                "reference": payload.get("reference"),
                "excerpt": extra,
                "ticket_url": link,
            }
        case "course_granted":
            return "course_access", {"course_title": payload.get("title"), "course_url": link}
        case "certificate_ready":
            return "certificate_issued", {
                "course_title": payload.get("title"),
                "certificate_url": link,
            }
        case "event_reminder":
            return "event_reminder", {
                "event_title": payload.get("title"),
                "when": when,
                "event_url": link,
            }
    return "notice", {"title": title, "detail": extra, "link_url": link}


def _email(
    user_id: UUID,
    type_: str,
    spec: Spec,
    payload: dict[str, Any],
    notification: Notification | None,
) -> None:
    if spec.rate_limited_email:
        key = f"notify-email:{user_id}:{spec.preference}"
        if ratelimit.hit(key, EMAIL_BURST_WINDOW) > EMAIL_BURST_LIMIT:
            logger.info("notification_email_throttled", type=type_)
            return
    contact = accounts.get_contact(user_id)
    if contact is None:
        return
    actor_id = _actor_id(payload)
    who = actor_names(user_id, [actor_id]).get(actor_id, "Someone") if actor_id else "Someone"
    title = spec.title(who, payload)
    extra = spec.body(payload) if spec.body else ""
    lead = f"{extra}\n\n" if extra else ""
    link = f"{settings.FRONTEND_BASE_URL}{spec.link(payload)}"
    template, values = mail_template_for(type_, title, extra, link, payload)
    emails.send_notice(
        contact.email,
        title,
        f"{title}.\n\n{lead}{link}",
        category=f"notification_{type_}",
        template=template,
        values=values,
        link=link,
    )
    if notification is not None:
        notification.channels_sent = [*notification.channels_sent, "email"]
        notification.save(update_fields=["channels_sent", "updated_at"])


def render(user_id: UUID, rows: list[Notification]) -> list[dict[str, Any]]:
    """Notifications ready to show: wording and link produced from the type and payload."""
    actor_ids = [a for a in (_actor_id(n.payload) for n in rows) if a]
    names = actor_names(user_id, list(dict.fromkeys(actor_ids)))
    items = []
    for row in rows:
        spec = TYPES.get(row.type)
        if spec is None:  # a type retired since this was written
            continue
        actor_id = _actor_id(row.payload)
        who = names.get(actor_id, "Someone") if actor_id else "Someone"
        items.append(
            {
                "id": row.pk,
                "type": row.type,
                "title": spec.title(who, row.payload),
                "link": spec.link(row.payload),
                "meta": row.payload,
                "read": row.read_at is not None,
                "created_at": row.created_at,
            }
        )
    return items
