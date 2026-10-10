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

## Analytics events not reaching the analytics tool

The `analytics.forward` job (every minute, queue `analytics`) moves a cursor through the event table
and sends batches to the sink. If the tool is down the batch is simply offered again next minute; no
events are lost, they queue in our own table. Check the worker log for the sink's error, and compare
`ForwardCursor.last_seq` with the highest `seq` in `analytics_event`. A lag of a few minutes is normal
(events are held 60 seconds on purpose). Delivery is at least once, so the tool must ignore repeated
event ids.

## `analytics_event_dropped` in the logs

In production a malformed event is dropped instead of failing the request. A steady stream of these
means a code path is emitting an event that does not match the registry; the log line names the event
and the reason. Fix the caller or the registry.

## Analytics partitions

The daily job keeps the next three months of partitions ready. If rows ever land in
`analytics_event_default`, the job did not run; run `analytics.ensure_partitions` and move the rows.
The retention job drops partitions older than 13 months. Archive them to object storage first once
the archive job exists.

## Google sign-in failing

`google_unavailable` (503) means our server could not fetch Google's signing keys; check outbound
access to `www.googleapis.com` (log line `google_keys_unreachable`). A spike of
`invalid_google_token` (401) usually means `GOOGLE_CLIENT_ID` does not match the id the frontend is
using, or a client clock is far off. Setting `GOOGLE_CLIENT_ID` to empty switches the feature off
without a deploy of code; password sign-in is unaffected.

## Link previews not appearing

Cards are filled in by the `feed.fetch_link_preview` task on the `media` queue. Check that the queue
has a worker and is not backed up. For one address, read `LinkPreview.fail_code`: `blocked_address`,
`internal_host`, `bad_scheme`, `bad_port` and `credentials_in_url` are deliberate refusals;
`timeout`, `network_error`, `dns_failure` and `status_NNN` are the site or the network, and are
retried an hour after someone next links the address; `nothing_to_show` and
`unsupported_content_type` mean the page offers no usable preview. A burst of `blocked_address` for
names that look ordinary can mean the resolver is returning private answers; do not loosen the checks,
fix the resolver.

The media workers should run with outbound access limited to the public internet (no route to the
VPC, metadata service or internal DNS). The application checks are the second line of defence.

## Notifications not arriving

In-app notices are created by tasks reacting to outbox events (`feed.notify_*`,
`notifications.notify_approved`). If members report none, look for stuck `OutboxEvent` rows with
topics `feed.*` and for failures of those tasks. `GET /notifications` should answer 304 when nothing
changed; a client that never gets 304 is not sending `If-None-Match`. Email notices stop quietly for
a member who exceeds ten of one kind in an hour (log line `notification_email_throttled`); their
in-app notices continue.

## Jobs not expiring or no expiry warnings

Expiry is two beat tasks: `jobs.expire_due` (every 15 minutes) and `jobs.warn_expiring` (hourly).
If posters report expired jobs still showing, remember the board hides a job the moment it passes
its expiry whether or not the sweep has run, so a visible expired job means the data is wrong;
check `expires_at`. If warnings are missing, check that beat is running and look for the
`jobs.expiring` outbox events. Daily alert digests come from `jobs.send_digests` (hourly check).

## Member jobs piling up for review

The count is `jobs_awaiting_review` on `GET /admin/queues` and the list is
`GET /admin/jobs?status=pending`. A super admin can switch the board to auto publish with
`PUT /admin/jobs/settings`; jobs already pending stay pending until an admin decides them.

## Scheduled news items not appearing

Scheduled items are published by `editorial.publish_due`, which beat runs every minute. If an item
is past its time and still scheduled, check that beat and a worker are running; the item is then
published with its scheduled time on the next run, nothing is lost. A scheduled time in the past is
rejected when scheduling, so a stuck item always means the sweep is not running.

## Event reminders not arriving

Reminders come from `events.send_reminders` (beat, every ten minutes) and are claimed per
registration before sending, so a restart never double-sends. A member who registered inside the
24 hour (or 1 hour) window is deliberately skipped for that reminder. If nobody gets reminders, check
that beat is running and that the event is still published; cancelled events send none.

## A newsletter is stuck or must be stopped

To stop one at once, pause it (`POST /admin/campaigns/{id}/pause`); nothing more is sent until it is
resumed, and cancelling leaves the unsent unsent. A campaign that pauses by itself means the email
provider rejected our credentials or sending domain (log line
`campaign_paused_provider_misconfigured`): fix the provider setup, then resume. A campaign that
stays in `sending` with queued recipients and no progress means its worker was lost; the
`campaigns.start_due` task re-kicks it every minute, so check that beat and the `email` queue
workers are running. Unsubscribes and bounces are honoured per message just before sending, so
there is no need to stop a campaign because someone asked to be removed.

## Unsubscribe links not working

`POST /unsubscribe` needs the signed token from the email. A 400 means the link was altered or
signed with a different `SECRET_KEY` (for example after rotating it), in which case old emails'
links stop working; keep the old key in rotation until old mail is no longer actionable. The web
page in the link is the front end's `/unsubscribe` route, which should call this endpoint.
