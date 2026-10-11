# 0031. Mentoring sessions: requests, booking, moving, cancelling, reminders and feedback

Status: accepted (Stage 3, fourth slice)

## One row for the whole life of a session

A founder's request and the booked session are the same row (`MentorSession`). Its status runs
`requested` → `confirmed` → `completed` (or `no_show`), or ends early as `declined`, `cancelled`
or `expired`. Keeping one row, rather than a request table and a booking table, means the database
can guard the calendar directly:

- **A request holds its time.** While a session is `requested` or `confirmed`, a PostgreSQL
  exclusion constraint refuses another active session for the same mentor that overlaps it, and
  another for the same founder (a founder cannot be in two places). Two founders asking for the
  same time at once is settled by the database, not by a check-then-write race; the loser gets 409.
  The service checks first for a clear message and the constraint settles the race, as with
  availability windows (ADR 0030). Touching sessions are fine.
- **One waiting request per founder and mentor** (a partial unique index), at most 5 waiting
  requests per founder and 10 requests a day. These are configuration
  (`MENTORSHIP_MAX_OPEN_REQUESTS`, `MENTORSHIP_REQUESTS_PER_DAY`).
- **Capacity is exact.** The mentor profile row is locked while a request is checked, then the
  places used in the mentor's Monday to Sunday week (local time) are counted. Places are used by
  requested, confirmed, completed and missed sessions; declined, cancelled and lapsed ones give the
  place back. A week with no places left offers no start times, but other weeks still do.
  (ADR 0030 said a mentor with no sessions left this week offers nothing at all; that was a
  stand-in until bookings existed.)
- **Only offered times can be asked for.** A request must be one of the start times
  `GET /mentors/{id}/availability` would offer (same notice period, same horizon, same free-time
  rules), so an off-grid or stale time is a 409, never a quiet double booking.

## Answering, lapsing and finishing

- **The mentor answers** (`/accept` or `/decline`). Declining needs a reason the founder sees.
  Accepting makes the session `confirmed` and starts creating the video meeting (ADR 0032).
- **Unanswered requests lapse.** A worker closes a request after 72 hours, or 2 hours before its
  start, whichever comes first, which frees the held time, and tells the founder
  (`mentorship.expire_requests`, every 10 minutes).
- **Finishing.** 15 minutes after a confirmed session ends, a worker marks it `completed` and asks
  both people for feedback (`mentorship.complete_due`, every 5 minutes). The platform cannot know
  whether the meeting really happened, so `completed` means "it was scheduled and its time has
  passed"; feedback is where either side says otherwise.
- **Reminders.** 24 hours and 1 hour before the start, both people get a notice and email
  (`mentorship.send_reminders`, every 5 minutes). Each reminder is claimed on the row before it is
  sent, so a restart cannot send it twice, and someone who confirmed inside a window is skipped for
  it (the same rule as event reminders). A moved session starts its reminders again.

## Cancelling and moving

- **Cancelling.** The founder can withdraw a waiting request or cancel a confirmed session; the
  mentor can cancel a confirmed session (a waiting request is declined, not cancelled). A confirmed
  session needs a reason, which the other person sees. Cancelling inside 24 hours of the start is
  recorded as `late_cancel` so support can see patterns; nothing is punished automatically.
  Nobody can cancel a session that has started.
- **Moving needs agreement.** Either person suggests one of the mentor's bookable times
  (`POST /sessions/{id}/reschedule`); the session keeps its time until the other person accepts.
  Accepting re-checks the time (another request may have taken it, which is 409 and leaves the
  original time), moves the session, resets its reminders and moves the video meeting. A
  suggestion can be withdrawn by its author or refused by the other person with
  `DELETE /sessions/{id}/reschedule`. A newer suggestion replaces an older one, so a counter offer
  is just a new suggestion. A session can be moved 3 times; after that, cancel and ask again.
- **A mentor who is withdrawn.** The `MentorRevoked` event cancels every open session of that
  mentor with the reason "no longer available" and tells both people. Admins can cancel any
  session with a reason (`sessions.manage`, audited), which also tells both people.
- **A member who is suspended or removed** has their open future sessions cancelled the same
  way (as mentor or as founder), and the other person is told. Reinstating does not bring them
  back; a new request is needed. A paused mentor keeps sessions already agreed (pausing only
  hides them from new requests).

## Feedback and ratings

- **Founders** give 1 to 5 stars and an optional comment, or report that the mentor did not come.
  Stars feed the mentor's rating, and sending feedback again corrects the rating rather than adding
  a second one (the rating count and total are adjusted under a lock). Reporting a no-show takes
  the stars back.
- **Mentors** record whether the session was held or the founder did not come, with an optional
  private note. `mentee_no_show` changes the status to `no_show`; changing it back restores
  `completed`.
- **Who sees what.** A founder sees their own feedback only. The mentor sees the founder's stars and
  comment (never public, and never attributed to the founder anywhere but the mentor's own
  session). Admins see both sides. Feedback is open for 14 days after the session.
- **Matching.** Mentors with at least 3 answered requests in the last 90 days have their median
  reply time added to the quality signal (a quarter of it: replies within 4 hours score full,
  a week or more nothing), and "usually replies within a day" shows as a reason. This closes the
  note in ADR 0030 that reply time would join once requests existed.

## Elsewhere

- **Notices** (preference group `mentorship`, in app and email): request received, confirmed,
  declined, cancelled, lapsed, new time suggested, accepted or refused, reminders, feedback
  request, meeting link problems and added. Request and suggestion emails are rate limited per
  recipient.
- **Dashboard** mentorship section gains `requests_waiting`, `sessions_upcoming` and
  `sessions_held_30d`; segments gain `mentee`; analytics records `mentorship_requested`,
  `mentorship_accepted` and `mentorship_declined` (with response hours), `session_booked`,
  `session_rescheduled`, `session_cancelled`, `session_completed` and `session_feedback_submitted`.
- **Calendar file.** `GET /sessions/{id}/calendar.ics` returns an iCalendar event with the meeting
  address, so a session can go in any calendar app.

## Consequences

The mentor's own calendar busy time is covered by ADR 0035 (a shared private calendar address).
Recurring sessions, group sessions, payments for mentoring and an in-app message thread between the
two people are not built.
