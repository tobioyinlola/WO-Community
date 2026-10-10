# 0015. Product analytics capture

Status: accepted (Stage 1)

## Decisions

- **One function records events.** `analytics.track(name, actor_id=..., properties=...)` writes the
  event in the caller's database transaction. That gives the guarantee the design asks of the outbox
  (an event exists exactly when the action committed, nothing is lost on a crash, nothing is recorded
  for a rolled back change) without a second hop: the event table is itself the durable queue the
  forwarder reads.
- **Recording can never break a request.** The insert runs in a savepoint. In production any failure
  (a bad event, a database problem) is logged as `analytics_event_dropped` and swallowed, leaving the
  surrounding transaction healthy. In tests and local runs `ANALYTICS_STRICT` makes it raise so a
  wrong event is caught immediately.
- **A registry defines every event** (`apps/analytics/registry.py`): all the events in the
  requirements, with their allowed properties. A property is a number in a range, a yes/no, one of a
  fixed set of words, or a short identifier (a slug). **There is no free text type**, so names, bios,
  rejection reasons and posts cannot enter analytics. Unknown events and unknown properties are
  refused.
- **Who may report what.** The browser may report only events it alone can see (page views, clicks);
  anything about an action the server performs (a member approved, an invitation sent) is recorded by
  the server and a browser cannot claim it. `POST /analytics/events` takes batches of up to 50, reports each
  rejected event with a reason and keeps the rest, ignores a bad token (treats the caller as a
  visitor) so tracking can never fail a page, and does not trust the browser's clock (nothing in the
  future, nothing more than a day old).
- **Identity.** A visitor's anonymous id is chosen by the browser, and only after they agree to
  analytics. At registration it is sent with the form and linked to the new member, so the funnel from
  directory visit to registration is continuous. The first link for an id wins, so a shared browser
  is never credited to a second person. For events about a member (approved, suspended, removed) the
  member is the actor; who acted is in the audit log.
- **Opting out.** `PUT /me/analytics-preferences {"opt_out": true}` stops everything: browser and
  server events about that member are discarded and no new visitor link is made. The choice takes
  effect at once (cached for five minutes between database reads, and refreshed when changed).
- **Storage.** `analytics_event` is an append-only table partitioned by month from the first
  migration, with a BRIN index on time, created by SQL and unmanaged by Django. Rows are never
  updated. A daily job keeps partitions ready three months ahead; another drops whole partitions
  older than 13 months (instant, no dead rows).
- **Forwarding.** A job every minute sends events to the analytics tool in order, in batches of 500,
  through a sink adapter (`ANALYTICS_SINK`; a logging sink until a tool is chosen). Progress is a
  cursor on the event sequence number, moved only after the sink accepts the batch, so a failure
  re-offers the same batch; delivery is at least once and the tool must dedupe on the event id. The
  cursor row is locked while sending so two forwarders never send the same events. Events are held
  for 60 seconds before forwarding so one numbered early that commits late is never skipped. Identity
  links are forwarded the same way.
- **Where it sits.** `analytics` is a level 0 module that depends on nothing, so any module can call
  it. The forwarder lives in `integrations` (which may import analytics) and the optional-login
  check for `/analytics/events` is injected by setting, because analytics cannot import accounts.

## What the registry contains today

All events from section 11.1 of the requirements are registered. Those whose modules do not exist yet
(posts, jobs, learning, mentorship, newsletters) have no emitter until those modules are built. Live
now: `email_verified`, `member_approved`, `member_rejected`, `member_suspended`, `member_removed`,
`invitation_sent`, `invitation_registered`, `profile_updated`, plus the browser events
`registration_started`, `registration_step_completed`, `registration_abandoned`, `directory_viewed`,
`startup_page_viewed`, `website_link_clicked` and `join_cta_clicked`. `onboarding_completed` needs the
onboarding checklist.

## Consequences

Dashboards, the daily summary tables and the marketing tags (PRD 11.2 and 11.3) are not built: they
read this table and belong with the admin dashboard and campaigns work. Monthly archival of expired
partitions to columnar files in object storage is also still to do; until it exists the retention job
should be left to run only once data approaches 13 months old (nothing is that old yet).
