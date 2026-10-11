# 0032. Video meeting providers: Google Meet and Zoom

Status: accepted (Stage 3, fourth slice)

## Decisions

- **An adapter per provider behind one interface** (`apps/integrations/meetings`): `create`,
  `reschedule` and `cancel`. Callers ask for a provider by name (`google_meet` or `zoom`), and
  `MEETING_PROVIDERS` maps each name to its adapter, as `EMAIL_ADAPTER` does for email. Tests and
  local runs use `FakeMeetingProvider`, which keeps meetings in memory and invents addresses.
- **The platform makes the meetings.** Meetings are created on one platform account, not on each
  mentor's account, so mentors need no sign-in or app approval and the platform can always cancel or
  move what it made. Google Meet links are made as events on one platform calendar through an OAuth
  refresh token (`GOOGLE_MEET_*`); Zoom meetings use a Server-to-Server OAuth app
  (`ZOOM_ACCOUNT_ID`, `ZOOM_CLIENT_ID`, `ZOOM_CLIENT_SECRET`). The two attendees are named on the
  invitation so the provider's waiting room and calendar show them, but providers are told not to
  email anyone (`sendUpdates=none`, `email_notification=false`): the platform sends its own notices.
- **Mentors choose.** A mentor can set `meeting_provider` on their profile; blank uses
  `MEETING_DEFAULT_PROVIDER`. The provider is fixed when the session is confirmed, so a later change
  affects only new sessions.
- **Never inside a request.** Confirming a session publishes `mentorship.session_confirmed`; a
  worker creates the meeting, so a slow or failing provider never delays or fails the mentor's
  answer. The session shows `meeting.state` of `pending`, then `ready` with the address.
- **Failures are sorted by whether retrying helps**, the same three kinds as email: *rejected*
  (bad request, unknown meeting: record and tell a person), *temporarily unavailable* (rate limit,
  timeout, 5xx: the task retries with backoff) and *misconfigured* (credentials or token refused: a
  person must fix it, and it is not hidden). After the last retry, or on a rejection, the session's
  meeting becomes `failed` and the mentor is told to add their own link
  (`PUT /sessions/{id}/meeting-link`, https only, never fetched by the server). The founder is told
  when it appears. A session is never left without a way to meet.
- **Safe to repeat.** Google gets the booking id as the conference request id. Zoom has no
  idempotency key, so the task claims the session row and stores the meeting id the moment the call
  returns; a task that crashes between those two steps could leave a stray Zoom meeting, which is
  harmless (nobody has its address). A meeting created for a session that was cancelled meanwhile is
  deleted at once. A session moved while its meeting was being made is moved afterwards.
- **Cancelling and moving** call the provider from a worker too. A meeting already gone (404 or
  410) is not an error. Meetings the mentor supplied themselves are never touched.
- **Tokens** are cached for slightly less than their lifetime and fetched again after a 401, so an
  early expiry costs one extra call.
- **Production** refuses to start with the fake provider as the default, and with the default
  provider's credentials missing.

## Consequences

Meetings live on the platform's accounts, so the provider plan limits (for example Zoom's
concurrent meetings) are the platform's. Putting sessions on a mentor's own calendar automatically
would need a per mentor sign-in and is not built; the `.ics` file and the meeting invitation are
the answer. Reading a mentor's calendar for busy time is a separate, sign-in free design
(ADR 0035). Recording, transcripts and attendance reports are not used.
