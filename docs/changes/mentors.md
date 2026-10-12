# Mentor settings and booking

An approved mentor gets a **Mentorship** section in Settings (a vertical list of sections beside the page) and
a banner on their dashboard, **Set up your availability**, until a weekly schedule exists.

## What a mentor sets

| Area | What it does |
| --- | --- |
| Availability | A row per day with a switch and one or more time ranges (24 hour, quarter hours). Copy to weekdays or all days, Mornings, Afternoons and Evenings presets, a time zone (defaults to the browser's), a live weekly grid and a sentence such as "Mon to Fri, 10:00 to 12:00 and 15:00 to 17:00 GMT+1" |
| Session settings | Which of 30, 45 and 60 minutes are offered and the usual one, a buffer (0, 10, 15, 30), minimum notice, booking window and the most sessions a week |
| Time off | Blocked dates or ranges, and extra time on one date. These apply as soon as they are added |
| Pricing | Free or paid, currency, price, optional price per length. See ADR 0048 |
| Meeting | Google Meet, Zoom or a personal link; the calendar connection (a private iCal address) and its status |
| Mentoring profile | Accepting new mentees (pauses booking and keeps the schedule), about, expertise, topics, languages, stages, sectors |
| Preview as mentee | The booking calendar exactly as a mentee sees it, in a time zone they can change |

A **Save changes** bar appears only when the form has unsaved changes. It says what is wrong when the form
cannot be saved: overlapping ranges, an end before a start, no range while accepting mentees, no length,
a paid price of zero, or a personal link missing.

Sessions already agreed are never deleted or moved by editing the schedule. A change that would leave one
outside the new times is refused with those sessions named, and goes through only when the mentor chooses
**Keep these sessions and save**.

## What a mentee sees

The mentor page has one booking calendar: a session length, a time zone, a strip of days that have times and
the times on the chosen day, with the price (or **Free**). Slots come from the weekly schedule less days off,
the buffer kept clear around anything booked, minimum notice, the booking window, the weekly limit, existing
sessions and the mentor's calendar. Two clicks, pick a time and confirm, make a request; the database
exclusion constraint settles two people asking for the same time at once (tested with concurrent requests).

Weekly ranges are read in the mentor's own zone, so 09:00 stays 09:00 across a clock change.

## API

| Method and path | Who |
| --- | --- |
| `GET`, `PUT /me/mentor/settings` | The mentor |
| `GET`, `PUT /me/mentor/availability` | The mentor (weekly ranges and time zone; extras and days off are kept) |
| `POST /me/mentor/exceptions`, `DELETE /me/mentor/exceptions/{id}` | The mentor |
| `GET /me/mentor/preview` | The mentor |
| `GET /mentors/{id}/slots?from=&to=&length=&tz=` | Any member, for a listed mentor |
| `POST /sessions` | Takes an optional `length_minutes`; the session records length, price and `payment_mode` |

Only approved mentors can use the `/me/mentor` endpoints (403 otherwise). `PUT` calls that would strand agreed
sessions answer 409 with the sessions in `sessions`; send `acknowledge: true` to go ahead.

## Data

`MentorSettings` (lengths, buffer, notice, window, pricing mode, default price, currency, personal link,
topics), `MentorSessionPrice` (a price per length) and `AvailabilityException` (days off). The weekly ranges
and extra time are the existing `AvailabilitySlot` rows; the time zone, weekly limit, pause switch and video
provider stay on `MentorProfile`. A mentor who never opens Settings keeps the old behaviour (one length, no
buffer, the platform notice and horizon). Sessions gained `length_minutes`, `price_minor`, `currency` and
`payment_mode`; older sessions are backfilled with the length of their time span.
