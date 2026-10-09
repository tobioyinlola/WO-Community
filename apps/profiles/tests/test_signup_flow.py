import pytest
from django.utils import timezone

from apps.accounts import services as accounts
from apps.accounts.models import User
from apps.accounts.tests.helpers import REGISTER_URL, registration_payload
from apps.core.models import OutboxEvent
from apps.profiles import services
from apps.profiles.models import FounderProfile

pytestmark = pytest.mark.django_db

EMAIL = "new.member@example.com"


def test_registering_creates_the_profile_from_the_form(api_client, run_outbox):
    assert api_client.post(REGISTER_URL, registration_payload()).status_code == 202
    run_outbox()
    profile = FounderProfile.objects.get(user__email=EMAIL)
    assert (profile.full_name, profile.country, profile.city) == ("Ada Founder", "NG", "Lagos")
    assert profile.slug.startswith("ada-founder-")
    assert profile.completeness_score > 0


def test_the_form_details_travel_in_the_outbox_not_in_the_user_table(api_client):
    api_client.post(REGISTER_URL, registration_payload())
    event = OutboxEvent.objects.get(topic="accounts.signup_details_submitted")
    assert event.payload["details"]["profile"]["full_name"] == "Ada Founder"
    assert not hasattr(User.objects.get(email=EMAIL), "full_name")


def test_an_existing_address_creates_nothing(api_client, make_user, run_outbox):
    make_user(email=EMAIL)
    api_client.post(REGISTER_URL, registration_payload())
    run_outbox()
    assert FounderProfile.objects.count() == 0
    assert not OutboxEvent.objects.filter(topic="accounts.signup_details_submitted").exists()


def test_running_the_handler_twice_changes_nothing(api_client, run_outbox):
    api_client.post(REGISTER_URL, registration_payload())
    run_outbox()
    user = User.objects.get(email=EMAIL)
    before = FounderProfile.objects.get(user=user)
    services.create_from_signup(user.pk, {"full_name": "Other Name", "country": "GH", "city": "x"})
    after = FounderProfile.objects.get(user=user)
    assert (after.full_name, after.slug) == (before.full_name, before.slug)
    assert FounderProfile.objects.count() == 1


def test_invited_members_get_their_profile_too(api_client, run_outbox):
    inviter = User.objects.create_user("admin@example.com", "a-long-test-passphrase")
    accounts.create_invitation(actor=inviter, email=EMAIL)
    from apps.accounts.models import Invitation

    raw = "known-token-for-test"
    import hashlib

    Invitation.objects.update(token_hash=hashlib.sha256(raw.encode()).hexdigest())
    response = api_client.post(REGISTER_URL, registration_payload(invitation_token=raw))
    assert response.status_code == 201
    run_outbox()
    user = User.objects.get(email=EMAIL)
    assert user.status == "active"
    assert FounderProfile.objects.get(user=user).full_name == "Ada Founder"


def test_two_members_with_the_same_name_get_different_slugs(api_client, run_outbox):
    api_client.post(REGISTER_URL, registration_payload())
    api_client.post(REGISTER_URL, registration_payload(email="second@example.com"))
    run_outbox()
    slugs = list(FounderProfile.objects.values_list("slug", flat=True))
    assert len(set(slugs)) == 2


def test_the_new_profile_can_be_edited_straight_after(api_client, run_outbox, client_for):
    api_client.post(REGISTER_URL, registration_payload())
    run_outbox()
    user = User.objects.get(email=EMAIL)
    user.email_verified_at = timezone.now()
    user.save()
    client = client_for(user)
    body = client.get("/api/v1/me/profile").json()
    assert body["full_name"] == "Ada Founder"
    assert body["completeness"]["next_missing_field"] == "headline"
