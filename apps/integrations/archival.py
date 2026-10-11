"""Copying a month of analytics events to Parquet files before the partition is dropped.

Events are only kept in the database for the retention window. Before a partition ages out it is
written to object storage as a Parquet file, a columnar format that data tools read directly
(BigQuery, Athena, DuckDB, pandas). The file is verified against the row count before the copy is
recorded, and the partition is dropped only once it is recorded.
"""

import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]
import structlog
from django.conf import settings
from django.db import connection
from django.utils import timezone

from apps.analytics import partitions
from apps.analytics.models import PartitionArchive
from apps.integrations.storage import PRIVATE, get_storage

logger = structlog.get_logger(__name__)

BATCH = 50_000
SCHEMA = pa.schema(
    [
        ("id", pa.string()),
        ("seq", pa.int64()),
        ("name", pa.string()),
        ("actor_id", pa.string()),
        ("anonymous_id", pa.string()),
        ("properties", pa.string()),  # JSON text, so the schema never changes with the registry
        ("source", pa.string()),
        ("occurred_at", pa.timestamp("us", tz="UTC")),
        ("received_at", pa.timestamp("us", tz="UTC")),
    ]
)


def key_for(partition: str) -> str:
    return f"archive/analytics/{partition}.parquet"


def _batches(partition: str) -> Any:
    """Rows of one partition in order, through a server side cursor so memory stays flat."""
    with connection.cursor() as cursor:
        # The name comes from the catalogue (expired_partitions), never from a request.
        table = connection.ops.quote_name(partition)
        cursor.execute(
            "SELECT id, seq, name, actor_id, anonymous_id, properties, source, occurred_at, "  # noqa: S608  # nosec B608
            f"received_at FROM {table} ORDER BY seq"
        )
        while True:
            rows = cursor.fetchmany(BATCH)
            if not rows:
                return
            yield rows


def archive_partition(partition: str) -> PartitionArchive:
    """Write one partition to Parquet and record it. Safe to repeat: an archive is made once."""
    existing = PartitionArchive.objects.filter(partition=partition).first()
    if existing is not None:
        return existing
    total = 0
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "part.parquet"
        with pq.ParquetWriter(path, SCHEMA, compression="zstd") as writer:
            for rows in _batches(partition):
                columns: list[list[Any]] = [[] for _ in SCHEMA]
                for row in rows:
                    event_id, seq, name, actor, anon, props, source, occurred, received = row
                    for column, value in zip(
                        columns,
                        (
                            str(event_id),
                            seq,
                            name,
                            str(actor) if actor else None,
                            str(anon) if anon else None,
                            # Django hands jsonb over as text; keep it as the JSON it already is.
                            props if isinstance(props, str) else json.dumps(props, sort_keys=True),
                            source,
                            occurred,
                            received,
                        ),
                        strict=True,
                    ):
                        column.append(value)
                writer.write_table(pa.Table.from_arrays(columns, schema=SCHEMA))
                total += len(rows)
        data = path.read_bytes()
        # Prove the file holds every row before anything may be dropped.
        written = pq.ParquetFile(path).metadata.num_rows
    if written != total:
        raise RuntimeError(f"archive of {partition} holds {written} rows, expected {total}")
    key = key_for(partition)
    get_storage().write(
        bucket=PRIVATE, key=key, data=data, content_type="application/vnd.apache.parquet"
    )
    record, _ = PartitionArchive.objects.get_or_create(
        partition=partition,
        defaults={
            "object_key": key,
            "rows": total,
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        },
    )
    logger.info("analytics_partition_archived", partition=partition, rows=total, size=len(data))
    return record


def archive_expired() -> list[str]:
    """Archive every partition that is past retention and not archived yet."""
    done: list[str] = []
    for name in partitions.expired_partitions(timezone.now(), settings.ANALYTICS_RETENTION_MONTHS):
        if not PartitionArchive.objects.filter(partition=name).exists():
            archive_partition(name)
            done.append(name)
    return done
