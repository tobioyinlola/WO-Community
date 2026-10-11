# 0035. Mentor calendar busy time

Status: accepted (Stage 3, closing slice)

## Decision

A mentor shares the **private iCal address** of their calendar (Google's "secret address in iCal
format", or the published address of an Outlook or Apple calendar). The platform reads it on a
schedule, keeps only the *times* the mentor is busy, and removes them from what founders are
offered. Together with the weekly and one-off windows the mentor already chooses (ADR 0030),
this lets a mentor pick the time they offer and have everything else in their life taken out of
it automatically.

## Why a feed address and not a calendar sign-in

- **No approval gate.** Reading a Google calendar with OAuth needs a sensitive-scope app
  verification by Google before it can be used by the public; Microsoft and Apple each need their
  own integration. The feed address works for all of them and for any calendar app that
  publishes one, with a single code path.
- **Least access.** The address gives read-only access to one calendar. Only times are stored.
  Revoking is the mentor's own act (reset the secret address in their calendar app, or stop
  sharing here).
- **The trade-off.** The address is a bearer secret, and feeds update on the provider's schedule
  (Google can lag by hours). That is why the preview and the stale flag exist, and why a
  founder's request is also checked against booked sessions in real time.

## How it works

- **Connecting** (`PUT /me/calendar`): the address is checked (https only, `webcal://` accepted),
  read once through the same guarded web client as link previews (public hosts only, the connection
  pinned to the checked address, redirects re-checked, 5 MB cap), and parsed. A wrong address is
  refused at once with the reason (not a calendar, unreachable, blocked), and never replaces a
  working one. 10 attempts an hour per mentor.
- **Stored.** The address is encrypted (`FIELD_ENCRYPTION_KEYS`) and never returned; the API shows
  only its host. The busy ranges are stored without titles, guests or places, replaced whenever the
  feed changes, for the next 62 days.
- **Refreshed** every 15 minutes by a worker (`mentorship.sync_calendars`), or on demand once a
  minute (`POST /me/calendar/sync`). No request waits on a calendar provider; offered times are
  computed from stored ranges (`scheduling.external_busy`).
- **A failed read makes the mentor look busier, never freer.** The ranges from the last good read
  are kept, and the status shows `error` with the reason and `stale` once the read is more than 3
  hours old. Mentors who are no longer active lose their connection.
- **What counts as busy.** Events that are not cancelled and not marked "free"
  (`TRANSP:TRANSPARENT`). All-day events are ignored unless the mentor turns on `include_all_day`
  (they are often reminders and birthdays). Recurring events are expanded inside the window, with
  deleted occurrences and moved or edited single occurrences honoured. Times with a zone name we do
  not know (some Outlook names) are read in the mentor's time zone.
- **Hostile feeds are bounded.** The parser caps events (20,000), occurrences per series (1,000),
  ranges (5,000) and event length (31 days), does not expand rules that repeat every few seconds,
  minutes or hours, and skips a broken event instead of failing the feed.
- **Choosing available time.** `GET /me/availability/preview?days=` returns, for the coming days,
  the mentor's windows, the calendar busy time, the booked sessions, the free time left and the
  start times founders would see, so a mentor can adjust `PUT /me/availability` with the result in
  front of them.
- **Effects.** The offered times, the "is this time bookable" check on a request or a move, and
  the availability signal in recommendations all use the busy time. Recommendations are refreshed
  when a mentor's busy time changes.

## Consequences

- A calendar's busy time can be up to 15 minutes old (plus the provider's own delay). A founder's
  request for a time the mentor has just filled is still the mentor's to decline.
- Sessions are not written *to* the mentor's calendar; the `.ics` file and the video meeting
  invitation (ADR 0032) are how a session gets there. Writing events would need the sign-in this
  design avoids.
- A feed with a very large number of events within the window will be truncated at the caps
  above rather than refused.
