import threading
import uuid
from datetime import timedelta

import pytest
from django.db import connections
from django.utils import timezone

from apps.analytics import services
from apps.analytics.models import AnalyticsEvent, ForwardCursor, IdentityLink
from apps.integrations.analytics import get_sink
from apps.integrations.analytics.sinks import FakeSink
from apps.integrations.tasks import forward

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _reset_sink():
    FakeSink.reset()


def record(count):
    for _ in range(count):
        services.track("email_verified", actor_id=uuid.uuid4())


def test_settings_select_the_fake_sink_in_tests():
    assert isinstance(get_sink(), FakeSink)


def test_events_are_forwarded_in_order_exactly_once():
    record(5)
    assert forward() == {"events": 5, "links": 0}
    expected = [str(i) for i in AnalyticsEvent.objects.order_by("seq").values_list("id", flat=True)]
    assert [e["id"] for e in FakeSink.events] == expected
    assert forward() == {"events": 0, "links": 0}
    assert len(FakeSink.events) == 5


def test_forwarded_events_carry_ids_and_categories_only():
    services.track(
        "invitation_sent", actor_id=uuid.uuid4(), properties={"role": "member", "bulk": False}
    )
    forward()
    [event] = FakeSink.events
    assert set(event) == {
        "id",
        "name",
        "actor_id",
        "anonymous_id",
        "properties",
        "source",
        "occurred_at",
    }
    assert event["properties"] == {"role": "member", "bulk": False}


def test_a_big_backlog_goes_out_in_batches(settings):
    settings.ANALYTICS_FORWARD_BATCH = 4
    record(10)
    assert forward()["events"] == 10
    assert FakeSink.batches == [4, 4, 2]


def test_an_unreachable_tool_leaves_the_cursor_so_the_same_events_are_offered_again():
    record(3)
    FakeSink.fail = True
    with pytest.raises(ConnectionError):
        forward()
    assert not ForwardCursor.objects.filter(last_seq__gt=0).exists()
    assert FakeSink.events == []
    FakeSink.fail = False
    assert forward()["events"] == 3


def test_recent_events_are_held_back_until_earlier_transactions_would_have_finished(settings):
    settings.ANALYTICS_FORWARD_DELAY_SECONDS = 60
    record(2)
    assert forward()["events"] == 0
    AnalyticsEvent.objects.update(received_at=timezone.now() - timedelta(seconds=61))
    assert forward()["events"] == 2


def test_identity_links_are_forwarded_once(make_user):
    member, anon = make_user(email="a@example.com"), uuid.uuid4()
    services.identify(anon, member.pk)
    assert forward()["links"] == 1
    assert FakeSink.links == [{"anonymous_id": str(anon), "user_id": str(member.pk)}]
    assert IdentityLink.objects.get().forwarded_at is not None
    assert forward()["links"] == 0


def test_a_failed_link_send_is_retried(make_user):
    member = make_user(email="a@example.com")
    services.identify(uuid.uuid4(), member.pk)
    FakeSink.fail = True
    with pytest.raises(ConnectionError):
        forward()
    assert IdentityLink.objects.get().forwarded_at is None
    FakeSink.fail = False
    assert forward()["links"] == 1


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
@pytest.mark.usefixtures("truncate_audit")
def test_a_second_forwarder_does_not_send_what_the_first_is_sending():
    record(2)
    # Committed first, so the second forwarder can see the row the first one will lock.
    ForwardCursor.objects.get_or_create(name=services.FORWARD_EVENTS)
    outcomes = []

    def while_first_is_sending(batch):
        def second_forwarder():
            try:
                outcomes.append(services.forward_events(lambda events: outcomes.append("sent")))
            finally:
                connections.close_all()

        worker = threading.Thread(target=second_forwarder)
        worker.start()
        worker.join()

    assert services.forward_events(while_first_is_sending) == 2
    assert outcomes == [0]  # the second one found the cursor locked and did nothing
