# 0025. Events and demo days

Status: accepted (Stage 2)

## Decisions

- **Event types** are demo day, workshop, meetup and announcement. Admins (`events.manage`:
  community admins and above) create events as drafts and publish, cancel or remove them. Content
  editors cannot manage events. Every change is audited.
- **Times.** An event has a start, an end (after the start, at most 14 days long) and a time zone
  name such as `Africa/Lagos`. Instants are stored and returned in UTC with the zone name beside them,
  so clients show local time without us guessing. A draft needs a future start before it can be
  published.
- **Registering.** Active members register for a published event until it starts, while registration
  is open and while there is room. The check runs with the event row locked, so many people
  registering at once can never exceed the capacity (tested with concurrent requests). A blank
  capacity means unlimited. Registering again is harmless, cancelling is allowed until the start, and
  there is no waiting list. The count shown is counted from the registrations, never a stored number
  that could drift.
- **Cancelling, moving and unpublishing.** Cancelling keeps the event visible with its status (so
  people see why it is gone), closes registration and tells everyone registered. Changing the times
  of a published event also tells them and resets their reminders. An event with registrations cannot
  be unpublished, because that would silently drop people; cancel it instead. Capacity cannot be
  lowered below the number registered.
- **Notices** go through `notify()` under the existing event-reminder preference: a confirmation on
  registering, reminders 24 hours and 1 hour before the start, and cancellation and rescheduling
  notices. A sweep every ten minutes sends reminders; someone who registered inside a reminder window
  does not also get that reminder, because the confirmation already covered it.
- **Calendar.** `GET /events/{id}/calendar.ics` returns an iCalendar file (UTC times, escaped text,
  a stable UID so re-importing updates rather than duplicates, and `STATUS:CANCELLED` when it is).
- **Demo days.** An admin sets the presenting startups and pitch order as one list (maximum 20, each
  startup once, optional https pitch link). Startups appear to a viewer only if their basics are
  visible to that viewer.
- **Archive.** After an event ends, `GET /events?when=past` lists it newest first and the detail
  shows the recording link and summary the admin added; before it ends those are hidden.
- **Attendee list and export.** Admins can list attendees (names and email addresses), export a CSV
  and mark people checked in. Because this is personal data, reading the list or exporting needs a
  fresh MFA step-up and both are recorded in the audit log. CSV cells that start with `=`, `+`, `-`,
  `@`, a tab or a carriage return are prefixed with an apostrophe so a spreadsheet cannot run them as
  formulas.
- **Public pages.** Events marked `public` appear at `GET /public/events` and
  `/public/events/{slug}` with Open Graph data and a share link, cached with ETags. They never show
  the join link, capacity, registration counts or any attendee information. Publishing, editing,
  cancelling and removal purge the CDN paths.

## A route that changed

`GET/POST /events` belongs to this module, as the design lists it. The analytics ingest endpoint had
been mounted at `POST /events`; it moved to `POST /analytics/events` (nothing consumes it yet). The
analytics ADR and stage notes are updated.

## Consequences

Hosts, speakers and sponsors, ticketing and payments, recurring events, waiting lists, and sending
the attendee list directly to the organiser are not built. Events are not in member search or in the
directory sitemap (same layering reason as jobs and news).
