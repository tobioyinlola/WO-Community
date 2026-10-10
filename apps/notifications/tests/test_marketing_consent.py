import pytest
from django.utils import timezone

from apps.accounts import services as accounts
from apps.accounts.models import ConsentRecord
from apps.notifications import services

pytestmark = pytest.mark.django_db

URL = "/api/v1/me/marketing-consent"


@pytest.fixture
def member(make_user):
    return make_user(
        email="m@example.com", approved_at=timezone.now(), email_verified_at=timezone.now()
    )


@pytest.fixture
def client(member, client_for):
    return client_for(member)


def test_the_default_is_no(client):
    assert client.get(URL).json() == {"granted": False}


def test_agreeing_is_recorded_with_a_version_and_can_be_withdrawn(client, member):
    assert client.put(URL, {"granted": True}, format="json").json() == {"granted": True}
    assert client.get(URL).json() == {"granted": True}
    latest = ConsentRecord.objects.filter(user=member, document="marketing").latest("created_at")
    assert latest.granted is True and latest.version == "1"
    client.put(URL, {"granted": False}, format="json")
    assert client.get(URL).json() == {"granted": False}
    assert ConsentRecord.objects.filter(user=member, document="marketing").count() == 2  # a history


def test_withdrawing_suppresses_the_address_at_once(client):
    client.put(URL, {"granted": True}, format="json")
    client.put(URL, {"granted": False}, format="json")
    assert services.is_suppressed("m@example.com")


def test_agreeing_again_lifts_an_unsubscribe_but_never_a_bounce_or_complaint(client, make_user):
    client.put(URL, {"granted": False}, format="json")
    client.put(URL, {"granted": True}, format="json")
    assert not services.is_suppressed("m@example.com")
    services.suppress("m@example.com", "bounced")
    client.put(URL, {"granted": True}, format="json")
    assert services.is_suppressed("m@example.com")


def test_the_member_is_mailable_only_while_consent_stands(client, member):
    assert not accounts.has_marketing_consent(member.pk)
    client.put(URL, {"granted": True}, format="json")
    assert accounts.has_marketing_consent(member.pk)
    client.put(URL, {"granted": False}, format="json")
    assert not accounts.has_marketing_consent(member.pk)


@pytest.mark.parametrize("body", [{}, {"granted": "maybe"}, {"granted": True, "x": 1}])
def test_bad_requests_are_refused(client, body):
    assert client.put(URL, body, format="json").status_code == 400


def test_consent_needs_an_active_member(api_client, make_user, client_for):
    assert api_client.get(URL).status_code == 401
    assert api_client.put(URL, {"granted": True}, format="json").status_code == 401
    assert (
        client_for(make_user(email="p@example.com", status="pending")).get(URL).status_code == 403
    )


def test_each_member_controls_only_their_own_consent(client, member, make_user, client_for):
    other = make_user(
        email="o@example.com", approved_at=timezone.now(), email_verified_at=timezone.now()
    )
    client.put(URL, {"granted": True}, format="json")
    assert client_for(other).get(URL).json() == {"granted": False}
