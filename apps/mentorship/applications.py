"""Mentor applications: applying, answering questions, and the admin decision."""

from datetime import timedelta
from typing import Any
from uuid import UUID

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import exceptions

from apps.accounts import services as accounts
from apps.analytics import services as analytics
from apps.audit import services as audit
from apps.core import events as domain_events
from apps.mentorship import domain, events
from apps.mentorship.models import OPEN_STATUSES, MentorApplication, MentorProfile

REAPPLY_AFTER = timedelta(days=30)
DEFAULT_CAPACITY = 3


class NotFound(exceptions.NotFound):
    default_detail = "Not found."


class Conflict(exceptions.APIException):
    status_code = 409
    default_code = "conflict"


class Forbidden(exceptions.PermissionDenied):
    default_detail = "You cannot do this."


REQUIRED = (
    "expertise",
    "years_experience",
    "current_role",
    "company",
    "linkedin_url",
    "industries",
    "stages",
    "languages",
    "timezone",
    "weekly_hours",
    "motivation",
)


def _clean(data: dict[str, Any]) -> dict[str, Any]:
    out = domain.clean_fields(data)
    if "linkedin_url" in data:
        out["linkedin_url"] = domain.linkedin(data["linkedin_url"])
    if "weekly_hours" in data:
        out["weekly_hours"] = domain.weekly_hours(data["weekly_hours"])
    if "availability_note" in data:
        out["availability_note"] = domain.text(
            "availability_note", data["availability_note"], limit=500, minimum=0
        )
    if "motivation" in data:
        out["motivation"] = domain.text(
            "motivation",
            data["motivation"],
            limit=domain.MAX_MOTIVATION,
            minimum=domain.MIN_MOTIVATION,
        )
    return out


def apply(*, user_id: UUID, data: dict[str, Any]) -> MentorApplication:
    """Submit an application. One may be open at a time; a decline waits 30 days."""
    if not data.get("accept_conduct"):
        raise domain.invalid("accept_conduct", "Accept the mentor conduct policy to apply.")
    missing = {f: ["This field is required."] for f in REQUIRED if f not in data}
    if missing:
        raise exceptions.ValidationError(missing)
    fields = _clean({k: data[k] for k in (*REQUIRED, "availability_note") if k in data})
    if not accounts.is_active(user_id):
        raise Forbidden()
    with transaction.atomic():
        if accounts.has_role(user_id, "mentor"):
            raise Conflict("You are already a mentor.")
        declined = (
            MentorApplication.objects.filter(
                applicant_id=user_id, status=MentorApplication.Status.DECLINED
            )
            .order_by("-decided_at")
            .first()
        )
        if (
            declined
            and declined.decided_at
            and timezone.now() < declined.decided_at + REAPPLY_AFTER
        ):
            raise Conflict("You can apply again 30 days after a decline.")
        try:
            with transaction.atomic():
                application = MentorApplication.objects.create(
                    applicant_id=user_id, conduct_accepted_at=timezone.now(), **fields
                )
        except IntegrityError as exc:
            raise Conflict("You already have an application waiting.") from exc
        domain_events.publish(events.MentorApplicationSubmitted(application_id=str(application.pk)))
    analytics.track("mentor_application_submitted", actor_id=user_id)
    return application


def _own_open(user_id: UUID, application_id: UUID) -> MentorApplication:
    application = (
        MentorApplication.objects.select_for_update()
        .filter(pk=application_id, applicant_id=user_id)
        .first()
    )
    if application is None:
        raise NotFound()
    if application.status not in OPEN_STATUSES:
        raise Conflict("This application is closed.")
    return application


def update(*, user_id: UUID, application_id: UUID, data: dict[str, Any]) -> MentorApplication:
    """Change an open application. Answering a request for information sends it back to review."""
    fields = _clean(data)
    with transaction.atomic():
        application = _own_open(user_id, application_id)
        for name, value in fields.items():
            setattr(application, name, value)
        resubmitted = application.status == MentorApplication.Status.INFO_REQUESTED
        if resubmitted:
            application.status = MentorApplication.Status.PENDING
        application.save()
        if resubmitted:
            domain_events.publish(
                events.MentorApplicationSubmitted(application_id=str(application.pk))
            )
    return application


def withdraw(*, user_id: UUID, application_id: UUID) -> MentorApplication:
    with transaction.atomic():
        application = _own_open(user_id, application_id)
        application.status = MentorApplication.Status.WITHDRAWN
        application.save(update_fields=["status", "updated_at"])
    return application


# --- the admin decision ---

OUTCOMES = {"approve": "approved", "decline": "declined", "request_info": "info_requested"}


def decide(
    *, actor: Any, application_id: UUID, decision: str, reason: str = "", ip: str = ""
) -> MentorApplication:
    """Approve, decline (with a reason) or ask the applicant for more information."""
    note = domain.text("reason", reason, limit=1000, minimum=0)
    if decision in ("decline", "request_info") and not note:
        raise domain.invalid(
            "reason",
            (
                "Say why the application was declined."
                if decision == "decline"
                else "Say what more you need to know."
            ),
        )
    with transaction.atomic():
        application = (
            MentorApplication.objects.select_for_update().filter(pk=application_id).first()
        )
        if application is None:
            raise NotFound()
        allowed = (
            (MentorApplication.Status.PENDING,)
            if decision == "request_info"
            else (MentorApplication.Status.PENDING, MentorApplication.Status.INFO_REQUESTED)
        )
        if application.status not in allowed:
            raise Conflict("This application was already decided or is waiting for the applicant.")
        if decision == "approve":
            if not accounts.is_active(application.applicant_id):
                raise Conflict("The applicant account is not active.")
            application.status = MentorApplication.Status.APPROVED
            _make_mentor(application)
        elif decision == "decline":
            application.status = MentorApplication.Status.DECLINED
        else:
            application.status = MentorApplication.Status.INFO_REQUESTED
        application.decided_by, application.decided_at = actor, timezone.now()
        application.decision_reason = "" if decision == "approve" else note
        application.save()
        audit.record(
            actor=actor,
            action=f"mentors.{decision}",
            target_type="mentor_application",
            target_id=application.pk,
            reason=application.decision_reason,
            ip=ip,
        )
        domain_events.publish(
            events.MentorApplicationDecided(
                application_id=str(application.pk),
                decision=OUTCOMES[decision],
                reason=application.decision_reason,
            )
        )
    if decision != "request_info":
        analytics.track(
            f"mentor_application_{OUTCOMES[decision]}", actor_id=application.applicant_id
        )
    return application


def _make_mentor(application: MentorApplication) -> None:
    now = timezone.now()
    fields = {
        "application": application,
        "expertise": application.expertise,
        "years_experience": application.years_experience,
        "current_role": application.current_role,
        "company": application.company,
        "industries": application.industries,
        "stages": application.stages,
        "languages": application.languages,
        "timezone": application.timezone,
    }
    profile = MentorProfile.objects.filter(user_id=application.applicant_id).first()
    if profile is None:
        MentorProfile.objects.create(
            user_id=application.applicant_id,
            approved_at=now,
            capacity_per_week=DEFAULT_CAPACITY,
            **fields,
        )
    else:  # a mentor who was revoked earlier and approved again
        for name, value in fields.items():
            setattr(profile, name, value)
        profile.status, profile.approved_at = MentorProfile.Status.ACTIVE, now
        profile.revoked_at = profile.revoked_by = None
        profile.revoke_reason = ""
        profile.save()
    accounts.grant_role(application.applicant_id, "mentor")


# --- reading ---


def latest_for(user_id: UUID) -> MentorApplication | None:
    return MentorApplication.objects.filter(applicant_id=user_id).order_by("-created_at").first()
