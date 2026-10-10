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

## Setting up Resend

1. Add two sending domains in the Resend dashboard, for example `mail.yourdomain` (transactional)
   and `news.yourdomain` (marketing). Publish the SPF and DKIM records Resend shows, and a DMARC
   record (start with `p=none` and a reporting address, tighten to `quarantine` once reports are
   clean). Wait until both show as verified.
2. Create an API key with *sending access* limited to those domains. Put it in `RESEND_API_KEY`
   through the secrets manager, never in the repository.
3. Add a webhook pointing at `https://<api host>/api/v1/webhooks/email/resend` subscribed to
   `email.sent`, `email.delivered`, `email.delivery_delayed`, `email.bounced`, `email.complained`,
   `email.opened`, `email.clicked` and `email.failed`. Copy its signing secret (`whsec_...`) into
   `RESEND_WEBHOOK_SECRET`.
4. Set `EMAIL_ADAPTER=apps.integrations.email.resend.ResendEmailAdapter`,
   `EMAIL_FROM_TRANSACTIONAL="WO Community <no-reply@mail.yourdomain>"`,
   `EMAIL_FROM_MARKETING="WO Community <community@news.yourdomain>"` and, if wanted, `EMAIL_REPLY_TO`.
5. Allow outbound HTTPS to `api.resend.com` from the workers.
6. Rotating the webhook secret: add the new secret in Resend (it signs with both for a while), deploy
   the new value, then retire the old one.

## Emails not arriving, or `FailedTask` rows for notification tasks

Look at the worker log for `EmailMisconfigured` first: it means Resend answered 401 or 403, usually a
revoked key or a sending domain that lost its verification. Fix it in Resend or the secret and replay
the dead-lettered tasks (they carry an idempotency key, so replays never double send). Repeated
`EmailTemporarilyUnavailable` means Resend is rate limiting (default 2 requests a second) or down; the
queue retries on its own. `email_rejected` log lines are single bad addresses and need no action.

## Webhook deliveries failing in the Resend dashboard

A 401 means the signing secret does not match `RESEND_WEBHOOK_SECRET` or the server clock is more than
five minutes off. A 404 means `EMAIL_ADAPTER` is not set to Resend on that environment.

## Bounce or complaint spike

`email_suppressed` log lines and `Suppression` rows show who was blocked. A sudden rise after a send
points at a bad list or content. Complaints above 0.1% or bounces above 5% on a campaign should pause
that campaign (the campaigns module will do this automatically).
