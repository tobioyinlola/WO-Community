import smtplib
from unittest.mock import MagicMock

import pytest

from apps.integrations.email.base import (
    MARKETING,
    EmailMessage,
    EmailTemporarilyUnavailable,
)
from apps.integrations.email.smtp import SmtpEmailAdapter


def test_sends_a_two_part_message_from_the_right_stream(monkeypatch, settings):
    settings.EMAIL_FROM_TRANSACTIONAL = "WO <no-reply@mail.example.com>"
    settings.EMAIL_FROM_MARKETING = "WO <news@news.example.com>"
    server = MagicMock()
    monkeypatch.setattr(smtplib, "SMTP", lambda *a, **k: MagicMock(__enter__=lambda s: server))
    adapter = SmtpEmailAdapter()
    adapter.send(
        EmailMessage(to="a@example.com", subject="Hi", text_body="plain", html_body="<p>x</p>")
    )
    sent = server.send_message.call_args.args[0]
    assert sent["From"] == "WO <no-reply@mail.example.com>"
    assert sent["To"] == "a@example.com"
    assert [p.get_content_type() for p in sent.iter_parts()] == ["text/plain", "text/html"]

    adapter.send(EmailMessage(to="a@example.com", subject="N", text_body="t", stream=MARKETING))
    assert server.send_message.call_args.args[0]["From"] == "WO <news@news.example.com>"


def test_a_server_that_is_down_is_retryable(monkeypatch):
    def refuse(*args, **kwargs):
        raise ConnectionRefusedError

    monkeypatch.setattr(smtplib, "SMTP", refuse)
    with pytest.raises(EmailTemporarilyUnavailable):
        SmtpEmailAdapter().send(EmailMessage(to="a@example.com", subject="x", text_body="y"))


def test_it_accepts_no_webhooks():
    adapter = SmtpEmailAdapter()
    assert adapter.verify_webhook(b"{}", {}) is False
    assert adapter.parse_event({}) == []
