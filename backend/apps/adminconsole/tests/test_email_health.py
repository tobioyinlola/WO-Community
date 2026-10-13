from datetime import date

import pytest

from apps.audit.models import AuditLog
from apps.notifications import services, warmup
from apps.notifications.models import DeliveryEvent, Suppression, WebhookDelivery
from apps.notifications.tests.fake_dns import FakeResolver

pytestmark = pytest.mark.django_db

HEALTH = "/api/v1/admin/email/health"
SUPPRESSIONS = "/api/v1/admin/email/suppressions"


@pytest.fixture(autouse=True)
def dns(settings):
    settings.EMAIL_FROM_TRANSACTIONAL = "WO Community <no-reply@mail.example.org>"
    settings.EMAIL_FROM_MARKETING = "WO Community <news@news.example.org>"
    settings.EMAIL_DKIM_SELECTORS = ["resend"]
    FakeResolver.records = {}
    yield FakeResolver.records
    FakeResolver.records = {}


@pytest.fixture
def admin_client(make_user, client_for):
    return client_for(make_user(roles=("community_admin",)), mfa_age=5)


@pytest.fixture
def boss_client(make_user, client_for):
    return client_for(make_user(roles=("super_admin",)), mfa_age=5)


def checks(response, domain):
    [found] = [d for d in response.json()["domains"] if d["domain"] == domain]
    return {c["key"]: c for c in found["checks"]}


def test_missing_records_are_reported_as_missing(admin_client):
    result = checks(admin_client.get(HEALTH), "mail.example.org")
    assert {k: v["status"] for k, v in result.items()} == {
        "spf": "missing",
        "dkim": "missing",
        "dmarc": "missing",
    }


def test_published_records_are_recognised(admin_client, dns):
    dns["mail.example.org"] = ["v=spf1 include:amazonses.com ~all"]
    dns["resend._domainkey.mail.example.org"] = ["v=DKIM1; k=rsa; p=MIGfMA0"]
    dns["_dmarc.mail.example.org"] = ["v=DMARC1; p=none; rua=mailto:d@example.org"]
    result = checks(admin_client.get(HEALTH), "mail.example.org")
    assert result["spf"]["status"] == "ok" and result["dkim"]["status"] == "ok"
    assert result["dmarc"]["status"] == "warning" and "p=none" in result["dmarc"]["detail"]
    dns["_dmarc.mail.example.org"] = ["v=DMARC1; p=quarantine"]
    assert checks(admin_client.get(HEALTH), "mail.example.org")["dmarc"]["status"] == "ok"


def test_a_wide_open_spf_record_is_a_warning(admin_client, dns):
    dns["mail.example.org"] = ["v=spf1 +all"]
    assert checks(admin_client.get(HEALTH), "mail.example.org")["spf"]["status"] == "warning"


def test_a_failed_lookup_says_unknown_not_missing(admin_client, dns):
    dns["mail.example.org"] = None
    assert checks(admin_client.get(HEALTH), "mail.example.org")["spf"]["status"] == "unknown"


def test_the_two_streams_are_checked_and_reported_separately(admin_client, settings):
    body = admin_client.get(HEALTH).json()
    assert body["separate_streams"] is True
    assert [d["stream"] for d in body["domains"]] == ["transactional", "broadcast"]
    settings.EMAIL_FROM_MARKETING = "WO Community <news@mail.example.org>"
    assert admin_client.get(HEALTH).json()["separate_streams"] is False


def test_sending_results_are_counted_and_failures_listed(admin_client):
    delivery = WebhookDelivery.objects.create(provider="fake", event_id="e1", payload={})
    for kind in ("sent", "sent", "delivered", "bounced", "complained"):
        DeliveryEvent.objects.create(
            delivery=delivery,
            kind=kind,
            provider_message_id=f"m-{kind}-{DeliveryEvent.objects.count()}",
            email_hash="h",
        )
    body = admin_client.get(HEALTH).json()
    assert body["stats"]["sent"] == 2 and body["stats"]["delivered"] == 1
    assert body["stats"]["bounced"] == 1 and body["stats"]["complained"] == 1
    assert {f["kind"] for f in body["failures"]} == {"bounced", "complained"}


def test_the_suppression_list_is_searchable_by_the_full_address(admin_client):
    services.suppress("gone@example.com", "bounced")
    services.suppress("left@example.com", "unsubscribed")
    everyone = admin_client.get(SUPPRESSIONS).json()
    assert everyone["count"] == 2
    one = admin_client.get(SUPPRESSIONS, {"email": "Gone@Example.com"}).json()
    assert one["count"] == 1 and one["results"][0]["reason"] == "bounced"
    assert "gone@example.com" not in str(everyone)


def test_only_a_super_admin_can_remove_an_entry_and_it_is_audited(admin_client, boss_client):
    services.suppress("gone@example.com", "bounced")
    entry = Suppression.objects.get()
    assert admin_client.delete(f"{SUPPRESSIONS}/{entry.pk}").status_code == 403
    assert Suppression.objects.count() == 1
    assert boss_client.delete(f"{SUPPRESSIONS}/{entry.pk}").status_code == 204
    assert not Suppression.objects.exists()
    assert AuditLog.objects.filter(action="email.suppression_removed").count() == 1


def test_the_pages_need_a_signed_in_admin(api_client, make_user, client_for):
    assert api_client.get(HEALTH).status_code == 401
    assert client_for(make_user()).get(HEALTH).status_code == 403
    assert client_for(make_user()).get(SUPPRESSIONS).status_code == 403


# --- the warm up cap ---


def test_without_a_start_date_or_cap_there_is_no_limit(settings):
    settings.EMAIL_WARMUP_START = ""
    settings.EMAIL_HOURLY_CAP = -1
    assert warmup.hourly_cap(date(2026, 10, 13)) is None
    assert warmup.room(date(2026, 10, 13), 99999) is None


def test_the_schedule_raises_the_cap_day_by_day(settings):
    settings.EMAIL_HOURLY_CAP = -1
    settings.EMAIL_WARMUP_START = "2026-10-01"
    caps = [warmup.hourly_cap(date(2026, 10, d)) for d in (1, 2, 3, 5, 8, 12, 16, 23, 30)]
    assert caps == [50, 50, 100, 250, 500, 1000, 2500, 5000, 10000]
    assert warmup.hourly_cap(date(2026, 12, 1)) is None  # warm up is over
    assert warmup.room(date(2026, 10, 1), 30) == 20
    assert warmup.room(date(2026, 10, 1), 80) == 0


def test_a_fixed_cap_overrides_the_schedule(settings):
    settings.EMAIL_WARMUP_START = "2026-10-01"
    settings.EMAIL_HOURLY_CAP = 7
    assert warmup.hourly_cap(date(2026, 10, 30)) == 7
    settings.EMAIL_HOURLY_CAP = 0
    assert warmup.hourly_cap(date(2026, 10, 1)) is None
