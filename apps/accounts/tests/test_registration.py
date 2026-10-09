from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.throttling import ScopedRateThrottle

from apps.accounts.models import ConsentRecord, EmailToken, User
from apps.accounts.tests.helpers import (
    LOGIN_URL,
    PASSWORD,
    REGISTER_URL,
    RESET_URL,
    VERIFY_URL,
    registration_payload,
)
from apps.core.models import OutboxEvent

pytestmark = pytest.mark.django_db


def test_registration_creates_a_pending_unverified_account(api_client):
    response = api_client.post(REGISTER_URL, registration_payload())
    assert response.status_code == 202
    user = User.objects.get(email="new.member@example.com")
    assert user.status == "pending"
    assert user.email_verified_at is None
    assert user.check_password(PASSWORD)
    assert user.password != PASSWORD


def test_consents_are_recorded_with_versions(api_client):
    api_client.post(REGISTER_URL, registration_payload(marketing_consent=True))
    records = {c.document: c for c in ConsentRecord.objects.all()}
    assert set(records) == {"terms", "privacy", "conduct", "marketing"}
    assert all(r.granted for r in records.values())
    assert records["terms"].version == "1"


def test_marketing_consent_defaults_to_not_granted(api_client):
    api_client.post(REGISTER_URL, registration_payload())
    assert ConsentRecord.objects.get(document="marketing").granted is False


def test_verification_email_is_sent_with_a_working_link(
    api_client, run_outbox, last_token, sent_emails
):
    api_client.post(REGISTER_URL, registration_payload())
    assert run_outbox() == 2  # the verification email and the signup details
    message = sent_emails[-1]
    assert message.to == "new.member@example.com"
    assert "https://app.test/verify-email?token=" in message.text_body
    response = api_client.post(VERIFY_URL, {"token": last_token()})
    assert response.status_code == 200
    assert User.objects.get().email_verified_at is not None


def test_only_the_token_hash_is_stored(api_client, run_outbox, last_token):
    api_client.post(REGISTER_URL, registration_payload())
    run_outbox()
    raw = last_token()
    assert not EmailToken.objects.filter(token_hash=raw).exists()
    assert EmailToken.objects.count() == 1
    assert raw not in str(list(OutboxEvent.objects.values_list("payload", flat=True)))


def test_verification_token_is_single_use(api_client, run_outbox, last_token):
    api_client.post(REGISTER_URL, registration_payload())
    run_outbox()
    token = last_token()
    assert api_client.post(VERIFY_URL, {"token": token}).status_code == 200
    again = api_client.post(VERIFY_URL, {"token": token})
    assert again.status_code == 400
    assert again.json()["code"] == "validation_error"


def test_expired_verification_token_is_rejected(api_client, run_outbox, last_token):
    api_client.post(REGISTER_URL, registration_payload())
    run_outbox()
    EmailToken.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
    assert api_client.post(VERIFY_URL, {"token": last_token()}).status_code == 400


def test_unknown_verification_token_is_rejected(api_client):
    assert api_client.post(VERIFY_URL, {"token": "nope"}).status_code == 400


def test_verification_link_cannot_be_used_to_reset_a_password(api_client, run_outbox, last_token):
    api_client.post(REGISTER_URL, registration_payload())
    run_outbox()
    response = api_client.post(
        RESET_URL, {"token": last_token(), "password": "another-long-passphrase"}
    )
    assert response.status_code == 400


def test_duplicate_registration_looks_identical_and_emails_the_owner(
    api_client, make_user, run_outbox, sent_emails
):
    make_user(email="taken@example.com")
    fresh = api_client.post(REGISTER_URL, registration_payload(email="fresh@example.com"))
    duplicate = api_client.post(REGISTER_URL, registration_payload(email="taken@example.com"))
    assert duplicate.status_code == fresh.status_code == 202
    assert duplicate.json() == fresh.json()
    assert User.objects.filter(email__iexact="taken@example.com").count() == 1
    run_outbox()
    to_owner = [m for m in sent_emails if m.to == "taken@example.com"]
    assert len(to_owner) == 1
    assert "already exists" in to_owner[0].text_body


def test_duplicate_check_ignores_case(api_client, make_user):
    make_user(email="taken@example.com")
    response = api_client.post(REGISTER_URL, registration_payload(email="TAKEN@Example.com"))
    assert response.status_code == 202
    assert User.objects.count() == 1


@pytest.mark.parametrize("missing", ["accepted_terms", "accepted_privacy", "accepted_conduct"])
def test_each_required_consent_must_be_accepted(api_client, missing):
    response = api_client.post(REGISTER_URL, registration_payload(**{missing: False}))
    assert response.status_code == 400
    assert missing in response.json()["errors"]
    assert User.objects.count() == 0


@pytest.mark.parametrize("password", ["short", "password1234", "1234567890123"])
def test_weak_passwords_are_rejected(api_client, password):
    response = api_client.post(REGISTER_URL, registration_payload(password=password))
    assert response.status_code == 400
    assert User.objects.count() == 0


def test_invalid_email_is_rejected(api_client):
    response = api_client.post(REGISTER_URL, registration_payload(email="not-an-email"))
    assert response.status_code == 400


def test_privileged_fields_cannot_be_set_at_registration(api_client):
    response = api_client.post(
        REGISTER_URL, registration_payload(status="active", role="super_admin")
    )
    assert response.status_code == 400
    assert User.objects.count() == 0


def test_registered_account_cannot_log_in_until_email_is_verified(api_client):
    api_client.post(REGISTER_URL, registration_payload())
    response = api_client.post(LOGIN_URL, {"email": "new.member@example.com", "password": PASSWORD})
    assert response.status_code == 403
    assert response.json()["code"] == "email_not_verified"


def test_registration_is_rate_limited_per_address(api_client, monkeypatch):
    monkeypatch.setattr(
        ScopedRateThrottle,
        "THROTTLE_RATES",
        {**ScopedRateThrottle.THROTTLE_RATES, "auth_register": "2/hour"},
    )
    statuses = [
        api_client.post(REGISTER_URL, registration_payload(email=f"p{n}@example.com")).status_code
        for n in range(3)
    ]
    assert statuses == [202, 202, 429]


def test_breached_password_is_rejected_at_registration(api_client):
    response = api_client.post(REGISTER_URL, registration_payload(password="Password123!456"))
    assert response.status_code == 400
    assert User.objects.count() == 0
    assert "breach" in str(response.json()["errors"]).lower()


# --- the profile and startup details on the form ---


def with_profile(**changes):
    profile = registration_payload()["profile"]
    profile.update(changes)
    return registration_payload(profile=profile)


def with_startup(**changes):
    startup = registration_payload()["startup"]
    startup.update(changes)
    return registration_payload(startup=startup)


@pytest.mark.parametrize("section", ["profile", "startup"])
def test_the_profile_and_startup_sections_are_required(api_client, section):
    payload = registration_payload()
    del payload[section]
    response = api_client.post(REGISTER_URL, payload)
    assert response.status_code == 400
    assert section in response.json()["errors"]
    assert User.objects.count() == 0


@pytest.mark.parametrize(
    ("builder", "field", "value"),
    [
        (with_profile, "full_name", "A"),
        (with_profile, "full_name", "<b></b>"),
        (with_profile, "country", "XX"),
        (with_profile, "country", "Nigeria"),
        (with_profile, "city", ""),
        (with_startup, "name", ""),
        (with_startup, "name", "x" * 121),
        (with_startup, "country", "ZZ"),
        (with_startup, "sector", "no-such-sector"),
        (with_startup, "stage", "no-such-stage"),
        (with_startup, "pitch", ""),
        (with_startup, "pitch", "x" * 161),
    ],
)
def test_invalid_details_are_rejected_and_no_account_is_made(api_client, builder, field, value):
    response = api_client.post(REGISTER_URL, builder(**{field: value}))
    assert response.status_code == 400
    section = "profile" if builder is with_profile else "startup"
    assert field in response.json()["errors"][section]
    assert User.objects.count() == 0


def test_unknown_detail_fields_are_rejected(api_client):
    payload = with_profile(role="super_admin")
    assert api_client.post(REGISTER_URL, payload).status_code == 400


def test_country_codes_are_accepted_in_lower_case(api_client):
    response = api_client.post(REGISTER_URL, with_profile(country="ng"))
    assert response.status_code == 202


def test_markup_in_names_is_stripped_before_it_is_stored(api_client):
    from apps.core.models import OutboxEvent

    api_client.post(REGISTER_URL, with_profile(full_name="<b>Ada</b> <script>x</script>Obi"))
    event = OutboxEvent.objects.get(topic="accounts.signup_details_submitted")
    assert event.payload["details"]["profile"]["full_name"] == "Ada Obi"


def test_bad_details_look_the_same_for_new_and_existing_addresses(api_client, make_user):
    make_user(email="taken@example.com")
    fresh = api_client.post(REGISTER_URL, with_profile(country="XX"))
    taken = api_client.post(
        REGISTER_URL, {**with_profile(country="XX"), "email": "taken@example.com"}
    )
    assert fresh.status_code == taken.status_code == 400
    assert fresh.json()["errors"] == taken.json()["errors"]
