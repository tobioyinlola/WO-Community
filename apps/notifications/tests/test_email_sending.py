import json

import httpx
import pytest

from apps.integrations.email import (
    MARKETING,
    EmailMessage,
    EmailMisconfigured,
    EmailRejected,
    EmailTemporarilyUnavailable,
)
from apps.integrations.email.fake import FakeEmailAdapter
from apps.notifications import emails, services

pytestmark = pytest.mark.django_db


# --- the fake, used by every other test ---


def test_every_message_carries_a_content_based_idempotency_key_and_a_category(sent_emails):
    emails.send_approved("ada@example.com")
    message = sent_emails[0]
    assert len(message.idempotency_key) == 64
    assert message.tags == {"category": "approved"}
    assert message.stream == "transactional"


def test_identical_messages_share_a_key_and_different_ones_do_not(sent_emails):
    emails.send_approved("ada@example.com")
    emails.send_approved("ada@example.com")
    emails.send_approved("bob@example.com")
    first, second, third = (m.idempotency_key for m in sent_emails)
    assert first == second != third


def test_each_kind_of_email_has_its_own_category(sent_emails):
    from datetime import datetime

    emails.send_verification("a@example.com", "t")
    emails.send_already_registered("a@example.com")
    emails.send_invitation("a@example.com", "t", "", datetime(2026, 10, 20))
    emails.send_approved("a@example.com")
    emails.send_rejected("a@example.com", "reason")
    emails.send_password_reset("a@example.com", "t")
    assert [m.tags["category"] for m in sent_emails] == [
        "verification",
        "already_registered",
        "invitation",
        "approved",
        "rejected",
        "password_reset",
    ]


def test_marketing_mail_skips_suppressed_addresses_but_transactional_mail_does_not(sent_emails):
    services.suppress("ada@example.com", "bounced")
    emails._send("ada@example.com", "News", "body", category="newsletter", stream=MARKETING)
    assert sent_emails == []
    emails.send_password_reset("ada@example.com", "token")
    assert len(sent_emails) == 1


def test_marketing_mail_goes_to_addresses_that_are_not_suppressed(sent_emails):
    emails._send("fine@example.com", "News", "body", category="newsletter", stream=MARKETING)
    assert sent_emails[0].stream == MARKETING


# --- how failures are treated ---


class Failing(FakeEmailAdapter):
    error: Exception | None = None

    def send(self, message: EmailMessage) -> str:
        raise self.error  # type: ignore[misc]


@pytest.fixture
def failing(settings):
    settings.EMAIL_ADAPTER = f"{__name__}.Failing"
    return Failing


def test_a_message_the_provider_will_never_accept_is_dropped_not_retried(failing):
    failing.error = EmailRejected("invalid `to` field", code="validation_error")
    emails.send_approved("not-deliverable@example.com")  # no exception


def test_a_temporary_failure_is_raised_so_the_task_retries(failing):
    failing.error = EmailTemporarilyUnavailable("rate limited", retry_after=2)
    with pytest.raises(EmailTemporarilyUnavailable):
        emails.send_approved("ada@example.com")


def test_a_misconfiguration_is_never_hidden(failing):
    failing.error = EmailMisconfigured("domain is not verified")
    with pytest.raises(EmailMisconfigured):
        emails.send_approved("ada@example.com")


def test_a_rejection_is_logged_without_the_address(failing, caplog):
    import logging

    failing.error = EmailRejected("bad address", code="validation_error")
    with caplog.at_level(logging.WARNING):
        emails.send_approved("secret.person@example.com")
    assert "email_rejected" in caplog.text
    assert "secret.person@example.com" not in caplog.text


# --- end to end through Resend (HTTP mocked) ---


@pytest.fixture
def resend_calls(settings, monkeypatch):
    """Switch to the Resend adapter with a fake Resend behind it."""
    from apps.integrations.email import resend

    calls: list[httpx.Request] = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"id": f"re_{len(calls)}"})

    client = httpx.Client(base_url="https://api.resend.com", transport=httpx.MockTransport(handler))
    settings.EMAIL_ADAPTER = "apps.integrations.email.resend.ResendEmailAdapter"
    monkeypatch.setattr(resend, "_shared_client", lambda key: client)
    return calls


def test_registration_sends_the_verification_email_through_resend(
    api_client, run_outbox, resend_calls
):
    from apps.accounts.tests.helpers import REGISTER_URL, registration_payload

    api_client.post(REGISTER_URL, registration_payload())
    run_outbox()
    [call] = resend_calls
    body = json.loads(call.content)
    assert call.url.path == "/emails"
    assert body["to"] == ["new.member@example.com"]
    assert body["from"] == "WO Community <no-reply@mail.test>"
    assert body["subject"] == "Confirm your email address"
    assert "verify-email?token=" in body["text"]
    assert body["tags"] == [{"name": "category", "value": "verification"}]
    assert len(call.headers["idempotency-key"]) == 64


def test_the_same_notice_triggered_twice_carries_the_same_key(
    api_client, make_user, run_outbox, resend_calls
):
    from apps.accounts.tests.helpers import REGISTER_URL, registration_payload

    make_user(email="taken@example.com")
    for _ in range(2):
        api_client.post(REGISTER_URL, registration_payload(email="taken@example.com"))
        run_outbox()
    first, second = resend_calls
    assert first.headers["idempotency-key"] == second.headers["idempotency-key"]
