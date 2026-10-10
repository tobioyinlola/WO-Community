from datetime import date, datetime

from django.db import connection

TABLE = "analytics_event"


def _month_start(value: date) -> date:
    return value.replace(day=1)


def _next_month(value: date) -> date:
    return date(value.year + (value.month // 12), value.month % 12 + 1, 1)


def partition_name(month: date) -> str:
    return f"{TABLE}_{month.year}_{month.month:02d}"


def ensure_month_partitions(start: date, months_ahead: int = 3) -> list[str]:
    """Create the partition for ``start``'s month and the following months."""
    created: list[str] = []
    month = _month_start(start)
    with connection.cursor() as cursor:
        for _ in range(months_ahead + 1):
            following = _next_month(month)
            name = partition_name(month)
            cursor.execute(
                f"CREATE TABLE IF NOT EXISTS {name} PARTITION OF {TABLE} "  # noqa: S608
                "FOR VALUES FROM (%s) TO (%s)",
                [f"{month.isoformat()} 00:00:00+00", f"{following.isoformat()} 00:00:00+00"],
            )
            created.append(name)
            month = following
    return created


def _months_back(value: date, months: int) -> date:
    index = value.year * 12 + (value.month - 1) - months
    return date(index // 12, index % 12 + 1, 1)


def drop_expired_partitions(now: datetime, keep_months: int) -> list[str]:
    """Drop whole monthly partitions older than the retention window.

    Dropping a partition is instant and leaves no dead rows, which is why the
    table is partitioned by month. The current month and ``keep_months`` before
    it are kept.
    """
    oldest_kept = _months_back(now.date(), keep_months)
    dropped: list[str] = []
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT c.relname FROM pg_inherits i "
            "JOIN pg_class c ON c.oid = i.inhrelid "
            "JOIN pg_class p ON p.oid = i.inhparent "
            "WHERE p.relname = %s",
            [TABLE],
        )
        for (name,) in cursor.fetchall():
            parts = name.removeprefix(f"{TABLE}_").split("_")
            if len(parts) != 2 or not all(part.isdigit() for part in parts):
                continue  # the default partition and anything unexpected
            if date(int(parts[0]), int(parts[1]), 1) < oldest_kept:
                cursor.execute(f"DROP TABLE {name}")  # noqa: S608
                dropped.append(name)
    return dropped
