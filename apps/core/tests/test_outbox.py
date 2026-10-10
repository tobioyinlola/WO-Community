from dataclasses import dataclass
from typing import ClassVar
from unittest import mock

import pytest
from django.db import transaction

from apps.core import events, outbox
from apps.core.models import FailedTask, OutboxEvent

pytestmark = pytest.mark.django_db


@dataclass(frozen=True)
class SomethingHappened(events.DomainEvent):
    topic: ClassVar[str] = "test.something_happened"
    thing_id: str


@pytest.fixture(autouse=True)
def _isolated_handlers():
    saved = {k: list(v) for k, v in outbox._handlers.items()}
    outbox._handlers.clear()
    yield
    outbox._handlers.clear()
    outbox._handlers.update(saved)


def test_event_is_recorded_with_its_payload():
    events.publish(SomethingHappened(thing_id="42"))
    stored = OutboxEvent.objects.get()
    assert stored.topic == "test.something_happened"
    assert stored.payload == {"thing_id": "42"}
    assert stored.status == "pending"


def test_rolled_back_transaction_leaves_no_event():
    with pytest.raises(RuntimeError), transaction.atomic():
        events.publish(SomethingHappened(thing_id="1"))
        raise RuntimeError("business rule failed")
    assert OutboxEvent.objects.count() == 0


def test_dispatch_sends_one_task_per_handler_and_marks_published():
    outbox.register_handler("test.something_happened", "demo.first", "critical")
    outbox.register_handler("test.something_happened", "demo.second")
    events.publish(SomethingHappened(thing_id="7"))
    with mock.patch("apps.core.outbox.current_app.send_task") as send_task:
        assert outbox.dispatch_pending() == 1
    event = OutboxEvent.objects.get()
    names = [call.args[0] for call in send_task.call_args_list]
    assert names == ["demo.first", "demo.second"]
    assert send_task.call_args_list[0].kwargs == {"args": [str(event.id)], "queue": "critical"}
    assert event.status == "published"
    assert event.published_at is not None


def test_dispatch_is_not_repeated_for_published_events():
    events.publish(SomethingHappened(thing_id="7"))
    assert outbox.dispatch_pending() == 1
    assert outbox.dispatch_pending() == 0


def test_event_without_handlers_is_still_marked_published():
    events.publish(SomethingHappened(thing_id="7"))
    outbox.dispatch_pending()
    assert OutboxEvent.objects.get().status == "published"


def test_failed_dispatch_is_retried_later_with_backoff():
    outbox.register_handler("test.something_happened", "demo.first")
    events.publish(SomethingHappened(thing_id="7"))
    with mock.patch("apps.core.outbox.current_app.send_task", side_effect=OSError("broker")):
        assert outbox.dispatch_pending() == 0
    event = OutboxEvent.objects.get()
    assert event.status == "pending"
    assert event.attempts == 1
    assert "broker" in event.last_error
    assert outbox.dispatch_pending() == 0  # not due yet


def test_event_fails_permanently_after_max_attempts(settings):
    settings.OUTBOX_MAX_ATTEMPTS = 1
    outbox.register_handler("test.something_happened", "demo.first")
    events.publish(SomethingHappened(thing_id="7"))
    with mock.patch("apps.core.outbox.current_app.send_task", side_effect=OSError("broker")):
        outbox.dispatch_pending()
    assert OutboxEvent.objects.get().status == "failed"


def test_future_events_wait_for_their_time():
    from datetime import timedelta

    from django.utils import timezone

    OutboxEvent.objects.create(
        topic="x", payload={}, available_at=timezone.now() + timedelta(hours=1)
    )
    assert outbox.dispatch_pending() == 0


def test_dead_letter_is_recorded_when_a_task_gives_up():
    from apps.core.tasks import dispatch_outbox

    dispatch_outbox.on_failure(ValueError("boom"), "task-1", ("a",), {"k": 1}, None)
    failed = FailedTask.objects.get()
    assert failed.task_name == "core.dispatch_outbox"
    assert failed.args == ["a"]
    assert failed.kwargs == {"k": 1}
    assert failed.replayed_at is None
