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

## An admin lost their authenticator

A super admin calls `POST /admin/members/{id}/reset-mfa` (needs a fresh MFA check). The admin logs
in with their password, is told `mfa_enrolment_required`, and enrols again. If the person who lost
their device is the only super admin, an operator deletes their `accounts_mfadevice` row and
recovery codes in the database, records why in the incident log, and the admin enrols at next login.

## Spike in `mfa.failed` audit entries or 429 on `/auth/mfa/*`

Someone is guessing codes for an account whose password they already know. Check the audit log for
the account, suspend it if the pattern looks hostile, and tell its owner to change their password.

## Uploads stuck in `processing`, or `FailedTask` rows for `uploads.process_upload`

The scanner is probably unreachable. Check `clamd` (host and port in `CLAMD_HOST`/`CLAMD_PORT`) from a
media worker. Uploads wait and retry on their own and are never published unscanned; once the scanner
is back they finish. Anything still processing after two hours is rejected by the hourly cleanup
(`processing_timeout`) and the member can upload again. Replay dead-lettered tasks as usual.

## `upload.malware_detected` in the audit log

A member uploaded a file the scanner flagged. The file was rejected and deleted; nothing was
published. One detection is usually a compromised device or a test string. Several for one member,
or for one signature across members, deserve a look: suspend the account if it looks deliberate.

## Quarantine bucket growing

The hourly `uploads.cleanup` job deletes abandoned uploads. If the bucket grows, check that beat is
running and that the bucket has the lifecycle rule (delete after one day) as a backstop.
