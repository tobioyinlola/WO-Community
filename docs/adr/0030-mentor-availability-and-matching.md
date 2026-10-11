# 0030. Mentor availability and matching

Status: accepted (Stage 3, third slice)

## Availability

- **Two kinds of window.** Weekly windows (weekday, start and end as wall clock times in the
  mentor time zone) and one off windows (UTC instants, up to 180 days ahead). A window is at least
  one session long, at most 12 hours, and cannot cross midnight. A mentor sends the whole schedule
  with `PUT /me/availability`; it replaces the old one in one transaction, so two edits cannot
  interleave. Omitted lists are emptied.
- **The database guards overlaps.** Weekly windows are stored as a range of minutes from Monday
  00:00 and one off windows as a time range, each with a PostgreSQL exclusion constraint per
  mentor (this needs the `btree_gist` extension, enabled by the migration; the database role
  that runs migrations must be allowed to create it). The service checks first for a clear
  message; the constraint settles races.
- **Wall clock stays put.** Weekly windows are expanded day by day in the mentor time zone, so
  09:00 is still 09:00 after a clock change. A mentor who moves time zone changes `timezone` in the
  same save; their weekly windows then mean the new zone.
- **Bookable times.** `GET /mentors/{id}/availability` returns start times (UTC) for the next 14
  days (at most 30; booking is capped 60 days out), with a minimum notice of 12 hours
  (`MENTORSHIP_MIN_NOTICE_HOURS`). Starts step by the session length (30, 45 or 60 minutes, chosen
  by the mentor) from the start of each whole free window, so the same times are offered however
  the question is asked and `is_bookable` accepts exactly the offered times. Booked sessions and
  the mentor external calendar busy time are subtracted; both are hooks in `scheduling.py`
  (`booked_intervals`, `external_busy`, `sessions_in_week`) that return nothing until bookings and
  calendar integrations exist. A paused mentor, or one with no sessions left this week, offers
  nothing.
- **Capacity** is sessions per week (1 to 20, default 3). The brief also mentions a monthly
  limit; only the weekly one is built.
- The directory can filter `available=true`: mentors who have published any weekly window or a
  future one off window (not a check that a slot is actually free).

## Recommendations

- `GET /mentors/recommended` scores every listed mentor (not paused, not revoked, not the caller,
  at least one session left this week) as a weighted sum of six signals between 0 and 1, and
  returns the top ones with a 0 to 100 `score`, the `reasons` as sentences, and the raw
  `components`. Weights are configuration (`MENTORSHIP_MATCH_WEIGHTS`): expertise 35, sector and
  stage fit 20, availability 15, language 10, capacity 10, quality 10.
- **Needs.** The founder saves up to 5 topics and languages (`PUT /me/mentorship-needs`) or passes
  `needs` for one request. A need matches an expertise tag when they are equal, one contains the
  other, they share a word of four or more letters, or the configured synonym lists
  (`MENTORSHIP_SYNONYMS`) link them. This stands in for the managed skill taxonomy with synonyms;
  the reference skills list has no synonyms yet.
- **A signal without data drops out** and the others are rescaled: no stated needs removes
  expertise, no startup removes fit, no languages removes language. A sparse profile is therefore
  scored on what is known, not punished.
- **Where the brief is only partly met.** Founders do not publish availability, so the
  availability signal uses the mentor bookable time in the next two weeks (10 or more free start
  times scores full) instead of mutual overlap. The quality signal uses the average rating with
  Bayesian smoothing (prior 4.0 worth 5 ratings); median response time joins when requests exist.
  There is no member blocking in the platform yet, so "blocked by the founder" cannot be applied.
- **Caching.** Ranked results are cached for 15 minutes per founder, keyed by needs, languages,
  startup details and a data version. The version moves whenever a mentor profile changes (after
  commit), a schedule is saved or the founder saves needs, so stale matches are never shown.
  `mentor_recommendation_shown` is recorded on each request.
