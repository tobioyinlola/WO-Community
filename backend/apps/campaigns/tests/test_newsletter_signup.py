import re

import pytest
from django.core.cache import cache

from apps.accounts import services as accounts
from apps.campaigns import newsletter, services
from apps.campaigns.models import CampaignRecipient, NewsletterSubscriber
from apps.campaigns.tests.conftest import make_campaign, subscriber
from apps.notifications import services as notifications

pytestmark = pytest.mark.django_db

SIGNUP = "/api/v1/newsletter/subscribe"
CONFIRM = "/api/v1/newsletter/confirm"
LEAVE = "/api/v1/newsletter/unsubscribe"


def confirm_link(sent_emails, to):
    mail = [m for m in sent_emails if m.to == to]
    assert mail, f"no email to {to}"
    match = re.search(r"/newsletter/confirm\?token=([^\s\"<]+)", mail[-1].text_body)
    assert match
    return match.group(1)


def test_signing_up_sends_a_confirmation_and_nothing_counts_until_it_is_opened(
    api_client, sent_emails
):
    response = api_client.post(SIGNUP, {"email": "Reader@Example.com"})
    assert response.status_code == 202
    row = NewsletterSubscriber.objects.get()
    assert (row.email, row.status) == ("reader@example.com", "pending")
    mail = [m for m in sent_emails if m.to == "reader@example.com"]
    assert mail[0].subject == "Confirm your WO Community newsletter subscription"

    token = confirm_link(sent_emails, "reader@example.com")
    assert api_client.post(CONFIRM, {"token": token}).status_code == 200
    row.refresh_from_db()
    assert row.status == "confirmed" and row.confirmed_at is not None


def test_the_answer_never_says_whether_an_address_is_already_on_the_list(api_client, sent_emails):
    first = api_client.post(SIGNUP, {"email": "reader@example.com"})
    api_client.post(CONFIRM, {"token": confirm_link(sent_emails, "reader@example.com")})
    again = api_client.post(SIGNUP, {"email": "reader@example.com"})
    assert first.json() == again.json() and again.status_code == 202
    assert len([m for m in sent_emails if m.to == "reader@example.com"]) == 1


def test_a_bot_filling_the_hidden_field_is_quietly_ignored(api_client, sent_emails):
    response = api_client.post(SIGNUP, {"email": "bot@example.com", "website": "spam"})
    assert response.status_code == 202
    assert not NewsletterSubscriber.objects.exists() and not sent_emails


@pytest.mark.parametrize("token", ["", "garbage", "a" * 400])
def test_bad_confirmation_links_are_refused(api_client, token):
    assert api_client.post(CONFIRM, {"token": token}).status_code == 400


def test_a_member_who_signs_up_gets_the_newsletter_through_their_account(
    api_client, sent_emails, make_user
):
    member = subscriber(make_user, "member@example.com", consent=False)
    api_client.post(SIGNUP, {"email": "member@example.com"})
    api_client.post(CONFIRM, {"token": confirm_link(sent_emails, "member@example.com")})
    assert accounts.has_marketing_consent(member.pk)
    assert not newsletter.sendable().exists()  # reached as a member, not twice


def test_campaigns_reach_subscribers_only_when_asked_and_they_can_leave(
    api_client, admin, everyone, sent_emails
):
    newsletter.subscribe("reader@example.com")
    newsletter.confirm(newsletter.confirm_token("reader@example.com"))
    sent_emails.clear()

    members_only = make_campaign(admin, everyone)
    assert services.audience_size(members_only.pk) == 0

    campaign = make_campaign(admin, everyone, include_subscribers=True)
    assert services.audience_size(campaign.pk) == 1
    services.send_now(actor=admin, campaign_id=campaign.pk)
    while services.send_batch(campaign.pk):
        pass
    row = CampaignRecipient.objects.get(campaign=campaign)
    assert row.status == "sent" and row.subscriber is not None
    mail = sent_emails[-1]
    assert mail.to == "reader@example.com" and mail.stream == "marketing"
    one_click = re.search(
        r"newsletter/unsubscribe\?token=([^>]+)>", mail.headers["List-Unsubscribe"]
    )
    assert one_click

    assert api_client.post(f"{LEAVE}?token={one_click.group(1)}").status_code == 200
    assert NewsletterSubscriber.objects.get().status == "unsubscribed"
    assert notifications.is_suppressed("reader@example.com")
    assert services.audience_size(campaign.pk) == 0


def test_signing_up_again_after_leaving_needs_a_new_confirmation(api_client, sent_emails):
    newsletter.subscribe("reader@example.com")
    row = newsletter.confirm(newsletter.confirm_token("reader@example.com"))
    newsletter.unsubscribe(newsletter.unsubscribe_token(row.pk))
    cache.clear()  # the confirmation email is not resent within ten minutes
    api_client.post(SIGNUP, {"email": "reader@example.com"})
    row.refresh_from_db()
    assert row.status == "pending"
    api_client.post(CONFIRM, {"token": confirm_link(sent_emails, "reader@example.com")})
    row.refresh_from_db()
    assert row.status == "confirmed"
    assert not notifications.is_suppressed("reader@example.com")


def test_admins_see_and_export_subscribers(make_user, client_for):
    newsletter.subscribe("a@example.com")
    newsletter.confirm(newsletter.confirm_token("a@example.com"))
    newsletter.subscribe("b@example.com")
    admin = make_user(roles=("community_admin",), email="boss@example.com")
    client = client_for(admin, mfa_age=5)
    page = client.get("/api/v1/admin/newsletter/subscribers").json()
    assert page["totals"] == {"confirmed": 1, "pending": 1, "unsubscribed": 0}
    assert {r["email"] for r in page["results"]} == {"a@example.com", "b@example.com"}
    export = client.get("/api/v1/admin/newsletter/subscribers/export")
    body = b"".join(export.streaming_content).decode()
    assert "a@example.com" in body and "b@example.com" not in body  # confirmed only
