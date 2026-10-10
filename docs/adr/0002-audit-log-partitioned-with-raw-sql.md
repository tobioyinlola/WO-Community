# 0002. Audit log is a raw SQL partitioned table

Status: accepted (Stage 0)

## Context

The audit log must be append only, partitioned by month from the first migration, and carry a hash
chain per day. Django cannot declare range partitioned tables.

## Decision

- The table is created by the initial migration with `RunSQL`, partitioned by `created_at`, with a
  default partition as a last resort. The model is `managed = False`.
- A trigger rejects `UPDATE` and `DELETE` for every role. Production additionally revokes those
  grants from the application role.
- Actor and target are stored as plain ids, not foreign keys, so erasing a user never touches the
  audit trail.
- Entries are chained per UTC day. `record()` takes a transaction level advisory lock for the day
  so concurrent writers keep one linear chain; `seq` comes from a dedicated sequence.
- A daily task creates partitions three months ahead. Rows should never reach the default
  partition; the runbook alerts if any do.

## Consequences

Retention is done by detaching old partitions, which a row level trigger does not block. Anchoring
the daily head hash in write-once object storage needs the storage adapter and is deferred.
