import json
from datetime import datetime, timedelta

import pyarrow.parquet as pq
import pytest
from django.db import connection
from django.utils import timezone

from apps.accounts.models import User, UserStatus
from apps.analytics import partitions
from apps.analytics.models import PartitionArchive
from apps.audit import services as audit
from apps.audit.models import AuditLog
from apps.integrations import anchoring, archival
from apps.integrations.storage import ANCHOR, PRIVATE
from apps.integrations.storage.fake import FakeStorage

pytestmark = pytest.mark.django_db


# --- audit anchoring ---


@pytest.fixture
def audited_day(db):
    """Two audit entries dated yesterday, chained like real ones."""
    yesterday = timezone.now() - timedelta(days=1)
    from unittest import mock

    with mock.patch("apps.audit.services.timezone.now", return_value=yesterday):
        audit.record(actor=None, action="test.one", target_type="x", target_id="1")
        audit.record(actor=None, action="test.two", target_type="x", target_id="2")
    return yesterday.date()


def test_the_head_of_a_day_commits_to_every_row(audited_day):
    head = audit.head_of(audited_day)
    assert head["count"] == 2 and head["day"] == audited_day.isoformat()
    last = (
        AuditLog.objects.filter(action="test.two", created_at__date=audited_day)
        .order_by("-seq")
        .first()
    )
    assert head["head_hash"] == last.hash and head["last_seq"] == last.seq
    assert audit.head_of(audited_day - timedelta(days=30)) is None


def test_a_day_is_anchored_once_in_write_once_storage(audited_day):
    assert anchoring.anchor_day(audited_day) == "stored"
    key = anchoring.key_for(audited_day)
    assert (ANCHOR, key) in FakeStorage.objects and (ANCHOR, key) in FakeStorage.locked
    assert json.loads(FakeStorage.objects[(ANCHOR, key)][0])["count"] == 2
    assert anchoring.anchor_day(audited_day) == "exists"  # the same head: nothing to do
    with pytest.raises(PermissionError):  # not even we can delete or replace it
        FakeStorage().delete(bucket=ANCHOR, key=key)
    with pytest.raises(PermissionError):
        FakeStorage().write(bucket=ANCHOR, key=key, data=b"{}", content_type="application/json")


def test_a_rewritten_day_no_longer_matches_its_anchor(audited_day):
    anchoring.anchor_day(audited_day)
    assert anchoring.verify_anchor(audited_day) is True
    # Someone with database access appends a row to the closed day.
    with connection.cursor() as cursor:
        cursor.execute("ALTER TABLE audit_auditlog DISABLE TRIGGER USER")
        try:
            row = (
                AuditLog.objects.filter(action="test.two", created_at__date=audited_day)
                .order_by("-seq")
                .first()
            )
            cursor.execute(
                "UPDATE audit_auditlog SET action = 'tampered' WHERE id = %s", [str(row.pk)]
            )
            cursor.execute(
                "UPDATE audit_auditlog SET hash = 'f' || substr(hash, 2) WHERE id = %s",
                [str(row.pk)],
            )
        finally:
            cursor.execute("ALTER TABLE audit_auditlog ENABLE TRIGGER USER")
    assert anchoring.verify_anchor(audited_day) is False
    assert anchoring.anchor_day(audited_day) == "mismatch"


def test_the_daily_job_anchors_yesterday_and_rechecks_recent_days(audited_day):
    result = anchoring.anchor_previous_day()
    assert result["outcome"] == "stored" and result["mismatched"] == []
    again = anchoring.anchor_previous_day()
    assert again["outcome"] == "exists"


def test_a_broken_chain_is_never_anchored(audited_day):
    with connection.cursor() as cursor:
        cursor.execute("ALTER TABLE audit_auditlog DISABLE TRIGGER USER")
        try:
            cursor.execute(
                "UPDATE audit_auditlog SET action = 'tampered' WHERE action = 'test.one'"
            )
        finally:
            cursor.execute("ALTER TABLE audit_auditlog ENABLE TRIGGER USER")
    assert anchoring.anchor_previous_day()["outcome"] == "chain_broken"
    assert (ANCHOR, anchoring.key_for(audited_day)) not in FakeStorage.objects


# --- analytics archive ---


def make_old_partition(month: datetime, rows: int = 3) -> str:
    name = partitions.partition_name(month.date())
    partitions.ensure_month_partitions(month.date(), months_ahead=0)
    with connection.cursor() as cursor:
        for i in range(rows):
            cursor.execute(
                f"INSERT INTO {name} (id, seq, name, actor_id, anonymous_id, properties, "  # noqa: S608
                "source, occurred_at, received_at) VALUES (gen_random_uuid(), "
                "nextval('analytics_event_seq'), %s, NULL, gen_random_uuid(), %s::jsonb, "
                "'server', %s, %s)",
                [f"event_{i}", json.dumps({"n": i}), month, month],
            )
    return name


def test_an_expired_partition_is_written_to_parquet_and_recorded():
    old = timezone.now().replace(day=15) - timedelta(days=30 * 20)
    name = make_old_partition(old, rows=3)
    done = archival.archive_expired()
    assert name in done
    record = PartitionArchive.objects.get(partition=name)
    assert record.rows == 3 and len(record.sha256) == 64
    data, content_type = FakeStorage.objects[(PRIVATE, record.object_key)]
    assert content_type == "application/vnd.apache.parquet"
    import io

    table = pq.read_table(io.BytesIO(data))
    assert table.num_rows == 3
    assert sorted(table.column("name").to_pylist()) == ["event_0", "event_1", "event_2"]
    assert json.loads(table.column("properties").to_pylist()[0]) in ({"n": 0}, {"n": 1}, {"n": 2})
    assert archival.archive_expired() == []  # an archive is made once


def test_a_partition_is_dropped_only_after_it_was_archived(settings):
    from apps.analytics import tasks

    settings.ANALYTICS_REQUIRE_ARCHIVE = True
    old = timezone.now().replace(day=15) - timedelta(days=30 * 20)
    name = make_old_partition(old)
    assert name not in tasks.drop_expired()  # no copy yet: kept
    archival.archive_expired()
    assert name in tasks.drop_expired()
    settings.ANALYTICS_REQUIRE_ARCHIVE = False
    again = make_old_partition(old - timedelta(days=60))
    assert again in tasks.drop_expired()  # the old behaviour is still available


# --- rejected registrations ---


def test_rejected_registrations_are_erased_after_the_retention_period(make_user, settings):
    from apps.accounts import membership

    old = make_user(email="old@example.com", status=UserStatus.REJECTED)
    recent = make_user(email="recent@example.com", status=UserStatus.REJECTED)
    suspended = make_user(email="susp@example.com", status=UserStatus.SUSPENDED)
    long_ago = timezone.now() - timedelta(days=settings.REJECTED_REGISTRATION_RETENTION_DAYS + 1)
    User.objects.filter(pk__in=[old.pk, suspended.pk]).update(status_changed_at=long_ago)
    User.objects.filter(pk=recent.pk).update(status_changed_at=timezone.now() - timedelta(days=5))
    User.objects.filter(pk=old.pk).update(status=UserStatus.REJECTED)
    assert membership.purge_rejected_registrations() == 1
    assert not User.objects.filter(pk=old.pk).exists()
    assert User.objects.filter(pk__in=[recent.pk, suspended.pk]).count() == 2
    assert membership.purge_rejected_registrations() == 0
    assert AuditLog.objects.filter(action="members.purged", target_id=str(old.pk)).exists()
