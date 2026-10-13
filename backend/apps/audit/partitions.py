from datetime import date

from django.db import connection


def _month_start(value: date) -> date:
    return value.replace(day=1)


def _next_month(value: date) -> date:
    return date(value.year + (value.month // 12), value.month % 12 + 1, 1)


def partition_name(month: date) -> str:
    return f"audit_auditlog_{month.year}_{month.month:02d}"


def ensure_month_partitions(start: date, months_ahead: int = 3) -> list[str]:
    """Create the partition for ``start``'s month and the following months."""
    created: list[str] = []
    month = _month_start(start)
    with connection.cursor() as cursor:
        for _ in range(months_ahead + 1):
            following = _next_month(month)
            name = partition_name(month)
            cursor.execute(
                f"CREATE TABLE IF NOT EXISTS {name} PARTITION OF audit_auditlog "  # noqa: S608
                "FOR VALUES FROM (%s) TO (%s)",
                [f"{month.isoformat()} 00:00:00+00", f"{following.isoformat()} 00:00:00+00"],
            )
            created.append(name)
            month = following
    return created
