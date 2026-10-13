import pytest
from rest_framework.throttling import ScopedRateThrottle

from apps.support.models import SupportTicket

pytestmark = pytest.mark.django_db

CONTACT = "/api/v1/support/contact"
GOOD = {
    "name": "Kemi Adeyemi",
    "email": "kemi@example.com",
    "subject": "Cannot sign in to my account",
    "message": "The page says my password is wrong but I just reset it today.",
}


def test_someone_who_cannot_sign_in_can_ask_for_help(api_client, sent_emails):
    response = api_client.post(CONTACT, GOOD, format="json")
    assert response.status_code == 202
    ticket = SupportTicket.objects.get()
    assert ticket.member_id is None and ticket.email == "kemi@example.com"
    assert ticket.category == "account" and ticket.status == "open"
    assert ticket.messages.count() == 1


def test_they_are_told_it_arrived_without_being_invited_to_reply_by_email(api_client, sent_emails):
    api_client.post(CONTACT, GOOD, format="json")
    assert len(sent_emails) == 1
    mail = sent_emails[0]
    assert mail.to == "kemi@example.com" and mail.no_reply is True
    assert "do not reply" in mail.text_body.lower()


def test_a_filled_hidden_field_means_a_bot_and_nothing_is_kept(api_client, sent_emails):
    response = api_client.post(CONTACT, {**GOOD, "website": "https://spam.test"}, format="json")
    assert response.status_code == 202
    assert SupportTicket.objects.count() == 0 and sent_emails == []


@pytest.mark.parametrize(
    "overrides",
    [
        {"name": "K"},
        {"email": "not-an-email"},
        {"subject": "Four"},
        {"message": "Too short"},
        {"message": "x" * 4001},
        {"extra": "field"},
    ],
)
def test_a_bad_form_is_refused(api_client, overrides):
    assert api_client.post(CONTACT, {**GOOD, **overrides}, format="json").status_code == 400
    assert SupportTicket.objects.count() == 0


def test_the_form_is_throttled(api_client, monkeypatch):
    monkeypatch.setattr(ScopedRateThrottle, "THROTTLE_RATES", {"support_contact": "2/hour"})
    statuses = [api_client.post(CONTACT, GOOD, format="json").status_code for _ in range(3)]
    assert statuses == [202, 202, 429]


def test_markup_in_the_message_is_not_kept(api_client):
    api_client.post(
        CONTACT,
        {**GOOD, "message": "<script>alert(1)</script> I need help signing in please."},
        format="json",
    )
    assert "<script" not in SupportTicket.objects.get().messages.get().body
