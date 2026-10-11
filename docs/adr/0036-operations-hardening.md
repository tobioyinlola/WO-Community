# 0036. Operations hardening

Status: accepted (hardening pass after Stage 3)

This closes the operational items the earlier stages carried forward. Each is small; they are
recorded together because they share one idea: the platform should be able to prove what happened,
keep what it must, and tell operators when it is unwell.

## The audit trail is anchored outside the database

The audit log is a hash chain per day (ADR 0002). That detects a changed row but not a whole day
rewritten consistently by someone with database access. A daily job
(`audit.anchor_previous_day`, `apps/integrations/anchoring.py`) verifies yesterday's chain and,
only if it is intact, writes the day's head (hash, row count, last sequence number) to a bucket
with S3 Object Lock in COMPLIANCE mode (`STORAGE_ANCHOR_BUCKET`, retention
`AUDIT_ANCHOR_RETENTION_DAYS`, 7 years). Nobody, including us, can replace or delete it during that
time, so a later mismatch is proof of tampering. The same job re-checks the last 7 anchors and logs
`audit_anchor_problem` at error level on any mismatch or a broken chain. A broken chain is never
anchored: that would lock wrong evidence in.

## Analytics are archived before they are dropped

Events live in monthly partitions that are dropped after 13 months. Before that,
`analytics.archive_expired` writes each expired partition to a Parquet file (zstd, a fixed schema
with properties kept as JSON text so the schema never changes with the event registry) under
`archive/analytics/` in the private bucket and records it (`PartitionArchive`: rows, size,
SHA-256). The file's row count is checked against the partition's before the record is written.
With `ANALYTICS_REQUIRE_ARCHIVE` on (production forces it), `analytics.drop_expired` drops only
partitions that have a record, so a failed archive can never lose data.

## Rejected registrations are erased after 90 days

`accounts.purge_rejected` deletes accounts rejected more than 90 days ago, with everything hanging
off them. The audit trail keeps only the user id (which holds no personal data), recorded as
`members.purged`. Suspended and removed members are not touched: they were members.

## Operators can see the system

- **Metrics.** `GET /metrics` serves Prometheus text, but only with `METRICS_TOKEN` as a bearer
  token (404 when unset). It exposes request counts and latency by route pattern (bounded
  cardinality), and gauges read at scrape time: waiting outbox events, the age of the oldest, failed
  outbox events and failed tasks. Set `PROMETHEUS_MULTIPROC_DIR` under gunicorn so all workers count.
- **Tracing.** OpenTelemetry for requests, database calls, Celery tasks and outbound HTTP, off until
  `OTEL_EXPORTER_OTLP_ENDPOINT` is set, sampled by `OTEL_TRACE_SAMPLE_RATIO` (default 10%).
  Query strings are redacted from spans because email links carry tokens in them. Nothing is
  imported or patched when it is off.

## The pipeline guards what the code cannot

`.github/workflows/ci.yml` runs lint, types, security audit, module boundaries, migration safety,
tests, API description drift and the deployment check; then builds the container image, starts it,
and scans it for high and critical vulnerabilities; and scans history for secrets.

- **Migration safety** uses `django-migration-linter` on migrations *new compared with the base
  branch* (old ones have run). Its first run found two real rollout hazards in our own work: adding
  a NOT NULL column without a database default breaks the previous release while it is still
  inserting rows during a rolling deploy. Both columns now carry `db_default`. One finding is
  waived on purpose: widening a varchar (`uploads.0006`) is metadata only in PostgreSQL.
- **Deployment check** is `scripts/deploy_check.py`, which fills the required environment with
  placeholders and runs Django's `check --deploy` against the production settings, so a misconfigured
  setting fails a build instead of a deploy.

## What stays outside this repository

Infrastructure as code for a specific cloud, DNS records and the email domain warm-up depend on
provider and account decisions that have not been made. `docs/deployment.md` records exactly what
the application needs from them (processes, buckets and their policies, network egress for the
media worker, the sending-domain checklist), so that work can be done without reading the code.
The CDN purger is waiting on the provider decision as before.
