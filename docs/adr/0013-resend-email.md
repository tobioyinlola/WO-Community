# 0013. Resend as the email provider

Status: accepted (Stage 1). Resolves the open decision "email provider and sending domains".

## Decisions

- **Resend behind the existing adapter.** `ResendEmailAdapter` implements the email interface, so
  no module changed to adopt it. Select it with
  `EMAIL_ADAPTER=apps.integrations.email.resend.ResendEmailAdapter`; local development and tests
  keep the in-memory fake. Production refuses to start with Resend selected unless the API key, the
  webhook secret and both sender addresses are set.
- **Two sending identities.** Transactional mail (verification, reset, approval, invitations) and
  marketing mail use different `From` addresses, ideally different subdomains
  (`mail.` and `news.`), so complaints about a newsletter cannot damage the reputation of password
  resets. The adapter picks the sender from the message's stream.
- **Failures are sorted by what to do about them:**

  | Resend answers | Meaning | Handling |
  |---|---|---|
  | 400, 404, 422 and other 4xx | The message can never be accepted (bad address, bad content) | `EmailRejected`: dropped and logged without the address; retrying cannot help |
  | 429, 5xx, timeouts, connection errors, concurrent duplicate | Transient | `EmailTemporarilyUnavailable`: the task retries with backoff, then dead-letters |
  | 401, 403 | Wrong or restricted key, or the sending domain is not verified | `EmailMisconfigured`: raised and alerted, never hidden |

- **A message is sent at most once.** Every send carries an `Idempotency-Key` that is a hash of the
  recipient, subject and body. A retry after a timeout cannot deliver twice, and an identical notice
  repeated within Resend's 24 hour window (for example the "you already have an account" email that
  someone keeps triggering for a victim's address) goes out once.
- **Webhooks.** `POST /api/v1/webhooks/email/resend` verifies the Svix signature over the exact bytes
  received (delivery id, timestamp and body), rejects timestamps more than five minutes from now so
  a captured delivery cannot be replayed, and accepts any one valid signature so the secret can be
  rotated. A valid delivery is stored raw, queued through the outbox and acknowledged immediately;
  repeats of the same delivery id are acknowledged and ignored. Unknown event types are stored and
  ignored so new Resend events never break anything.
- **Delivery outcomes** (`sent`, `delivered`, `delayed`, `bounced`, `soft_bounced`, `complained`,
  `opened`, `clicked`, `failed`) are recorded with the address only as a hash. A permanent bounce or a
  complaint puts the address on the **suppression list**, which marketing sends check before every
  message (transactional mail is unaffected). Raw deliveries contain addresses, so they are deleted
  30 days after processing.

## What is not covered yet

Newsletters, segments, unsubscribe links and the campaign pause on bounce or complaint rates belong
to the campaigns module; this slice provides the pieces they use (batch sending, the marketing
sender, suppression, delivery events). Emails are plain text; HTML templates arrive with campaigns.
