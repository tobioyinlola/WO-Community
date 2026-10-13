import base64
import json
import time

import httpx
import pytest
from django.core.exceptions import ImproperlyConfigured

from apps.integrations.email import (
    MARKETING,
    EmailMessage,
    EmailMisconfigured,
    EmailRejected,
    EmailTemporarilyUnavailable,
)
from apps.integrations.email.resend import ResendEmailAdapter
from apps.integrations.tests.helpers import sign


class Recorder:
    """A fake Resend: records requests and answers with a canned response."""

    def __init__(self, response=None):
        self.requests: list[httpx.Request] = []
        self.response = response or (lambda request: httpx.Response(200, json={"id": "msg_1"}))

    def __call__(self, request):
        self.requests.append(request)
        return self.response(request)

    @property
    def body(self):
        return json.loads(self.requests[-1].content)


def make(recorder):
    client = httpx.Client(
        base_url="https://api.resend.com", transport=httpx.MockTransport(recorder)
    )
    return ResendEmailAdapter(client=client)


MESSAGE = EmailMessage(to="ada@example.com", subject="Hello", text_body="Plain body")


# --- sending ---


def test_a_transactional_message_is_posted_with_the_transactional_sender():
    recorder = Recorder()
    message_id = make(recorder).send(MESSAGE)
    assert message_id == "msg_1"
    request = recorder.requests[0]
    assert (request.method, request.url.path) == ("POST", "/emails")
    assert recorder.body == {
        "from": "WO Community <no-reply@mail.test>",
        "to": ["ada@example.com"],
        "subject": "Hello",
        "text": "Plain body",
    }


def test_a_marketing_message_uses_the_marketing_sender_and_extras():
    recorder = Recorder()
    message = EmailMessage(
        to="ada@example.com",
        subject="News",
        text_body="t",
        html_body="<p>t</p>",
        stream=MARKETING,
        reply_to="team@example.com",
        headers={"List-Unsubscribe": "<https://app.test/unsub>"},
        tags={"category": "newsletter"},
    )
    make(recorder).send(message)
    assert recorder.body["from"] == "WO Community <community@news.test>"
    assert recorder.body["html"] == "<p>t</p>"
    assert recorder.body["reply_to"] == "team@example.com"
    assert recorder.body["headers"] == {"List-Unsubscribe": "<https://app.test/unsub>"}
    assert recorder.body["tags"] == [{"name": "category", "value": "newsletter"}]


def test_the_default_reply_address_comes_from_settings(settings):
    settings.EMAIL_REPLY_TO = "help@example.com"
    recorder = Recorder()
    make(recorder).send(MESSAGE)
    assert recorder.body["reply_to"] == "help@example.com"


def test_the_idempotency_key_is_sent_only_when_given():
    recorder = Recorder()
    adapter = make(recorder)
    adapter.send(MESSAGE)
    assert "idempotency-key" not in recorder.requests[0].headers
    adapter.send(
        EmailMessage(to="a@example.com", subject="s", text_body="b", idempotency_key="k" * 300)
    )
    assert recorder.requests[1].headers["idempotency-key"] == "k" * 256


def test_the_shared_client_authenticates_with_the_api_key(settings):
    settings.RESEND_API_KEY = "re_secret_value"  # noqa: S105
    from apps.integrations.email import resend

    resend._shared_client.cache_clear()
    client = ResendEmailAdapter().client
    assert client.headers["authorization"] == "Bearer re_secret_value"
    assert str(client.base_url).startswith("https://api.resend.com")
    resend._shared_client.cache_clear()


def test_a_missing_api_key_fails_at_construction(settings):
    settings.RESEND_API_KEY = ""
    with pytest.raises(ImproperlyConfigured):
        ResendEmailAdapter()


# --- batches ---


def test_batches_are_split_at_one_hundred_and_ids_stay_in_order():
    counter = iter(range(1000))

    def respond(request):
        items = json.loads(request.content)
        return httpx.Response(200, json={"data": [{"id": f"m{next(counter)}"} for _ in items]})

    recorder = Recorder(respond)
    messages = [
        EmailMessage(to=f"p{n}@example.com", subject="s", text_body="b") for n in range(250)
    ]
    ids = make(recorder).send_batch(messages)
    assert ids == [f"m{n}" for n in range(250)]
    assert [len(json.loads(r.content)) for r in recorder.requests] == [100, 100, 50]
    assert all(r.url.path == "/emails/batch" for r in recorder.requests)


def test_an_empty_batch_sends_nothing():
    recorder = Recorder()
    assert make(recorder).send_batch([]) == []
    assert recorder.requests == []


# --- failures ---


def failing(status, body=None, headers=None):
    return Recorder(lambda request: httpx.Response(status, json=body, headers=headers))


@pytest.mark.parametrize("status", [401, 403])
def test_credential_and_domain_problems_are_a_misconfiguration(status):
    recorder = failing(status, {"name": "restricted_api_key", "message": "no access"})
    with pytest.raises(EmailMisconfigured, match="no access"):
        make(recorder).send(MESSAGE)


@pytest.mark.parametrize("status", [400, 404, 422])
def test_messages_resend_will_never_accept_are_rejected_for_good(status):
    recorder = failing(status, {"name": "validation_error", "message": "invalid `to` field"})
    with pytest.raises(EmailRejected) as caught:
        make(recorder).send(MESSAGE)
    assert caught.value.code == "validation_error"
    assert "invalid" in str(caught.value)


def test_rate_limits_are_retryable_and_report_the_wait():
    recorder = failing(
        429, {"name": "rate_limit_exceeded", "message": "slow down"}, {"retry-after": "3"}
    )
    with pytest.raises(EmailTemporarilyUnavailable) as caught:
        make(recorder).send(MESSAGE)
    assert caught.value.retry_after == 3.0


@pytest.mark.parametrize("status", [500, 502, 503, 504])
def test_provider_errors_are_retryable(status):
    with pytest.raises(EmailTemporarilyUnavailable):
        make(failing(status, {"name": "application_error", "message": "oops"})).send(MESSAGE)


def test_an_error_page_instead_of_json_is_still_handled():
    recorder = Recorder(lambda request: httpx.Response(502, text="<html>Bad gateway</html>"))
    with pytest.raises(EmailTemporarilyUnavailable):
        make(recorder).send(MESSAGE)


@pytest.mark.parametrize(
    "error", [httpx.ConnectTimeout("t"), httpx.ReadTimeout("t"), httpx.ConnectError("c")]
)
def test_network_trouble_is_retryable(error):
    def boom(request):
        raise error

    with pytest.raises(EmailTemporarilyUnavailable):
        make(Recorder(boom)).send(MESSAGE)


def test_a_simultaneous_duplicate_is_retryable_but_a_conflicting_one_is_not():
    busy = failing(409, {"name": "concurrent_idempotent_requests", "message": "in flight"})
    with pytest.raises(EmailTemporarilyUnavailable):
        make(busy).send(MESSAGE)
    clash = failing(409, {"name": "invalid_idempotent_request", "message": "different payload"})
    with pytest.raises(EmailRejected):
        make(clash).send(MESSAGE)


def test_a_failure_in_one_batch_chunk_stops_the_rest():
    recorder = failing(500, {"message": "down"})
    with pytest.raises(EmailTemporarilyUnavailable):
        make(recorder).send_batch(
            [EmailMessage(to=f"p{n}@example.com", subject="s", text_body="b") for n in range(150)]
        )
    assert len(recorder.requests) == 1


# --- webhook signatures ---


@pytest.fixture
def adapter():
    return ResendEmailAdapter(client=httpx.Client())


def test_a_correctly_signed_delivery_verifies(adapter, settings):
    body = b'{"type":"email.delivered"}'
    assert adapter.verify_webhook(body, sign(body, settings.RESEND_WEBHOOK_SECRET))


def test_a_changed_body_fails(adapter, settings):
    headers = sign(b'{"type":"email.delivered"}', settings.RESEND_WEBHOOK_SECRET)
    assert not adapter.verify_webhook(b'{"type":"email.bounced"}', headers)


def test_a_signature_made_with_another_secret_fails(adapter):
    other = "whsec_" + base64.b64encode(b"some-other-secret-value").decode()
    body = b"{}"
    assert not adapter.verify_webhook(body, sign(body, other))


def test_the_delivery_id_and_timestamp_are_covered_by_the_signature(adapter, settings):
    body = b"{}"
    headers = sign(body, settings.RESEND_WEBHOOK_SECRET)
    assert not adapter.verify_webhook(body, {**headers, "svix-id": "msg_other"})
    assert not adapter.verify_webhook(
        body, {**headers, "svix-timestamp": str(int(time.time()) + 1)}
    )


@pytest.mark.parametrize("offset", [-301, 301, -86400])
def test_old_or_future_deliveries_are_refused_so_captures_cannot_be_replayed(
    adapter, settings, offset
):
    body = b"{}"
    headers = sign(body, settings.RESEND_WEBHOOK_SECRET, timestamp=int(time.time()) + offset)
    assert not adapter.verify_webhook(body, headers)


def test_a_delivery_inside_the_tolerance_passes(adapter, settings):
    body = b"{}"
    headers = sign(body, settings.RESEND_WEBHOOK_SECRET, timestamp=int(time.time()) - 200)
    assert adapter.verify_webhook(body, headers)


def test_any_one_valid_signature_is_enough_during_secret_rotation(adapter, settings):
    body = b"{}"
    headers = sign(body, settings.RESEND_WEBHOOK_SECRET)
    stale = "v1," + base64.b64encode(b"x" * 32).decode()
    assert adapter.verify_webhook(
        body, {**headers, "svix-signature": f"{stale} {headers['svix-signature']}"}
    )


def test_unknown_signature_versions_do_not_count(adapter, settings):
    body = b"{}"
    assert not adapter.verify_webhook(
        body, sign(body, settings.RESEND_WEBHOOK_SECRET, versions=("v2",))
    )


@pytest.mark.parametrize("missing", ["svix-id", "svix-timestamp", "svix-signature"])
def test_missing_headers_fail(adapter, settings, missing):
    body = b"{}"
    headers = sign(body, settings.RESEND_WEBHOOK_SECRET)
    del headers[missing]
    assert not adapter.verify_webhook(body, headers)


@pytest.mark.parametrize("stamp", ["soon", "", "1e9", "-"])
def test_a_nonsense_timestamp_fails(adapter, settings, stamp):
    body = b"{}"
    headers = {**sign(body, settings.RESEND_WEBHOOK_SECRET), "svix-timestamp": stamp}
    assert not adapter.verify_webhook(body, headers)


def test_nothing_verifies_when_no_secret_is_configured(adapter, settings):
    body = b"{}"
    headers = sign(body, settings.RESEND_WEBHOOK_SECRET)
    settings.RESEND_WEBHOOK_SECRET = ""
    assert not adapter.verify_webhook(body, headers)


def test_the_delivery_id_comes_from_the_svix_header(adapter):
    assert adapter.webhook_event_id({"svix-id": "msg_123"}) == "msg_123"
    assert adapter.webhook_event_id({}) == ""


# --- understanding events ---


def event(kind, **data):
    return {
        "type": kind,
        "created_at": "2026-10-10T10:00:00.000Z",
        "data": {"email_id": "em_1", "to": ["Ada@Example.com"], **data},
    }


@pytest.mark.parametrize(
    ("resend_type", "kind"),
    [
        ("email.sent", "sent"),
        ("email.delivered", "delivered"),
        ("email.delivery_delayed", "delayed"),
        ("email.complained", "complained"),
        ("email.opened", "opened"),
        ("email.clicked", "clicked"),
        ("email.failed", "failed"),
    ],
)
def test_events_are_translated(adapter, resend_type, kind):
    [parsed] = adapter.parse_event(event(resend_type))
    assert (parsed.kind, parsed.provider_message_id) == (kind, "em_1")
    assert parsed.email == "ada@example.com"
    assert parsed.occurred_at == "2026-10-10T10:00:00.000Z"


def test_a_permanent_bounce_is_a_bounce_and_other_bounces_are_soft(adapter):
    [hard] = adapter.parse_event(event("email.bounced", bounce={"type": "Permanent"}))
    [soft] = adapter.parse_event(event("email.bounced", bounce={"type": "Transient"}))
    [unknown] = adapter.parse_event(event("email.bounced"))
    assert (hard.kind, soft.kind, unknown.kind) == ("bounced", "soft_bounced", "soft_bounced")


def test_every_recipient_gets_its_own_event(adapter):
    parsed = adapter.parse_event(event("email.delivered", to=["a@example.com", "b@example.com"]))
    assert [e.email for e in parsed] == ["a@example.com", "b@example.com"]


@pytest.mark.parametrize(
    "payload",
    [
        {"type": "email.received", "data": {"email_id": "x", "to": ["a@example.com"]}},
        {"type": "domain.updated", "data": {}},
        {"type": "email.delivered", "data": {"to": ["a@example.com"]}},
        {"type": "email.delivered"},
        {},
    ],
)
def test_unknown_or_incomplete_events_are_ignored(adapter, payload):
    assert adapter.parse_event(payload) == []
