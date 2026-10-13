import threading
from datetime import timedelta

import pytest
from django.db import ProgrammingError, connection, connections, transaction
from django.db.utils import InternalError, OperationalError
from django.utils import timezone

from apps.audit import partitions, services
from apps.audit.models import AuditLog

pytestmark = pytest.mark.django_db


def test_entries_are_chained_within_a_day(make_user):
    actor = make_user(roles=("community_admin",))
    first = services.record(actor=actor, action="member.approve", target_type="user", target_id=1)
    second = services.record(actor=actor, action="member.suspend", reason="spam")
    assert first.prev_hash == ""
    assert second.prev_hash == first.hash
    assert second.seq > first.seq
    assert second.actor_roles == ["community_admin"]
    assert services.verify_day(timezone.now().date())


def test_raw_ip_and_user_agent_are_never_stored(make_user):
    entry = services.record(
        actor=make_user(), action="login", ip="203.0.113.9", user_agent="Mozilla/5.0"
    )
    stored = AuditLog.objects.get(pk=entry.pk)
    assert stored.ip_hash == services.hash_value("203.0.113.9")
    assert "203.0.113.9" not in (stored.ip_hash + stored.user_agent_hash)
    assert len(stored.ip_hash) == 64


def test_system_actions_can_be_recorded_without_actor():
    entry = services.record(actor=None, action="retention.purge")
    assert entry.actor_id is None


def test_update_is_rejected_by_the_database(make_user):
    entry = services.record(actor=make_user(), action="member.approve")
    with pytest.raises((InternalError, ProgrammingError, OperationalError)), transaction.atomic():
        AuditLog.objects.filter(pk=entry.pk).update(action="member.nothing")


def test_delete_is_rejected_by_the_database(make_user):
    entry = services.record(actor=make_user(), action="member.approve")
    with pytest.raises((InternalError, ProgrammingError, OperationalError)), transaction.atomic():
        AuditLog.objects.filter(pk=entry.pk).delete()


def test_tampering_is_detected_by_verification(make_user):
    actor = make_user()
    services.record(actor=actor, action="a")
    victim = services.record(actor=actor, action="b")
    services.record(actor=actor, action="c")
    with connection.cursor() as cursor:
        cursor.execute("ALTER TABLE audit_auditlog DISABLE TRIGGER audit_auditlog_no_change")
        cursor.execute("UPDATE audit_auditlog SET action = 'forged' WHERE id = %s", [victim.pk])
        cursor.execute("ALTER TABLE audit_auditlog ENABLE TRIGGER audit_auditlog_no_change")
    assert services.verify_day(timezone.now().date()) is False


def test_removed_entry_is_detected_by_verification(make_user):
    actor = make_user()
    services.record(actor=actor, action="a")
    middle = services.record(actor=actor, action="b")
    services.record(actor=actor, action="c")
    with connection.cursor() as cursor:
        cursor.execute("ALTER TABLE audit_auditlog DISABLE TRIGGER audit_auditlog_no_change")
        cursor.execute("DELETE FROM audit_auditlog WHERE id = %s", [middle.pk])
        cursor.execute("ALTER TABLE audit_auditlog ENABLE TRIGGER audit_auditlog_no_change")
    assert services.verify_day(timezone.now().date()) is False


def test_future_months_get_partitions():
    future = (timezone.now() + timedelta(days=200)).date()
    created = partitions.ensure_month_partitions(future, months_ahead=1)
    assert partitions.partition_name(future.replace(day=1)) in created
    with connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass(%s)", [created[0]])
        assert cursor.fetchone()[0] is not None


def test_partition_creation_is_repeatable():
    today = timezone.now().date()
    assert partitions.ensure_month_partitions(today) == partitions.ensure_month_partitions(today)


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
@pytest.mark.usefixtures("truncate_audit")
def test_concurrent_writers_still_produce_a_valid_chain(make_user):
    actor = make_user()
    errors: list[Exception] = []

    def write(n: int) -> None:
        try:
            services.record(actor=actor, action=f"concurrent.{n}")
        except Exception as exc:  # pragma: no cover - surfaced by the assertion below
            errors.append(exc)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=write, args=(n,)) for n in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert not errors
    assert AuditLog.objects.count() == 8
    assert services.verify_day(timezone.now().date())
