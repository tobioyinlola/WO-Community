# Runbook: core platform alerts

## Outbox backlog (events pending longer than 2 minutes)

Meaning: events are written but not reaching Celery.

1. Check the `critical` queue and that a worker is consuming it (`celery -A config inspect active`).
2. Check beat is running; `core.dispatch_outbox` runs every 5 seconds.
3. Look at `OutboxEvent` rows with `status = 'pending'` and a high `attempts` or a `last_error`.
4. Rows with `status = 'failed'` exhausted retries. Fix the cause, then set `status = 'pending'`,
   `attempts = 0` to replay.

## Dead letters (`FailedTask` rows with `replayed_at` empty)

Any row from the `critical` queue pages. Inspect `exception`, fix the cause, replay the task with
the stored `args` and `kwargs`, then set `replayed_at`. Tasks are idempotent, so a replay is safe.

## Audit chain broken (`audit_chain_broken` log line, security alert)

Treat as a security incident. The log line names the day and the first row that does not match.
Preserve the database state, compare against the latest backup and the anchored head hash, and
follow the security incident process.

## Audit rows in the default partition

`audit.ensure_partitions` did not run. Run it, then move the rows into the correct monthly
partition during a maintenance window.

## Readiness failing

`/health/ready` returns 503 when PostgreSQL or Redis cannot be reached. Instances are removed from
rotation automatically. Check the database and Redis first, then connection pool saturation.
