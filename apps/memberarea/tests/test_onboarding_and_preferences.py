import pytest
from django.utils import timezone

from apps.analytics.models import AnalyticsEvent
from apps.notifications import preferences
from apps.notifications.models import NotificationPreference
from apps.profiles.tests.conftest import FULL, patch
from apps.startups.tests.conftest import STARTUPS, new_startup_body

pytestmark = pytest.mark.django_db

ONBOARDING = "/api/v1/me/onboarding"
PREFS = "/api/v1/me/notification-preferences"


@pytest.fixture
def member(make_user):
    return make_user(
        email="m@example.com", approved_at=timezone.now(), email_verified_at=timezone.now()
    )


@pytest.fixture
def client(member, client_for):
    return client_for(member)


def items(client):
    body = client.get(ONBOARDING).json()
    return {item["key"]: item["done"] for item in body["items"]}


def finish_everything(client):
    patch(client, FULL)
    response = client.post(STARTUPS, new_startup_body())
    startup = response.json()["id"]
    etag = client.get(f"{STARTUPS}/{startup}")["ETag"]
    client.put(
        f"{STARTUPS}/{startup}/traction",
        {"metrics": [{"kind": "users", "value": 10}]},
        HTTP_IF_MATCH=etag,
        format="json",
    )
    client.put(PREFS, {"preferences": {}})


# --- the checklist ---


def test_a_new_member_starts_with_nothing_done(client):
    body = client.get(ONBOARDING).json()
    assert [i["key"] for i in body["items"]] == [
        "complete_profile",
        "add_startup",
        "add_traction",
        "set_notification_preferences",
    ]
    assert not any(i["done"] for i in body["items"])
    assert body["complete"] is False
    assert body["profile_completeness"]["score"] == 0
    assert body["profile_completeness"]["next_missing_field"]


def test_each_step_ticks_off_when_it_is_done(client):
    patch(client, FULL)
    assert items(client)["complete_profile"] is True
    startup = client.post(STARTUPS, new_startup_body()).json()["id"]
    assert items(client)["add_startup"] is True
    assert items(client)["add_traction"] is False
    etag = client.get(f"{STARTUPS}/{startup}")["ETag"]
    client.put(
        f"{STARTUPS}/{startup}/traction",
        {"metrics": [{"kind": "users", "value": 3}]},
        HTTP_IF_MATCH=etag,
        format="json",
    )
    assert items(client)["add_traction"] is True
    assert items(client)["set_notification_preferences"] is False
    client.put(PREFS, {"preferences": {}})
    assert items(client)["set_notification_preferences"] is True


def test_a_thin_profile_does_not_count_as_complete(client):
    patch(client, {"full_name": "Ada Obi", "headline": "Founder"})
    assert items(client)["complete_profile"] is False


def test_finishing_records_the_event_once(client, member):
    finish_everything(client)
    body = client.get(ONBOARDING).json()
    assert body["complete"] is True
    client.get(ONBOARDING)
    client.get(ONBOARDING)
    [event] = AnalyticsEvent.objects.filter(name="onboarding_completed")
    assert event.actor_id == member.pk
    assert set(event.properties) == {"time_to_complete_hours"}


def test_nothing_is_recorded_while_steps_are_missing(client):
    patch(client, FULL)
    client.get(ONBOARDING)
    assert not AnalyticsEvent.objects.filter(name="onboarding_completed").exists()


def test_a_team_members_startup_counts_for_them(client, make_user, client_for):
    from apps.startups.models import Startup, StartupMember

    owner = make_user(email="o@example.com", approved_at=timezone.now())
    startup = client_for(owner).post(STARTUPS, new_startup_body()).json()["id"]
    from apps.accounts.models import User

    me = User.objects.get(email="m@example.com")
    StartupMember.objects.create(startup=Startup.objects.get(pk=startup), user=me, title="CTO")
    assert items(client)["add_startup"] is True


def test_the_checklist_needs_a_login(api_client):
    assert api_client.get(ONBOARDING).status_code == 401


def test_one_members_progress_is_not_anothers(client, make_user, client_for):
    finish_everything(client)
    other = make_user(email="x@example.com", approved_at=timezone.now())
    assert not any(client_for(other).get(ONBOARDING).json()["items"][i]["done"] for i in range(4))


# --- notification preferences ---


def test_defaults_before_anything_is_saved(client):
    body = client.get(PREFS).json()
    assert body["confirmed"] is False
    assert body["preferences"]["comments"] == {"email": True, "in_app": True}
    assert body["preferences"]["newsletter"] == {"email": False, "in_app": False}


def test_a_partial_change_is_merged_and_confirms(client, member):
    response = client.put(PREFS, {"preferences": {"comments": {"email": False}}})
    assert response.status_code == 200
    body = response.json()
    assert body["confirmed"] is True
    assert body["preferences"]["comments"] == {"email": False, "in_app": True}
    assert body["preferences"]["mentions"] == {"email": True, "in_app": True}
    assert client.get(PREFS).json() == body
    assert NotificationPreference.objects.get().choices == {"comments": {"email": False}}


def test_changes_build_on_each_other_and_can_be_reverted(client):
    client.put(PREFS, {"preferences": {"comments": {"email": False}}})
    client.put(PREFS, {"preferences": {"mentions": {"in_app": False}}})
    body = client.get(PREFS).json()["preferences"]
    assert body["comments"]["email"] is False and body["mentions"]["in_app"] is False
    client.put(PREFS, {"preferences": {"comments": {"email": True}}})
    assert NotificationPreference.objects.get().choices == {"mentions": {"in_app": False}}


def test_saving_with_no_changes_still_confirms_the_defaults(client):
    assert client.put(PREFS, {"preferences": {}}).json()["confirmed"] is True


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"preferences": {"nonsense": {"email": True}}},
        {"preferences": {"comments": {"sms": True}}},
        {"preferences": {"comments": {"email": "maybe"}}},
        {"preferences": {"comments": {}}},
        {"preferences": {"approvals": {"email": False}}},
        {"preferences": {}, "extra": 1},
    ],
)
def test_invalid_changes_are_refused_and_nothing_is_saved(client, body):
    assert client.put(PREFS, body).status_code == 400
    assert not NotificationPreference.objects.exists()


def test_account_messages_cannot_be_switched_off_but_other_channels_can(client):
    response = client.put(PREFS, {"preferences": {"approvals": {"in_app": False}}})
    assert response.status_code == 200
    assert response.json()["preferences"]["approvals"] == {"email": True, "in_app": False}


def test_preferences_are_private_to_each_member(client, make_user, client_for):
    client.put(PREFS, {"preferences": {"comments": {"email": False}}})
    other = make_user(email="x@example.com", approved_at=timezone.now())
    assert client_for(other).get(PREFS).json()["preferences"]["comments"]["email"] is True


def test_preferences_need_an_active_member(api_client, make_user, client_for):
    assert api_client.get(PREFS).status_code == 401
    assert api_client.put(PREFS, {"preferences": {}}).status_code == 401
    pending = make_user(email="p@example.com", status="pending")
    assert client_for(pending).get(PREFS).status_code == 403


def test_senders_can_ask_whether_to_send(client, member):
    client.put(PREFS, {"preferences": {"comments": {"email": False}}})
    assert preferences.allows(member.pk, "comments", "email") is False
    assert preferences.allows(member.pk, "comments", "in_app") is True
    assert preferences.allows(member.pk, "approvals", "email") is True  # locked on
