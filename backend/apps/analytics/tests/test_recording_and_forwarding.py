import logging
import uuid
from datetime import timedelta

import pytest
from django.db import connection, transaction
from django.utils import timezone

from apps.analytics import partitions, services
from apps.analytics.models import AnalyticsEvent, IdentityLink

pytestmark = pytest.mark.django_db


def user_id():
    return uuid.uuid4()


# --- recording ---


def test_an_event_is_stored_with_everything_it_needs():
    actor, anon = user_id(), uuid.uuid4()
    assert services.track(
        "startup_page_viewed",
        actor_id=actor,
        anonymous_id=anon,
        properties={"startup_slug": "acme-pay"},
        source="client",
    )
    event = AnalyticsEvent.objects.get()
    assert (event.name, event.actor_id, event.anonymous_id) == ("startup_page_viewed", actor, anon)
    assert event.properties == {"startup_slug": "acme-pay"}
    assert event.source == "client"
    assert event.occurred_at <= event.received_at


def test_sequence_numbers_increase_in_the_order_events_are_recorded():
    for _ in range(3):
        services.track("email_verified", actor_id=user_id())
    assert list(AnalyticsEvent.objects.order_by("seq").values_list("seq", flat=True)) == sorted(
        AnalyticsEvent.objects.values_list("seq", flat=True)
    )
    assert len(set(AnalyticsEvent.objects.values_list("seq", flat=True))) == 3


def test_the_clients_clock_is_not_trusted():
    now = timezone.now()
    services.track(
        "join_cta_clicked",
        properties={"location": "home"},
        source="client",
        occurred_at=now + timedelta(hours=5),
    )
    services.track(
        "join_cta_clicked",
        properties={"location": "home"},
        source="client",
        occurred_at=now - timedelta(days=3),
    )
    recent = now - timedelta(hours=2)
    services.track(
        "join_cta_clicked", properties={"location": "home"}, source="client", occurred_at=recent
    )
    times = sorted(AnalyticsEvent.objects.values_list("occurred_at", flat=True))
    assert all(t <= timezone.now() for t in times)
    assert times[0] == recent  # only the believable timestamp was kept
    assert all(t > now - timedelta(hours=3) for t in times)


def test_a_wrong_event_raises_in_strict_mode():
    with pytest.raises(Exception, match="unknown event"):
        services.track("made_up_event")


def test_in_production_a_wrong_event_is_dropped_and_logged_not_raised(settings, caplog):
    settings.ANALYTICS_STRICT = False
    with caplog.at_level(logging.WARNING):
        assert services.track("made_up_event") is False
    assert "analytics_event_dropped" in caplog.text
    assert AnalyticsEvent.objects.count() == 0


def test_a_database_failure_while_recording_never_breaks_the_callers_transaction(
    settings, monkeypatch
):
    settings.ANALYTICS_STRICT = False

    def broken(*args, **kwargs):
        raise RuntimeError("disk full")

    with transaction.atomic():
        monkeypatch.setattr(AnalyticsEvent.objects, "create", broken)
        assert services.track("email_verified", actor_id=user_id()) is False
        # the surrounding transaction is still healthy and can keep working
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            assert cursor.fetchone() == (1,)


def test_an_event_is_not_kept_when_the_surrounding_change_rolls_back():
    with pytest.raises(RuntimeError), transaction.atomic():
        services.track("email_verified", actor_id=user_id())
        raise RuntimeError("business rule failed")
    assert AnalyticsEvent.objects.count() == 0


# --- opting out ---


def test_nothing_is_recorded_for_a_member_who_opted_out(make_user):
    member, other = make_user(email="a@example.com"), make_user(email="b@example.com")
    services.set_opt_out(member.pk, True)
    assert services.track("email_verified", actor_id=member.pk) is False
    assert services.track("email_verified", actor_id=other.pk) is True
    assert list(AnalyticsEvent.objects.values_list("actor_id", flat=True)) == [other.pk]


def test_rejoining_takes_effect_at_once(make_user):
    member = make_user(email="a@example.com")
    services.set_opt_out(member.pk, True)
    assert services.is_opted_out(member.pk)
    services.set_opt_out(member.pk, False)
    assert not services.is_opted_out(member.pk)
    assert services.track("email_verified", actor_id=member.pk)


def test_anonymous_events_are_not_affected_by_anyones_choice(make_user):
    services.set_opt_out(make_user(email="a@example.com").pk, True)
    assert services.track("directory_viewed", anonymous_id=uuid.uuid4(), source="client")


# --- linking a visitor to a member ---


def test_a_visitor_is_linked_to_the_member_they_become(make_user):
    member, anon = make_user(email="a@example.com"), uuid.uuid4()
    assert services.identify(anon, member.pk) is True
    link = IdentityLink.objects.get()
    assert (link.anonymous_id, link.user_id, link.forwarded_at) == (anon, member.pk, None)


def test_the_first_link_wins_so_a_shared_browser_is_not_misattributed(make_user):
    first, second = make_user(email="a@example.com"), make_user(email="b@example.com")
    anon = uuid.uuid4()
    services.identify(anon, first.pk)
    assert services.identify(anon, second.pk) is False
    assert IdentityLink.objects.get().user_id == first.pk


def test_an_opted_out_member_is_never_linked(make_user):
    member = make_user(email="a@example.com")
    services.set_opt_out(member.pk, True)
    assert services.identify(uuid.uuid4(), member.pk) is False
    assert IdentityLink.objects.count() == 0


# --- storage housekeeping ---


def test_creating_partitions_is_repeatable():
    today = timezone.now().date()
    assert partitions.ensure_month_partitions(today) == partitions.ensure_month_partitions(today)


def partition_exists(name):
    with connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass(%s)", [name])
        return cursor.fetchone()[0] is not None


def test_partitions_older_than_the_retention_window_are_dropped_and_recent_ones_kept():
    now = timezone.now()
    old = now - timedelta(days=30 * 20)
    recent = now - timedelta(days=30 * 6)
    partitions.ensure_month_partitions(old.date(), months_ahead=0)
    partitions.ensure_month_partitions(recent.date(), months_ahead=0)
    old_name = partitions.partition_name(old.date().replace(day=1))
    recent_name = partitions.partition_name(recent.date().replace(day=1))

    dropped = partitions.drop_expired_partitions(now, keep_months=13)

    assert old_name in dropped
    assert not partition_exists(old_name)
    assert partition_exists(recent_name) and recent_name not in dropped
    assert partition_exists("analytics_event_default")  # the safety partition is never dropped


def test_an_event_outside_every_prepared_month_still_lands_somewhere():
    far = timezone.now() - timedelta(hours=1)
    AnalyticsEvent.objects.create(
        seq=999_999,
        name="email_verified",
        properties={},
        source="server",
        occurred_at=far,
        received_at=far,
    )
    assert AnalyticsEvent.objects.filter(seq=999_999).exists()
