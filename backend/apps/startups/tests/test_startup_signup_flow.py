import hashlib

import pytest

from apps.accounts import services as accounts
from apps.accounts.models import Invitation, User
from apps.accounts.tests.helpers import REGISTER_URL, registration_payload
from apps.startups import services
from apps.startups.models import Startup, StartupMember

pytestmark = pytest.mark.django_db

EMAIL = "new.member@example.com"


def test_registering_creates_the_startup_from_the_form(api_client, run_outbox):
    api_client.post(REGISTER_URL, registration_payload())
    run_outbox()
    startup = Startup.objects.get(owner__email=EMAIL)
    assert startup.name == "Ada Pay"
    assert (startup.sector.slug, startup.stage.slug) == ("fintech", "seed")
    assert (startup.country, startup.city) == ("NG", "Lagos")
    assert startup.pitch == "Payments for small traders"
    assert startup.directory_opt_in is False
    assert startup.completeness_score == 15


def test_the_registrant_is_the_founder_on_the_team(api_client, run_outbox):
    api_client.post(REGISTER_URL, registration_payload())
    run_outbox()
    member = StartupMember.objects.get()
    assert (member.user.email, member.is_founder) == (EMAIL, True)


def test_an_existing_address_creates_no_startup(api_client, make_user, run_outbox):
    make_user(email=EMAIL)
    api_client.post(REGISTER_URL, registration_payload())
    run_outbox()
    assert Startup.objects.count() == 0


def test_running_the_handler_twice_creates_one_startup(api_client, run_outbox):
    api_client.post(REGISTER_URL, registration_payload())
    run_outbox()
    user = User.objects.get(email=EMAIL)
    assert services.create_from_signup(user.pk, registration_payload()["startup"]) is None
    assert Startup.objects.filter(owner=user).count() == 1


def test_invited_members_get_their_startup_too(api_client, run_outbox):
    inviter = User.objects.create_user("admin@example.com", "a-long-test-passphrase")
    accounts.create_invitation(actor=inviter, email=EMAIL)
    raw = "known-token-for-test"
    Invitation.objects.update(token_hash=hashlib.sha256(raw.encode()).hexdigest())
    response = api_client.post(REGISTER_URL, registration_payload(invitation_token=raw))
    assert response.status_code == 201
    run_outbox()
    assert Startup.objects.get(owner__email=EMAIL).name == "Ada Pay"


def test_the_new_startup_is_visible_to_its_owner_straight_away(api_client, run_outbox, client_for):
    api_client.post(REGISTER_URL, registration_payload())
    run_outbox()
    user = User.objects.get(email=EMAIL)
    mine = client_for(user).get("/api/v1/me/startups").json()
    assert [s["name"] for s in mine] == ["Ada Pay"]
    assert mine[0]["completeness"]["next_missing_field"] == "description"
