import pytest
from django.core import signing

from apps.accounts import services as accounts
from apps.campaigns import services
from apps.campaigns.models import CampaignRecipient
from apps.campaigns.tests.conftest import make_campaign, subscriber
from apps.notifications import services as notifications

pytestmark = pytest.mark.django_db

URL = "/api/v1/unsubscribe"


def token_for(user, campaign=None):
    return services.unsubscribe_token(user.pk, campaign.pk if campaign else None)


def test_the_link_in_an_email_unsubscribes_with_one_post_and_no_login(api_client, make_user):
    user = subscriber(make_user, "gone@example.com")
    response = api_client.post(URL, {"token": token_for(user)}, format="json")
    assert response.status_code == 200 and response["Cache-Control"] == "no-store"
    assert not accounts.has_marketing_consent(user.pk)
    assert notifications.is_suppressed("gone@example.com")


def test_mail_clients_post_the_token_in_the_query_string(api_client, make_user):
    user = subscriber(make_user, "oneclick@example.com")
    response = api_client.post(f"{URL}?token={token_for(user)}", {"List-Unsubscribe": "One-Click"})
    assert response.status_code == 200
    assert not accounts.has_marketing_consent(user.pk)


def test_the_campaign_is_credited_with_the_unsubscribe(admin, everyone, api_client, make_user):
    user = subscriber(make_user, "gone@example.com")
    campaign = make_campaign(admin, everyone)
    services.send_now(actor=admin, campaign_id=campaign.pk)
    services.send_batch(campaign.pk)
    api_client.post(URL, {"token": token_for(user, campaign)}, format="json")
    assert CampaignRecipient.objects.get(campaign=campaign, user=user).unsubscribed_at is not None
    assert services.report(campaign)["unsubscribed"] == 1


def test_unsubscribing_twice_is_harmless(api_client, make_user):
    user = subscriber(make_user, "twice@example.com")
    token = token_for(user)
    assert api_client.post(URL, {"token": token}, format="json").status_code == 200
    assert api_client.post(URL, {"token": token}, format="json").status_code == 200
    assert notifications.is_suppressed("twice@example.com")


def test_only_marketing_stops_other_mail_keeps_coming(api_client, make_user, sent_emails):
    from apps.notifications import emails

    user = subscriber(make_user, "keep@example.com")
    api_client.post(URL, {"token": token_for(user)}, format="json")
    emails.send_password_reset("keep@example.com", "tok")
    assert sent_emails[-1].stream == "transactional"
    user.refresh_from_db()
    assert user.status == "active"


@pytest.mark.parametrize("token", ["", "garbage", "a:b:c", "x" * 600])
def test_invalid_links_are_refused(api_client, token):
    assert api_client.post(URL, {"token": token}, format="json").status_code == 400


def test_a_link_cannot_be_forged_or_borrowed_from_another_purpose(api_client, make_user):
    victim = subscriber(make_user, "victim@example.com")
    forged = signing.dumps({"u": str(victim.pk), "c": ""}, salt="something-else")
    assert api_client.post(URL, {"token": forged}, format="json").status_code == 400
    tampered = token_for(victim)[:-2] + "xx"
    assert api_client.post(URL, {"token": tampered}, format="json").status_code == 400
    assert accounts.has_marketing_consent(victim.pk)


def test_a_link_for_a_deleted_account_is_accepted_quietly(api_client, make_user):
    user = subscriber(make_user, "deleted@example.com")
    token = token_for(user)
    user.delete()
    assert api_client.post(URL, {"token": token}, format="json").status_code == 200


def test_only_post_is_allowed(api_client, make_user):
    assert api_client.get(URL).status_code == 405


def test_missing_and_extra_fields_are_refused(api_client):
    assert api_client.post(URL, {}, format="json").status_code == 400
    assert api_client.post(URL, {"token": "x", "extra": 1}, format="json").status_code == 400


def test_the_endpoint_is_rate_limited(api_client, monkeypatch):
    from rest_framework.throttling import ScopedRateThrottle

    monkeypatch.setattr(
        ScopedRateThrottle,
        "THROTTLE_RATES",
        {**ScopedRateThrottle.THROTTLE_RATES, "auth_token": "2/min"},
    )
    codes = [api_client.post(URL, {"token": "bad"}, format="json").status_code for _ in range(3)]
    assert codes == [400, 400, 429]
