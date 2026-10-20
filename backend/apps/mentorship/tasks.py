from typing import Any
from uuid import UUID

import structlog
from celery import shared_task
from django.conf import settings

from apps.accounts import services as accounts
from apps.core.models import OutboxEvent
from apps.mentorship.models import MentorApplication, MentorInterest
from apps.notifications import adminalerts, emails, notify

logger = structlog.get_logger(__name__)
ADMIN_ROLES = ["community_admin", "super_admin"]


def _payload(event_id: str) -> dict[str, Any] | None:
    event = OutboxEvent.objects.filter(pk=event_id).first()
    if event is None:
        logger.warning("outbox_event_missing", event_id=event_id)
        return None
    return dict(event.payload)


@shared_task(name="mentorship.notify_admins")
def notify_admins(event_id: str) -> None:
    data = _payload(event_id)
    application = (
        MentorApplication.objects.filter(pk=data["application_id"]).first() if data else None
    )
    if application is None or application.status != MentorApplication.Status.PENDING:
        return
    contact = accounts.get_contact(application.applicant_id)
    if contact is not None:
        emails.send_quietly(
            contact.email,
            "mentor_application_received",
            {"url": f"{settings.FRONTEND_BASE_URL}/app/mentors/become"},
            category="mentor_application_received",
        )
    adminalerts.raise_alert(
        "mentor_application",
        item_key=f"mentor-application:{application.pk}",
        what="New mentor application",
        who=contact.email if contact else "A member",
        path="/admin/mentors",
        in_app=False,  # the loop below already tells them in the app
    )
    for admin_id in list(accounts.ids_with_roles(ADMIN_ROLES)):
        notify.notify(
            UUID(str(admin_id)),
            "mentor_application_received",
            {"application_id": str(application.pk)},
            dedupe_key=f"{event_id}:{admin_id}",
        )


@shared_task(name="mentorship.notify_decision")
def notify_decision(event_id: str) -> None:
    data = _payload(event_id)
    application = (
        MentorApplication.objects.filter(pk=data["application_id"]).first() if data else None
    )
    if data is None or application is None:
        return
    notify.notify(
        application.applicant_id,
        "mentor_application_decision",
        {
            "application_id": str(application.pk),
            "decision": data["decision"],
            "reason": data["reason"],
        },
        dedupe_key=f"{event_id}:decision",
    )


@shared_task(name="mentorship.notify_revoked")
def notify_revoked(event_id: str) -> None:
    data = _payload(event_id)
    if data is None:
        return
    notify.notify(
        UUID(data["user_id"]),
        "mentor_revoked",
        {"reason": data["reason"]},
        dedupe_key=f"{event_id}:revoked",
    )


@shared_task(name="mentorship.notify_pending")
def notify_pending(event_id: str) -> None:
    data = _payload(event_id)
    if data is None:
        return
    notify.notify(
        UUID(data["user_id"]),
        "mentor_pending",
        {"reason": data["reason"]},
        dedupe_key=f"{event_id}:pending",
    )


@shared_task(name="mentorship.notify_reinstated")
def notify_reinstated(event_id: str) -> None:
    data = _payload(event_id)
    if data is None:
        return
    notify.notify(
        UUID(data["user_id"]),
        "mentor_reinstated",
        {},
        dedupe_key=f"{event_id}:reinstated",
    )


@shared_task(name="mentorship.record_interest")
def record_interest(event_id: str) -> None:
    data = _payload(event_id)
    if data is None or not data["details"].get("also_mentor"):
        return
    MentorInterest.objects.get_or_create(user_id=UUID(data["user_id"]))
