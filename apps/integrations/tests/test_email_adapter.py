from apps.integrations.email import EmailMessage, get_email_adapter
from apps.integrations.email.fake import FakeEmailAdapter


def test_settings_select_the_fake_adapter_in_tests():
    assert isinstance(get_email_adapter(), FakeEmailAdapter)


def test_fake_adapter_records_messages_without_sending():
    adapter = get_email_adapter()
    message = EmailMessage(to="a@example.com", subject="Hi", text_body="Hello")
    ids = adapter.send_batch([message, message])
    assert len(set(ids)) == 2
    assert FakeEmailAdapter.sent == [message, message]


def test_fake_adapter_webhook_and_event_parsing():
    adapter = get_email_adapter()
    assert adapter.verify_webhook(b"{}", {"X-Fake-Signature": "valid"})
    assert not adapter.verify_webhook(b"{}", {})
    events = adapter.parse_event(
        {"events": [{"kind": "bounced", "message_id": "m1", "email": "a@example.com"}]}
    )
    assert events[0].kind == "bounced"
