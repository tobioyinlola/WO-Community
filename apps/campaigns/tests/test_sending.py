from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts import services as accounts
from apps.campaigns import services
from apps.campaigns.models import Campaign, CampaignRecipient
from apps.campaigns.tasks import continue_sending, start_due
from apps.campaigns.tests.conftest import make_campaign, set_profile, subscriber
from apps.integrations.email import EmailMisconfigured, EmailRejected, EmailTemporarilyUnavailable
from apps.integrations.email.fake import FakeEmailAdapter
from apps.notifications import services as notifications

pytestmark = pytest.mark.django_db


def marketing(sent_emails):
    return [m for m in sent_emails if m.stream == "marketing"]


@pytest.fixture
def audience(make_user):
    return [subscriber(make_user, f"m{i}@example.com") for i in range(3)]


def run(campaign):
    while services.send_batch(campaign.pk):
        pass
    campaign.refresh_from_db()


# --- sending ---


def test_a_campaign_reaches_every_eligible_member_once(
    admin, everyone, audience, sent_emails, make_user
):
    subscriber(make_user, "declined@example.com", consent=False)
    campaign = make_campaign(admin, everyone)
    services.send_now(actor=admin, campaign_id=campaign.pk)
    run(campaign)
    sent = marketing(sent_emails)
    assert sorted(m.to for m in sent) == ["m0@example.com", "m1@example.com", "m2@example.com"]
    campaign.refresh_from_db()
    assert campaign.status == "sent" and campaign.recipient_count == 3 and campaign.finished_at
    assert CampaignRecipient.objects.filter(status="sent").count() == 3
    assert all(r.provider_message_id.startswith("fake-") for r in campaign.recipients.all())


def test_each_message_is_personal_and_carries_one_click_unsubscribe(
    admin, everyone, make_user, sent_emails
):
    user = subscriber(make_user, "ada@example.com")
    set_profile(user, full_name="Ada Obi")
    campaign = make_campaign(admin, everyone)
    services.send_now(actor=admin, campaign_id=campaign.pk)
    run(campaign)
    [message] = marketing(sent_emails)
    assert message.subject == "News for you, Ada"
    assert "Hello Ada" in message.html_body and "HELLO ADA" in message.text_body
    token = message.headers["List-Unsubscribe"].split("token=")[1].rstrip(">")
    assert message.headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert message.headers["List-Unsubscribe"].startswith("<http")
    assert token in message.html_body and token in message.text_body
    assert message.tags["campaign"] == str(campaign.pk) and message.idempotency_key


def test_the_audience_is_frozen_when_sending_begins(
    admin, everyone, audience, make_user, sent_emails
):
    campaign = make_campaign(admin, everyone)
    services.send_now(actor=admin, campaign_id=campaign.pk)
    subscriber(make_user, "late@example.com")  # joins after the freeze
    run(campaign)
    assert "late@example.com" not in [m.to for m in marketing(sent_emails)]
    campaign.refresh_from_db()
    assert campaign.segment_snapshot == {} and campaign.recipient_count == 3


def test_big_audiences_go_out_in_batches(admin, everyone, audience, settings, sent_emails):
    settings.CAMPAIGN_BATCH_SIZE = 2
    campaign = make_campaign(admin, everyone)
    services.send_now(actor=admin, campaign_id=campaign.pk)
    assert services.send_batch(campaign.pk) is True and len(marketing(sent_emails)) == 2
    assert Campaign.objects.get(pk=campaign.pk).status == "sending"
    assert services.send_batch(campaign.pk) is False and len(marketing(sent_emails)) == 3
    assert Campaign.objects.get(pk=campaign.pk).status == "sent"


def test_the_task_keeps_sending_until_done(admin, everyone, audience, settings, sent_emails):
    settings.CAMPAIGN_BATCH_SIZE = 1
    campaign = make_campaign(admin, everyone)
    services.send_now(actor=admin, campaign_id=campaign.pk)
    continue_sending(str(campaign.pk))
    assert len(marketing(sent_emails)) == 3


def test_started_campaigns_are_picked_up_through_the_outbox(
    admin, everyone, audience, run_outbox, sent_emails
):
    campaign = make_campaign(admin, everyone)
    services.send_now(actor=admin, campaign_id=campaign.pk)
    run_outbox()
    assert len(marketing(sent_emails)) == 3


# --- who is left out, and when ---


def test_suppressed_addresses_are_never_sent_to(admin, everyone, audience, sent_emails):
    notifications.suppress("m1@example.com", "bounced")
    campaign = make_campaign(admin, everyone)
    services.send_now(actor=admin, campaign_id=campaign.pk)
    run(campaign)
    assert "m1@example.com" not in [m.to for m in marketing(sent_emails)]
    assert campaign.recipient_count == 2


def test_an_unsubscribe_during_a_send_is_honoured_immediately(
    admin, everyone, audience, settings, sent_emails
):
    settings.CAMPAIGN_BATCH_SIZE = 1
    campaign = make_campaign(admin, everyone)
    services.send_now(actor=admin, campaign_id=campaign.pk)
    services.send_batch(campaign.pk)
    late = campaign.recipients.filter(status="queued").first()
    accounts.set_marketing_consent(late.user_id, False)
    run(campaign)
    late.refresh_from_db()
    assert late.status == "skipped" and len(marketing(sent_emails)) == 2


def test_a_suppression_added_mid_send_is_honoured_too(
    admin, everyone, audience, settings, sent_emails
):
    settings.CAMPAIGN_BATCH_SIZE = 1
    campaign = make_campaign(admin, everyone)
    services.send_now(actor=admin, campaign_id=campaign.pk)
    services.send_batch(campaign.pk)
    last = campaign.recipients.filter(status="queued").last()
    notifications.suppress(accounts.emails_for([last.user_id])[last.user_id], "complained")
    run(campaign)
    last.refresh_from_db()
    assert last.status == "skipped"


def test_transactional_mail_is_unaffected_by_unsubscribing(make_user, sent_emails):
    from apps.notifications import emails

    user = subscriber(make_user, "keep@example.com")
    accounts.set_marketing_consent(user.pk, False)
    emails.send_approved("keep@example.com")
    assert sent_emails and sent_emails[-1].stream == "transactional"


# --- preconditions and states ---


def test_a_campaign_needs_content_and_an_audience(admin, everyone):
    empty = services.create_campaign(actor=admin, data={"name": "x", "subject": "s"})
    assert empty.blocks == []
    from rest_framework.exceptions import ValidationError

    with pytest.raises(ValidationError):
        services.send_now(actor=admin, campaign_id=empty.pk)
    nobody = make_campaign(admin, None)
    with pytest.raises(ValidationError):
        services.send_now(actor=admin, campaign_id=nobody.pk)


def test_sending_twice_is_refused(admin, everyone, audience):
    from apps.campaigns.services import Conflict

    campaign = make_campaign(admin, everyone)
    services.send_now(actor=admin, campaign_id=campaign.pk)
    with pytest.raises(Conflict):
        services.send_now(actor=admin, campaign_id=campaign.pk)


def test_the_kill_switch_stops_sending_until_resumed(
    admin, everyone, audience, settings, sent_emails
):
    settings.CAMPAIGN_BATCH_SIZE = 1
    campaign = make_campaign(admin, everyone)
    services.send_now(actor=admin, campaign_id=campaign.pk)
    services.send_batch(campaign.pk)
    services.pause(actor=admin, campaign_id=campaign.pk)
    assert services.send_batch(campaign.pk) is False and len(marketing(sent_emails)) == 1
    services.resume(actor=admin, campaign_id=campaign.pk)
    run(campaign)
    assert len(marketing(sent_emails)) == 3 and campaign.status == "sent"


def test_cancelling_leaves_the_unsent_unsent(admin, everyone, audience, settings, sent_emails):
    settings.CAMPAIGN_BATCH_SIZE = 1
    campaign = make_campaign(admin, everyone)
    services.send_now(actor=admin, campaign_id=campaign.pk)
    services.send_batch(campaign.pk)
    services.cancel(actor=admin, campaign_id=campaign.pk)
    assert services.send_batch(campaign.pk) is False
    assert len(marketing(sent_emails)) == 1
    assert campaign.recipients.filter(status="skipped").count() == 2


def test_state_changes_are_only_allowed_from_the_right_state(admin, everyone, audience):
    from apps.campaigns.services import Conflict

    campaign = make_campaign(admin, everyone)
    for call in (services.pause, services.resume, services.cancel, services.unschedule):
        with pytest.raises(Conflict):
            call(actor=admin, campaign_id=campaign.pk)


def test_a_sent_campaign_cannot_be_edited_or_deleted(admin, everyone, audience):
    from apps.campaigns.services import Conflict

    campaign = make_campaign(admin, everyone)
    services.send_now(actor=admin, campaign_id=campaign.pk)
    run(campaign)
    with pytest.raises(Conflict):
        services.update_campaign(
            actor=admin, campaign_id=campaign.pk, data={"name": "x"}, if_match=None
        )
    with pytest.raises(Conflict):
        services.delete_campaign(actor=admin, campaign_id=campaign.pk)


# --- scheduling ---


def test_a_scheduled_campaign_starts_by_itself_when_due(admin, everyone, audience, sent_emails):
    campaign = make_campaign(admin, everyone)
    services.schedule(actor=admin, campaign_id=campaign.pk, at=timezone.now() + timedelta(hours=1))
    assert start_due() == 0
    Campaign.objects.filter(pk=campaign.pk).update(
        scheduled_at=timezone.now() - timedelta(minutes=1)
    )
    assert start_due() == 1
    assert (
        len(marketing(sent_emails)) == 3 and Campaign.objects.get(pk=campaign.pk).status == "sent"
    )
    assert start_due() == 0


def test_a_schedule_must_be_in_the_future_and_can_be_cancelled(admin, everyone):
    from rest_framework.exceptions import ValidationError

    campaign = make_campaign(admin, everyone)
    with pytest.raises(ValidationError):
        services.schedule(
            actor=admin, campaign_id=campaign.pk, at=timezone.now() - timedelta(minutes=1)
        )
    services.schedule(actor=admin, campaign_id=campaign.pk, at=timezone.now() + timedelta(hours=1))
    assert services.unschedule(actor=admin, campaign_id=campaign.pk).status == "draft"


def test_the_audience_is_chosen_when_it_starts_not_when_scheduled(
    admin, everyone, audience, make_user, sent_emails
):
    campaign = make_campaign(admin, everyone)
    services.schedule(actor=admin, campaign_id=campaign.pk, at=timezone.now() + timedelta(hours=1))
    subscriber(make_user, "joined-later@example.com")
    Campaign.objects.filter(pk=campaign.pk).update(
        scheduled_at=timezone.now() - timedelta(minutes=1)
    )
    start_due()
    assert "joined-later@example.com" in [m.to for m in marketing(sent_emails)]


def test_a_stalled_send_is_picked_up_by_the_watchdog(admin, everyone, audience, sent_emails):
    campaign = make_campaign(admin, everyone)
    services.send_now(actor=admin, campaign_id=campaign.pk)  # the worker never ran
    start_due()
    assert len(marketing(sent_emails)) == 3


# --- trouble at the provider ---


def test_a_temporary_provider_problem_leaves_the_rest_queued_for_later(
    admin, everyone, audience, monkeypatch, sent_emails
):
    campaign = make_campaign(admin, everyone)
    services.send_now(actor=admin, campaign_id=campaign.pk)

    def busy(self, message):
        raise EmailTemporarilyUnavailable("rate limited")

    monkeypatch.setattr(FakeEmailAdapter, "send", busy)
    assert services.send_batch(campaign.pk) is True
    assert campaign.recipients.filter(status="queued").count() == 3
    monkeypatch.undo()
    run(campaign)
    assert campaign.status == "sent"


def test_a_message_the_provider_rejects_is_dropped_and_the_rest_continue(
    admin, everyone, audience, monkeypatch, sent_emails
):
    original = FakeEmailAdapter.send

    def picky(self, message):
        if message.to == "m1@example.com":
            raise EmailRejected("bad address", code="invalid")
        return original(self, message)

    monkeypatch.setattr(FakeEmailAdapter, "send", picky)
    campaign = make_campaign(admin, everyone)
    services.send_now(actor=admin, campaign_id=campaign.pk)
    run(campaign)
    assert campaign.recipients.filter(status="failed").count() == 1 and campaign.status == "sent"


def test_misconfigured_credentials_pause_the_campaign_instead_of_losing_mail(
    admin, everyone, audience, monkeypatch
):
    def broken(self, message):
        raise EmailMisconfigured("bad key")

    monkeypatch.setattr(FakeEmailAdapter, "send", broken)
    campaign = make_campaign(admin, everyone)
    services.send_now(actor=admin, campaign_id=campaign.pk)
    assert services.send_batch(campaign.pk) is False
    assert Campaign.objects.get(pk=campaign.pk).status == "paused"
    assert campaign.recipients.filter(status="queued").count() == 3


# --- the test send ---


def test_a_test_send_goes_to_the_admin_alone_and_is_marked(admin, everyone, audience, sent_emails):
    campaign = make_campaign(admin, everyone)
    services.send_test(actor=admin, campaign_id=campaign.pk)
    [message] = sent_emails
    assert message.to == "admin@example.com" and message.subject.startswith("[Test] ")
    assert message.stream == "transactional"
    assert Campaign.objects.get(pk=campaign.pk).status == "draft"


# --- reporting ---


def test_provider_reports_build_the_campaign_report(admin, everyone, audience):
    campaign = make_campaign(admin, everyone)
    services.send_now(actor=admin, campaign_id=campaign.pk)
    run(campaign)
    first, second, third = list(campaign.recipients.order_by("id"))
    for recipient, kinds in (
        (first, ["delivered", "opened", "clicked"]),
        (second, ["delivered"]),
        (third, ["bounced"]),
    ):
        for kind in kinds:
            services.record_delivery(kind, recipient.provider_message_id)
    report = services.report(campaign)
    assert report["recipients"] == 3 and report["sent"] == 3
    assert (report["delivered"], report["opened"], report["clicked"], report["bounced"]) == (
        2,
        1,
        1,
        1,
    )
    assert report["open_rate"] == round(1 / 3, 4) and report["click_rate"] == round(1 / 3, 4)


def test_a_click_implies_delivery_and_an_open(admin, everyone, audience):
    campaign = make_campaign(admin, everyone)
    services.send_now(actor=admin, campaign_id=campaign.pk)
    run(campaign)
    recipient = campaign.recipients.first()
    services.record_delivery("clicked", recipient.provider_message_id)
    recipient.refresh_from_db()
    assert recipient.delivered_at and recipient.opened_at and recipient.clicked_at


def test_reports_ignore_unknown_messages_and_unrelated_kinds(admin, everyone, audience):
    services.record_delivery("opened", "not-one-of-ours")
    services.record_delivery("sent", "")
    campaign = make_campaign(admin, everyone)
    assert services.report(campaign)["opened"] == 0


def test_delivery_events_from_the_webhook_reach_the_report(admin, everyone, audience):
    """The real path: a stored provider delivery is processed and the campaign hears about it."""
    from apps.notifications.models import WebhookDelivery
    from apps.notifications.services import process_delivery

    campaign = make_campaign(admin, everyone)
    services.send_now(actor=admin, campaign_id=campaign.pk)
    run(campaign)
    recipient = campaign.recipients.first()
    email = accounts.emails_for([recipient.user_id])[recipient.user_id]
    delivery = WebhookDelivery.objects.create(
        provider="fake",
        event_id="evt-1",
        payload={
            "events": [
                {"kind": "opened", "message_id": recipient.provider_message_id, "email": email}
            ]
        },
    )
    process_delivery(delivery.pk, FakeEmailAdapter())
    recipient.refresh_from_db()
    assert recipient.opened_at is not None
