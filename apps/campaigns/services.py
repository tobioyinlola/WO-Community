"""Public commands of the campaigns module: segments, newsletters and sending."""

import hashlib
from datetime import datetime
from typing import Any
from uuid import UUID

import structlog
from django.conf import settings
from django.core import signing
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import exceptions

from apps.accounts import services as accounts
from apps.analytics import services as analytics
from apps.audit import services as audit
from apps.campaigns import events, render, segments
from apps.campaigns.models import (
    Campaign,
    CampaignRecipient,
    CampaignTemplate,
    Segment,
)
from apps.core import etag
from apps.core import events as domain_events
from apps.core.text import plain
from apps.integrations.email import (
    MARKETING,
    TRANSACTIONAL,
    EmailMessage,
    EmailMisconfigured,
    EmailRejected,
    EmailTemporarilyUnavailable,
    get_email_adapter,
)
from apps.notifications import services as notifications
from apps.profiles import selectors as profiles

logger = structlog.get_logger(__name__)

TOKEN_SALT = "campaign-unsubscribe"  # noqa: S105  # nosec B105  # a signing namespace


class NotFound(exceptions.NotFound):
    default_detail = "Not found."


class Conflict(exceptions.APIException):
    status_code = 409
    default_code = "conflict"


class InvalidUnsubscribeLink(exceptions.ValidationError):
    default_code = "invalid_unsubscribe_link"


def _invalid(field: str, message: str) -> exceptions.ValidationError:
    return exceptions.ValidationError({field: [message]})


# --- unsubscribe links ---


def unsubscribe_token(user_id: UUID, campaign_id: UUID | None) -> str:
    return signing.dumps(
        {"u": str(user_id), "c": str(campaign_id) if campaign_id else ""}, salt=TOKEN_SALT
    )


def _parse_token(token: str) -> tuple[UUID, UUID | None]:
    try:
        data = signing.loads(token, salt=TOKEN_SALT)
        return UUID(data["u"]), UUID(data["c"]) if data["c"] else None
    except (signing.BadSignature, KeyError, ValueError, TypeError) as exc:
        raise InvalidUnsubscribeLink("This unsubscribe link is not valid.") from exc


def unsubscribe(token: str, *, ip: str = "") -> None:
    """Withdraw marketing consent and stop all marketing mail to the address, at once."""
    user_id, campaign_id = _parse_token(token)
    emails = accounts.emails_for([user_id])
    if user_id not in emails:
        return  # the account is gone, so there is nothing left to mail
    with transaction.atomic():
        accounts.set_marketing_consent(user_id, False, ip=ip)
        notifications.suppress(emails[user_id], "unsubscribed")
        if campaign_id:
            changed = CampaignRecipient.objects.filter(
                campaign_id=campaign_id, user_id=user_id, unsubscribed_at__isnull=True
            ).update(unsubscribed_at=timezone.now())
            if changed:
                analytics.track(
                    "newsletter_unsubscribed",
                    actor_id=user_id,
                    properties={"campaign": str(campaign_id)},
                )


# --- segments and templates ---


def create_segment(*, actor: Any, name: str, definition: dict[str, Any]) -> Segment:
    return Segment.objects.create(
        name=plain(name), definition=segments.clean(definition), created_by=actor
    )


def update_segment(
    *, segment_id: UUID, name: str | None, definition: dict[str, Any] | None
) -> Segment:
    segment = Segment.objects.filter(pk=segment_id).first()
    if segment is None:
        raise NotFound()
    if name is not None:
        segment.name = plain(name)
    if definition is not None:
        segment.definition = segments.clean(definition)
    segment.save()
    return segment


def delete_segment(*, segment_id: UUID) -> None:
    """Campaigns that used it keep their own snapshot; drafts using it lose the link."""
    deleted, _ = Segment.objects.filter(pk=segment_id).delete()
    if not deleted:
        raise NotFound()


def create_template(*, actor: Any, name: str, blocks: list[dict[str, Any]]) -> CampaignTemplate:
    return CampaignTemplate.objects.create(
        name=plain(name), blocks=render.clean_blocks(blocks, owner_id=actor.pk), created_by=actor
    )


def delete_template(*, template_id: UUID) -> None:
    deleted, _ = CampaignTemplate.objects.filter(pk=template_id).delete()
    if not deleted:
        raise NotFound()


# --- writing campaigns ---


def _check_text(subject: str, preheader: str) -> tuple[str, str]:
    subject, preheader = plain(subject), plain(preheader)
    if not subject:
        raise _invalid("subject", "This field may not be blank.")
    render.check_merge_fields(subject)
    return subject, preheader


def create_campaign(*, actor: Any, data: dict[str, Any], ip: str = "") -> Campaign:
    subject, preheader = _check_text(data["subject"], data.get("preheader", ""))
    blocks_in = data.get("blocks")
    if data.get("template_id"):
        template = CampaignTemplate.objects.filter(pk=data["template_id"]).first()
        if template is None:
            raise _invalid("template_id", "Unknown template.")
        blocks_in = template.blocks
    campaign = Campaign.objects.create(
        name=plain(data["name"]),
        subject=subject,
        preheader=preheader,
        blocks=render.clean_blocks(blocks_in, owner_id=actor.pk) if blocks_in else [],
        segment=_segment(data.get("segment_id")),
        created_by=actor,
    )
    audit.record(
        actor=actor,
        action="campaigns.created",
        target_type="campaign",
        target_id=campaign.pk,
        ip=ip,
    )
    return campaign


def _segment(segment_id: UUID | None) -> Segment | None:
    if segment_id is None:
        return None
    segment = Segment.objects.filter(pk=segment_id).first()
    if segment is None:
        raise _invalid("segment_id", "Unknown segment.")
    return segment


def _lock(campaign_id: UUID) -> Campaign:
    campaign = Campaign.objects.select_for_update().filter(pk=campaign_id).first()
    if campaign is None:
        raise NotFound()
    return campaign


def update_campaign(
    *, actor: Any, campaign_id: UUID, data: dict[str, Any], if_match: str | None
) -> Campaign:
    with transaction.atomic():
        campaign = _lock(campaign_id)
        if campaign.status not in (Campaign.Status.DRAFT, Campaign.Status.SCHEDULED):
            raise Conflict("Only a draft or scheduled campaign can be edited.")
        etag.assert_matches(if_match, campaign)
        if "name" in data:
            campaign.name = plain(data["name"])
        if "subject" in data or "preheader" in data:
            campaign.subject, campaign.preheader = _check_text(
                data.get("subject", campaign.subject), data.get("preheader", campaign.preheader)
            )
        if "blocks" in data:
            campaign.blocks = render.clean_blocks(data["blocks"], owner_id=actor.pk)
        if "segment_id" in data:
            campaign.segment = _segment(data["segment_id"])
        campaign.save()
    return campaign


def delete_campaign(*, actor: Any, campaign_id: UUID, ip: str = "") -> None:
    with transaction.atomic():
        campaign = _lock(campaign_id)
        if campaign.status in (Campaign.Status.SENDING, Campaign.Status.PAUSED):
            raise Conflict("Cancel a campaign that is sending before removing it.")
        if campaign.started_at is not None:
            raise Conflict("A campaign that has started is kept for its report.")
        audit.record(
            actor=actor,
            action="campaigns.deleted",
            target_type="campaign",
            target_id=campaign.pk,
            ip=ip,
        )
        campaign.delete()


# --- preparing to send ---


def _ready(campaign: Campaign) -> None:
    if not campaign.blocks:
        raise _invalid("blocks", "Add some content first.")
    if campaign.segment is None:
        raise _invalid("segment_id", "Choose who to send it to.")


def schedule(*, actor: Any, campaign_id: UUID, at: datetime, ip: str = "") -> Campaign:
    if at <= timezone.now():
        raise _invalid("scheduled_at", "Choose a time in the future.")
    with transaction.atomic():
        campaign = _lock(campaign_id)
        if campaign.status not in (Campaign.Status.DRAFT, Campaign.Status.SCHEDULED):
            raise Conflict("Only a draft can be scheduled.")
        _ready(campaign)
        campaign.status, campaign.scheduled_at = Campaign.Status.SCHEDULED, at
        campaign.save(update_fields=["status", "scheduled_at", "updated_at"])
        audit.record(
            actor=actor,
            action="campaigns.scheduled",
            target_type="campaign",
            target_id=campaign.pk,
            after={"scheduled_at": at.isoformat()},
            ip=ip,
        )
    return campaign


def unschedule(*, actor: Any, campaign_id: UUID, ip: str = "") -> Campaign:
    with transaction.atomic():
        campaign = _lock(campaign_id)
        if campaign.status != Campaign.Status.SCHEDULED:
            raise Conflict("This campaign is not scheduled.")
        campaign.status, campaign.scheduled_at = Campaign.Status.DRAFT, None
        campaign.save(update_fields=["status", "scheduled_at", "updated_at"])
        audit.record(
            actor=actor,
            action="campaigns.unscheduled",
            target_type="campaign",
            target_id=campaign.pk,
            ip=ip,
        )
    return campaign


def _begin(campaign: Campaign) -> None:
    """Freeze the audience and queue every recipient. Call with the campaign locked."""
    _ready(campaign)
    segment = campaign.segment
    if segment is None:  # _ready has already refused this
        raise _invalid("segment_id", "Choose who to send it to.")
    definition = segment.definition
    audience = segments.recipients(definition)
    CampaignRecipient.objects.bulk_create(
        CampaignRecipient(campaign=campaign, user_id=uid) for uid, _ in audience
    )
    campaign.segment_snapshot = definition
    campaign.recipient_count = len(audience)
    campaign.status = Campaign.Status.SENDING
    campaign.started_at = timezone.now()
    campaign.scheduled_at = None
    campaign.save()
    domain_events.publish(events.CampaignStarted(campaign_id=str(campaign.pk)))


def send_now(*, actor: Any, campaign_id: UUID, ip: str = "") -> Campaign:
    with transaction.atomic():
        campaign = _lock(campaign_id)
        if campaign.status not in (Campaign.Status.DRAFT, Campaign.Status.SCHEDULED):
            raise Conflict("Only a draft or scheduled campaign can be sent.")
        _begin(campaign)
        audit.record(
            actor=actor,
            action="campaigns.sent",
            target_type="campaign",
            target_id=campaign.pk,
            after={"recipients": campaign.recipient_count},
            ip=ip,
        )
    return campaign


def pause(*, actor: Any, campaign_id: UUID, ip: str = "") -> Campaign:
    """The kill switch: nothing more is sent until the campaign is resumed."""
    with transaction.atomic():
        campaign = _lock(campaign_id)
        if campaign.status != Campaign.Status.SENDING:
            raise Conflict("Only a campaign that is sending can be paused.")
        campaign.status = Campaign.Status.PAUSED
        campaign.save(update_fields=["status", "updated_at"])
        audit.record(
            actor=actor,
            action="campaigns.paused",
            target_type="campaign",
            target_id=campaign.pk,
            ip=ip,
        )
    return campaign


def resume(*, actor: Any, campaign_id: UUID, ip: str = "") -> Campaign:
    with transaction.atomic():
        campaign = _lock(campaign_id)
        if campaign.status != Campaign.Status.PAUSED:
            raise Conflict("This campaign is not paused.")
        campaign.status = Campaign.Status.SENDING
        campaign.save(update_fields=["status", "updated_at"])
        audit.record(
            actor=actor,
            action="campaigns.resumed",
            target_type="campaign",
            target_id=campaign.pk,
            ip=ip,
        )
        domain_events.publish(events.CampaignStarted(campaign_id=str(campaign.pk)))
    return campaign


def cancel(*, actor: Any, campaign_id: UUID, ip: str = "") -> Campaign:
    """Stop for good. People already sent to keep what they got; the rest are never mailed."""
    with transaction.atomic():
        campaign = _lock(campaign_id)
        if campaign.status not in (
            Campaign.Status.SCHEDULED,
            Campaign.Status.SENDING,
            Campaign.Status.PAUSED,
        ):
            raise Conflict("Only a scheduled, sending or paused campaign can be cancelled.")
        campaign.status, campaign.finished_at = Campaign.Status.CANCELLED, timezone.now()
        campaign.save(update_fields=["status", "finished_at", "updated_at"])
        campaign.recipients.filter(status=CampaignRecipient.Status.QUEUED).update(
            status=CampaignRecipient.Status.SKIPPED
        )
        audit.record(
            actor=actor,
            action="campaigns.cancelled",
            target_type="campaign",
            target_id=campaign.pk,
            ip=ip,
        )
    return campaign


# --- building and sending one email ---


def _build(
    campaign: Campaign, user_id: UUID, email: str, first_name: str, *, test: bool
) -> EmailMessage:
    token = unsubscribe_token(user_id, campaign.pk)
    page_url = f"{settings.FRONTEND_BASE_URL}/unsubscribe?token={token}"
    one_click = f"{settings.API_BASE_URL}/api/v1/unsubscribe?token={token}"
    html_body, text_body = render.render(
        preheader=campaign.preheader,
        blocks=campaign.blocks,
        first_name=first_name,
        unsubscribe_url=page_url,
    )
    subject = render.MERGE_TOKEN.sub(lambda m: first_name or render.FALLBACK_NAME, campaign.subject)
    key = hashlib.sha256(
        f"campaign:{campaign.pk}:{user_id}:{'test' if test else ''}".encode()
    ).hexdigest()
    return EmailMessage(
        to=email,
        subject=f"[Test] {subject}" if test else subject,
        text_body=text_body,
        html_body=html_body,
        stream=TRANSACTIONAL if test else MARKETING,
        headers={
            "List-Unsubscribe": f"<{one_click}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        },
        idempotency_key=key,
        tags={"category": "campaign", "campaign": str(campaign.pk)},
    )


def send_test(*, actor: Any, campaign_id: UUID) -> None:
    """Send the campaign to the admin who asked, and nobody else."""
    campaign = Campaign.objects.filter(pk=campaign_id).first()
    if campaign is None:
        raise NotFound()
    if not campaign.blocks:
        raise _invalid("blocks", "Add some content first.")
    email = accounts.emails_for([actor.pk]).get(actor.pk, "")
    first = profiles.first_names([actor.pk]).get(actor.pk, "")
    get_email_adapter().send(_build(campaign, actor.pk, email, first, test=True))


def _event_props(campaign: Campaign) -> dict[str, str]:
    props = {"campaign": str(campaign.pk)}
    if campaign.segment_id:
        props["segment"] = str(campaign.segment_id)
    return props


def _send_row(campaign: Campaign, row_id: UUID, adapter: Any) -> str:
    """Send to one recipient in its own transaction. Returns "ok", "stop" or "busy".

    One transaction per message means a crash can lose at most the record of the message in
    flight (the provider's idempotency key stops it going twice), never a whole batch. The
    campaign's status is read again each time, so the kill switch takes effect within one message.
    """
    with transaction.atomic():
        status = Campaign.objects.filter(pk=campaign.pk).values_list("status", flat=True).first()
        if status != Campaign.Status.SENDING:
            return "stop"
        row = (
            campaign.recipients.select_for_update(skip_locked=True)
            .filter(pk=row_id, status=CampaignRecipient.Status.QUEUED)
            .first()
        )
        if row is None:
            return "ok"  # another worker already has it
        uid = row.user_id
        email = accounts.emails_for([uid]).get(uid) if uid else None
        # Eligibility is checked again at the moment of sending, so an unsubscribe is honoured
        # immediately even for people queued earlier.
        if (
            uid is None
            or not email
            or not accounts.has_marketing_consent(uid)
            or notifications.is_suppressed(email)
        ):
            row.status = CampaignRecipient.Status.SKIPPED
            row.save(update_fields=["status", "updated_at"])
            return "ok"
        try:
            row.provider_message_id = adapter.send(
                _build(campaign, uid, email, profiles.first_names([uid]).get(uid, ""), test=False)
            )
            row.status, row.sent_at = CampaignRecipient.Status.SENT, timezone.now()
            analytics.track("newsletter_sent", actor_id=uid, properties=_event_props(campaign))
        except EmailRejected as exc:
            logger.warning("campaign_email_rejected", code=exc.code)
            row.status = CampaignRecipient.Status.FAILED
        except EmailTemporarilyUnavailable:
            return "busy"  # leave it queued; the next run retries
        except EmailMisconfigured:
            Campaign.objects.filter(pk=campaign.pk).update(
                status=Campaign.Status.PAUSED, updated_at=timezone.now()
            )
            logger.error("campaign_paused_provider_misconfigured", campaign_id=str(campaign.pk))
            return "stop"
        row.save()
    return "ok"


def send_batch(campaign_id: UUID) -> bool:
    """Send the next batch. Returns True if more remain, so the caller schedules another."""
    campaign = Campaign.objects.filter(pk=campaign_id).first()
    if campaign is None or campaign.status != Campaign.Status.SENDING:
        return False
    row_ids = list(
        campaign.recipients.filter(status=CampaignRecipient.Status.QUEUED)
        .order_by("id")
        .values_list("pk", flat=True)[: settings.CAMPAIGN_BATCH_SIZE]
    )
    adapter = get_email_adapter()
    for row_id in row_ids:
        outcome = _send_row(campaign, row_id, adapter)
        if outcome == "stop":
            return False
        if outcome == "busy":
            return True
    with transaction.atomic():
        locked = _lock(campaign_id)
        if locked.status != Campaign.Status.SENDING:
            return False
        remaining = locked.recipients.filter(status=CampaignRecipient.Status.QUEUED).exists()
        if not remaining:
            locked.status, locked.finished_at = Campaign.Status.SENT, timezone.now()
            locked.save(update_fields=["status", "finished_at", "updated_at"])
        return remaining


def start_due() -> int:
    """Begin campaigns whose scheduled time has come."""
    started = 0
    due = Campaign.objects.filter(
        status=Campaign.Status.SCHEDULED, scheduled_at__lte=timezone.now()
    )
    for candidate in due:
        with transaction.atomic():
            campaign = _lock(candidate.pk)
            if campaign.status != Campaign.Status.SCHEDULED:
                continue
            _begin(campaign)
            started += 1
    return started


def sending_ids() -> list[UUID]:
    return list(
        Campaign.objects.filter(
            status=Campaign.Status.SENDING, recipients__status=CampaignRecipient.Status.QUEUED
        )
        .values_list("pk", flat=True)
        .distinct()
    )


# --- reporting ---

_TIMESTAMP_KINDS = {
    "delivered": "delivered_at",
    "opened": "opened_at",
    "clicked": "clicked_at",
    "bounced": "bounced_at",
    "complained": "complained_at",
}


def _mark(rows: Any, column: str, event: str | None, now: datetime) -> None:
    """Stamp rows that do not have this milestone yet, and record the analytics event once each."""
    fresh = list(rows.filter(**{f"{column}__isnull": True}).values_list("user_id", "campaign_id"))
    if not fresh:
        return
    rows.filter(**{f"{column}__isnull": True}).update(**{column: now})
    if event is None:
        return
    for user_id, campaign_id in fresh:
        if user_id is not None:
            analytics.track(event, actor_id=user_id, properties={"campaign": str(campaign_id)})


_EVENT_FOR_KIND = {
    "delivered": "newsletter_delivered",
    "opened": "newsletter_opened",
    "clicked": "newsletter_clicked",
}


def record_delivery(kind: str, provider_message_id: str) -> None:
    """Called for each new delivery report from the email provider."""
    column = _TIMESTAMP_KINDS.get(kind)
    if column is None or not provider_message_id:
        return
    rows = CampaignRecipient.objects.filter(provider_message_id=provider_message_id)
    now = timezone.now()
    # A click proves delivery and an open, even if the provider never reported them.
    if kind == "clicked":
        _mark(rows, "delivered_at", "newsletter_delivered", now)
        _mark(rows, "opened_at", "newsletter_opened", now)
    elif kind == "opened":
        _mark(rows, "delivered_at", "newsletter_delivered", now)
    _mark(rows, column, _EVENT_FOR_KIND.get(kind), now)


def report(campaign: Campaign) -> dict[str, Any]:
    counts = campaign.recipients.aggregate(
        queued=Count("id", filter=Q(status=CampaignRecipient.Status.QUEUED)),
        sent=Count("id", filter=Q(status=CampaignRecipient.Status.SENT)),
        skipped=Count("id", filter=Q(status=CampaignRecipient.Status.SKIPPED)),
        failed=Count("id", filter=Q(status=CampaignRecipient.Status.FAILED)),
        delivered=Count("id", filter=Q(delivered_at__isnull=False)),
        opened=Count("id", filter=Q(opened_at__isnull=False)),
        clicked=Count("id", filter=Q(clicked_at__isnull=False)),
        bounced=Count("id", filter=Q(bounced_at__isnull=False)),
        unsubscribed=Count("id", filter=Q(unsubscribed_at__isnull=False)),
        complained=Count("id", filter=Q(complained_at__isnull=False)),
    )
    sent = counts["sent"] or 0
    counts["open_rate"] = round(counts["opened"] / sent, 4) if sent else 0.0
    counts["click_rate"] = round(counts["clicked"] / sent, 4) if sent else 0.0
    return {"recipients": campaign.recipient_count, **counts}


def recent_reports(limit: int = 5) -> list[dict[str, Any]]:
    """The latest finished or running campaigns with their reports, for the dashboard."""
    rows = Campaign.objects.filter(
        status__in=[Campaign.Status.SENDING, Campaign.Status.SENT]
    ).order_by("-started_at")[:limit]
    return [{"id": c.pk, "name": c.name, "started_at": c.started_at, **report(c)} for c in rows]
