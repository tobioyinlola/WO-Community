# 0026. Newsletters: segments, campaigns and unsubscribing

Status: accepted (Stage 2)

## Decisions

- **Who may be mailed.** Only active members with a verified address whose *latest* marketing
  consent is a yes, and whose address is not on the suppression list. Consent is recorded as a
  versioned history (never overwritten), captured at registration and changeable at
  `PUT /me/marketing-consent`. Account emails (verification, password reset, approvals, notices)
  are separate and never stop.
- **Segments are validated JSON, not expressions.** A strict serializer allows a fixed list of
  attributes: country, sector, stage, skills, roles, joined and last active dates, profile
  completeness range and tags. Unknown keys, bad values and oversize lists are refused. Several
  values in one list mean "any of these"; different attributes must all hold. Each attribute is
  answered by the module that owns it (accounts, profiles, startups, feed, jobs) returning member
  ids; nothing the admin types reaches SQL. An empty segment is everyone mailable.
- **Tags** available now: `profile_complete` (score 80 or more), `registered_incomplete` (not that),
  `directory_listed`, `founder_active` (posted or commented in 30 days), `founder_dormant` (not in
  60 days) and `job_poster`. Course enrolment and the mentor and learner tags arrive with those
  modules.
- **Preview** reports two numbers: members who match, and of those how many can really be mailed.
- **Content** is a list of blocks (heading, paragraph, button, image, divider), the structure a
  visual editor edits. Text is escaped when rendered; paragraphs pass the same allow list as
  comments; button and image links must be https; images come from finished `campaign_image`
  uploads. The only merge field is `{{first_name}}` (subject and text), filled from the member's own
  name with a polite fallback; any other `{{field}}` is refused when saving. Templates are saved
  block lists; creating a campaign from one copies the blocks.
- **Every email** carries an unsubscribe link in the body and the `List-Unsubscribe` and
  `List-Unsubscribe-Post: One-Click` headers (RFC 8058), sends on the marketing stream and is
  tagged with its campaign. The link holds a signed token that only the server can create.
- **Unsubscribing** (`POST /unsubscribe`, no login) withdraws marketing consent, suppresses the
  address and credits the campaign, all at once, which is stricter than the 24 hours allowed.
  Repeating it is harmless, a forged or altered token is refused, and the endpoint is rate limited.
  Agreeing again later lifts an unsubscribe but never a bounce or complaint block.
- **Sending.** Starting a send freezes the audience into per-person rows and records the segment as
  it was. Batches of 50 go out on the email queue with a short pause between them. Before each
  message the person's consent and suppression are checked again, so an unsubscribe or a bounce
  that arrives mid-send is honoured immediately. A provider that is only busy leaves the rest queued
  for the next run; a message it will never accept is dropped; a credentials problem pauses the
  campaign rather than losing mail. A beat task starts scheduled campaigns and re-kicks any send
  whose worker was lost; claimed rows and the provider idempotency key stop double sends.
- **Controls.** `campaigns.send` (community admins and above) with MFA. Starting, scheduling and
  resuming need a fresh step-up; pausing (the kill switch) and cancelling deliberately do not, so
  stopping is never slower than starting. Test sends go to the admin alone. Every action is audited.
- **Reporting.** The provider's delivery reports (already received and verified by the notifications
  module) update each recipient as they arrive, through a listener the notifications module offers,
  so the report survives the 30 day purge of raw webhook data. A click implies an open and a
  delivery. The report counts people: sent, delivered, opened, clicked, bounced, unsubscribed,
  complained, plus skipped and failed, with open and click rates of those sent.

## Consequences

Open counts are approximate (mail clients block or fake tracking pixels), as everywhere. A/B tests,
resend to non-openers, per-link click detail, send-time optimisation and the campaign analytics
events (`newsletter_sent` and the rest) are not built. The `newsletter` entry in the notification
preferences matrix is unused for email; marketing email is governed by marketing consent alone.
Sender domain setup (SPF, DKIM, DMARC, separate marketing subdomain, warm-up) is operational work.
