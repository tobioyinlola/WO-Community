import json
import time
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.core.models import OutboxEvent
from apps.integrations.tests.helpers import sign
from apps.notifications import services
from apps.notifications.models import DeliveryEvent, Suppression, WebhookDelivery

pytestmark = pytest.mark.django_db

URL = "/api/v1/webhooks/email/resend"


@pytest.fixture(autouse=True)
def _use_resend(settings):
    settings.EMAIL_ADAPTER = "apps.integrations.email.resend.ResendEmailAdapter"


def delivery(kind, *, to="ada@example.com", message_id="em_1", **data):
    return {
        "type": kind,
        "created_at": "2026-10-10T10:00:00.000Z",
        "data": {"email_id": message_id, "to": [to], **data},
    }


def post(client, payload, settings, delivery_id="msg_1", **sign_overrides):
    body = json.dumps(payload).encode()
    headers = sign(body, settings.RESEND_WEBHOOK_SECRET, delivery_id=delivery_id, **sign_overrides)
    extra = {f"HTTP_{k.upper().replace('-', '_')}": v for k, v in headers.items()}
    return client.generic("POST", URL, body, content_type="application/json", **extra)


# --- the front door ---


def test_a_signed_delivery_is_stored_queued_and_acknowledged(api_client, settings):
    response = post(api_client, delivery("email.delivered"), settings)
    assert response.status_code == 200
    assert response.json() == {"status": "accepted"}
    stored = WebhookDelivery.objects.get()
    assert (stored.provider, stored.event_id) == ("resend", "msg_1")
    assert stored.payload["type"] == "email.delivered"
    assert stored.processed_at is None
    assert OutboxEvent.objects.filter(topic="notifications.webhook_received").count() == 1


def test_nothing_is_processed_inside_the_request(api_client, settings):
    post(api_client, delivery("email.bounced", bounce={"type": "Permanent"}), settings)
    assert DeliveryEvent.objects.count() == 0 and Suppression.objects.count() == 0


def test_a_repeated_delivery_is_acknowledged_but_not_stored_twice(api_client, settings):
    payload = delivery("email.delivered")
    assert post(api_client, payload, settings).json() == {"status": "accepted"}
    again = post(api_client, payload, settings)
    assert again.status_code == 200 and again.json() == {"status": "duplicate"}
    assert WebhookDelivery.objects.count() == 1
    assert OutboxEvent.objects.filter(topic="notifications.webhook_received").count() == 1


def test_a_bad_signature_is_refused_and_nothing_is_kept(api_client, settings):
    payload = json.dumps(delivery("email.delivered")).encode()
    headers = sign(payload, settings.RESEND_WEBHOOK_SECRET)
    headers["svix-signature"] = "v1,AAAA"
    extra = {f"HTTP_{k.upper().replace('-', '_')}": v for k, v in headers.items()}
    response = api_client.generic("POST", URL, payload, content_type="application/json", **extra)
    assert response.status_code == 401
    assert WebhookDelivery.objects.count() == 0 and OutboxEvent.objects.count() == 0


def test_unsigned_requests_are_refused(api_client):
    response = api_client.post(URL, delivery("email.delivered"))
    assert response.status_code == 401


def test_a_replayed_old_delivery_is_refused(api_client, settings):
    response = post(
        api_client, delivery("email.delivered"), settings, timestamp=int(time.time()) - 3600
    )
    assert response.status_code == 401


def test_a_body_that_is_not_json_is_a_400_even_when_correctly_signed(api_client, settings):
    body = b"not json at all"
    headers = sign(body, settings.RESEND_WEBHOOK_SECRET)
    extra = {f"HTTP_{k.upper().replace('-', '_')}": v for k, v in headers.items()}
    response = api_client.generic("POST", URL, body, content_type="application/json", **extra)
    assert response.status_code == 400
    assert WebhookDelivery.objects.count() == 0


def test_a_json_list_instead_of_an_object_is_refused(api_client, settings):
    response = post(api_client, [1, 2, 3], settings)
    assert response.status_code == 400


def test_only_the_configured_provider_has_an_endpoint(api_client, settings):
    other = "/api/v1/webhooks/email/sendgrid"
    assert api_client.post(other, delivery("email.delivered")).status_code == 404


def test_the_endpoint_ignores_cookies_and_bearer_tokens(api_client, settings):
    body = json.dumps(delivery("email.delivered")).encode()
    headers = sign(body, settings.RESEND_WEBHOOK_SECRET)
    extra = {f"HTTP_{k.upper().replace('-', '_')}": v for k, v in headers.items()}
    response = api_client.generic(
        "POST",
        URL,
        body,
        content_type="application/json",
        HTTP_AUTHORIZATION="Bearer garbage",
        **extra,
    )
    assert response.status_code == 200


def test_the_endpoint_is_documented_in_the_schema(api_client):
    paths = api_client.get("/api/v1/schema/", HTTP_ACCEPT="application/vnd.oai.openapi+json").json()
    assert "/api/v1/webhooks/email/{provider}" in paths["paths"]


# --- processing ---


def run(api_client, settings, run_outbox, payload, delivery_id="msg_1"):
    post(api_client, payload, settings, delivery_id=delivery_id)
    run_outbox()


def test_a_delivered_report_is_recorded_with_a_hashed_address(api_client, settings, run_outbox):
    run(api_client, settings, run_outbox, delivery("email.delivered"))
    event = DeliveryEvent.objects.get()
    assert (event.kind, event.provider_message_id) == ("delivered", "em_1")
    assert event.email_hash == services.hash_email("ada@example.com")
    assert "ada@example.com" not in event.email_hash
    assert WebhookDelivery.objects.get().processed_at is not None
    assert Suppression.objects.count() == 0


def test_a_permanent_bounce_suppresses_the_address(api_client, settings, run_outbox):
    run(api_client, settings, run_outbox, delivery("email.bounced", bounce={"type": "Permanent"}))
    suppression = Suppression.objects.get()
    assert suppression.reason == "bounced"
    assert services.is_suppressed("ADA@example.com")


def test_a_complaint_suppresses_the_address(api_client, settings, run_outbox):
    run(api_client, settings, run_outbox, delivery("email.complained"))
    assert Suppression.objects.get().reason == "complained"


@pytest.mark.parametrize(
    "payload",
    [
        delivery("email.bounced", bounce={"type": "Transient"}),
        delivery("email.delivery_delayed"),
        delivery("email.opened"),
        delivery("email.clicked"),
        delivery("email.sent"),
        delivery("email.failed"),
    ],
)
def test_other_outcomes_never_suppress(api_client, settings, run_outbox, payload):
    run(api_client, settings, run_outbox, payload)
    assert DeliveryEvent.objects.count() == 1 and Suppression.objects.count() == 0


def test_events_we_do_not_use_are_stored_and_ignored(api_client, settings, run_outbox):
    run(api_client, settings, run_outbox, {"type": "domain.updated", "data": {}})
    assert DeliveryEvent.objects.count() == 0
    assert WebhookDelivery.objects.get().processed_at is not None


def test_each_recipient_of_one_message_is_handled(api_client, settings, run_outbox):
    payload = delivery("email.complained")
    payload["data"]["to"] = ["a@example.com", "b@example.com"]
    run(api_client, settings, run_outbox, payload)
    assert Suppression.objects.count() == 2


def test_processing_twice_changes_nothing(api_client, settings, run_outbox):
    from apps.integrations.email import get_email_adapter

    run(api_client, settings, run_outbox, delivery("email.complained"))
    stored = WebhookDelivery.objects.get()
    assert services.process_delivery(stored.pk, get_email_adapter()) == 0
    assert DeliveryEvent.objects.count() == 1 and Suppression.objects.count() == 1


def test_a_suppressed_address_stays_suppressed_with_its_first_reason(
    api_client, settings, run_outbox
):
    run(api_client, settings, run_outbox, delivery("email.bounced", bounce={"type": "Permanent"}))
    run(api_client, settings, run_outbox, delivery("email.complained"), delivery_id="msg_2")
    assert Suppression.objects.count() == 1
    assert Suppression.objects.get().reason == "bounced"


# --- suppression ---


def test_addresses_are_matched_regardless_of_case_and_spacing():
    services.suppress(" Ada@Example.COM ", "bounced")
    assert services.is_suppressed("ada@example.com")
    assert not services.is_suppressed("other@example.com")


# --- housekeeping ---


def test_old_processed_deliveries_are_purged_but_recent_and_unprocessed_ones_are_not(settings):
    old = WebhookDelivery.objects.create(provider="resend", event_id="old", payload={})
    recent = WebhookDelivery.objects.create(provider="resend", event_id="recent", payload={})
    unprocessed = WebhookDelivery.objects.create(provider="resend", event_id="open", payload={})
    long_ago = timezone.now() - timedelta(days=settings.EMAIL_WEBHOOK_RETENTION_DAYS + 1)
    WebhookDelivery.objects.filter(pk__in=[old.pk, unprocessed.pk]).update(created_at=long_ago)
    WebhookDelivery.objects.filter(pk__in=[old.pk, recent.pk]).update(processed_at=timezone.now())
    assert services.purge_old_deliveries() == 1
    assert set(WebhookDelivery.objects.values_list("event_id", flat=True)) == {"recent", "open"}
