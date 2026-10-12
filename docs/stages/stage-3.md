# Stage 3: Learning and mentorship

Scope from the brief: courses, progress, certificates, YouTube URL validation, lesson progress, then
mentor applications and approval, mentor profile, availability, matching, requests, booking with
exclusion constraints, Google and Zoom adapters, reminders and feedback.

## Slice 1: the learning hub (done)

Design and trade-offs are in ADR 0028.

| Endpoint | What it does |
|---|---|
| `GET /courses`, `GET /courses/categories`, `GET /courses/{id}` | Catalogue (filter text, category, level, access, `enrolled`), and a course with its outline, locks, progress, resume point and your rating. |
| `POST /courses/{id}/enrol` | One action for free courses; 402 for paid ones until purchasing exists. |
| `GET /me/courses` | Your courses with percent complete. |
| `GET /lessons/{id}` | Open a lesson (video id and privacy-enhanced embed address, reading text, or resource link). Visitors allowed on courses opened to them. |
| `PUT /lessons/{id}/progress` | Save position and completion; finishing the last lesson completes the course. |
| `PUT /courses/{id}/rating` | Rate 1 to 5 with optional feedback (enrolled members). |
| `GET /certificates`, `/certificates/{id}`, `/certificates/{id}/pdf` | Your certificates and the PDF download. |
| `GET /public/courses`, `/public/courses/{slug}`, `/public/certificates/{code}` | Courses open to visitors, and certificate verification. |
| `/admin/courses...`, `/admin/modules...`, `/admin/lessons...` | Author, reorder, duplicate, publish, cover, stats, enrolments, ratings, grant access. |

Notices: certificate ready, access granted. Segments: `learner_free`, `learner_paid`,
`course_completed`. The dashboard has a live learning section.

## Slice 2: mentor applications and profiles (done)

Design in ADR 0029. Endpoints: `POST /mentor-applications`, `GET /me/mentor-application`,
`PATCH` and `DELETE /mentor-applications/{id}`, `GET /mentors`, `GET /mentors/{member id}`,
`GET` and `PUT /me/mentor-profile`; admin: `GET /admin/mentor-applications`, `.../{id}`,
`POST .../{id}/decision`, `GET /admin/mentors`, `POST /admin/mentors/{id}/revoke` and `/restore`.

## Slice 3: availability and recommendations (done)

Design in ADR 0030. Endpoints: `GET` and `PUT /me/availability`, `GET /mentors/{id}/availability`,
`GET /mentors/recommended`, `GET` and `PUT /me/mentorship-needs`, `GET /me/mentoring`, and the
`available` filter on `GET /mentors`. Mentors also appear in global search (`types=mentors`).

## Slice 4: mentoring sessions (done)

Design in ADR 0031 (sessions) and ADR 0032 (video meetings).

| Endpoint | What it does |
|---|---|
| `POST /sessions` | Ask a mentor for one of their bookable times (`mentor_id`, `starts_at`, `topic`, `message`). The time is held while the mentor decides. 5 waiting requests, 10 a day, one waiting request per mentor. |
| `GET /sessions` | Your sessions as mentor or founder. `state`: `upcoming`, `pending`, `past`, `closed`, `all`; `role`; keyset paging. |
| `GET /sessions/{id}` | One session: parties, meeting, any suggested time, feedback and what you can do (`actions`). 404 for anyone else. |
| `POST /sessions/{id}/accept`, `/decline` | The mentor answers. Declining needs a reason. |
| `POST /sessions/{id}/cancel` | Either person cancels (a founder can withdraw a waiting request). A confirmed session needs a reason; inside 24 hours it is marked late. |
| `POST /sessions/{id}/reschedule` | Suggest another bookable time. `DELETE` withdraws it or keeps the original time. `POST .../reschedule/accept` moves the session. |
| `PUT /sessions/{id}/meeting-link` | The mentor adds their own https link when the platform could not make a meeting. |
| `PUT /sessions/{id}/feedback` | Founder: stars, comment or "mentor did not come". Mentor: held or "founder did not come". Open 14 days. |
| `GET /sessions/{id}/calendar.ics` | The session as a calendar file. |
| `GET /admin/sessions`, `/admin/sessions/{id}`, `POST .../cancel` | Support: list (status, mentor, founder), one session with both sides' feedback, and cancel with a reason (audited). Permission `sessions.manage`. |

Also: `meeting_provider` on `PUT /me/mentor-profile` (`google_meet`, `zoom` or blank for the
default); `GET /mentors/{id}/availability` now omits weeks with no places left. Timed jobs:
`mentorship.expire_requests`, `mentorship.send_reminders`, `mentorship.complete_due`. New settings:
`MEETING_DEFAULT_PROVIDER`, `MEETING_GOOGLE_MEET_ADAPTER`, `MEETING_ZOOM_ADAPTER`,
`GOOGLE_MEET_*`, `ZOOM_*` and the `MENTORSHIP_*` session limits (see `.env.example`).

## Slice 5: course files (done)

Design in ADR 0033.

| Endpoint | What it does |
|---|---|
| `POST /uploads` with `purpose: course_file` | Reserve a document upload (PDF, DOCX, XLSX or PPTX up to 25 MB). Only people who manage courses. Then upload and complete as for images; the result is `ready` with a `size` and no public address. |
| `POST /admin/modules/{id}/lessons`, `PATCH /admin/lessons/{id}` with `upload_id` | Put the document in a resource lesson instead of a `resource_url`. Admin lessons show `file` (name, size, type). |
| `GET /lessons/{id}/file` | A 5 minute signed link that saves the file as an attachment. Same access rule as opening the lesson. |

`resource` in lesson detail now says `kind` (`link` or `file`), with `size` and `content_type`.
New setting: `STORAGE_PRIVATE_BUCKET` (a private bucket; the media bucket stays public).

## Slice 6: mentor calendar busy time (done)

Design in ADR 0035.

| Endpoint | What it does |
|---|---|
| `GET /me/calendar` | Whether a calendar is shared, its host, when it was last read, any error and whether it is stale. The address is never returned. |
| `PUT /me/calendar` | Share the private iCal address (`feed_url`, https or webcal) and/or set `include_all_day`. Read once at once, so a wrong address is refused with the reason. |
| `POST /me/calendar/sync` | Read it now (once a minute). Otherwise a worker reads it every 15 minutes. |
| `DELETE /me/calendar` | Stop sharing; forgets the address and the busy time. |
| `GET /me/availability/preview?days=` | Your windows, calendar busy time, booked sessions, free time and the start times founders see. |

Setting: `CALENDAR_FEED_READER` (the web reader by default; a fake in tests).

## Decisions recorded

- **Paid video** stays on unlisted YouTube behind the application lock (ADR 0034), with the
  conditions that would reopen it.

## Stage 3 closing notes

Stage 3 is complete except for one item that is a decision, not work:

- **The CDN purger.** The `cdn` adapter still has only logging and fake purgers because no CDN
  provider has been chosen (Cloudflare, CloudFront and Fastly are the usual candidates). Choose
  one before hardening or any deploy; the work is one adapter class plus its credentials.

Carried forward:

- Sessions are not written to a mentor's calendar (it would need a sign-in); the `.ics` file and
  the meeting invitation carry them there.
- Stage 4 adds purchasing, which creates enrolments with source `purchase`; paid courses can be
  watched and downloaded only through enrolment until then.
