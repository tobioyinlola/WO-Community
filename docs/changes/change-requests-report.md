# Change requests: report

What was built for the seven change requests, how it was checked, what was left out on purpose, and how
to run and smoke test it. The plan written before any code is in `change-requests-plan.md`; each area has
its own page in this folder with the detail (`support.md`, `referrals.md`, `learning.md`,
`certificates.md`, `mentors.md`).

## What was built

| # | Change | Where to look |
|---|---|---|
| 1 | **Support tickets.** Contact support opens a right side drawer; a member follows the conversation in the app; admins have an inbox, saved replies, internal notes and an overdue flag. No support address exists anywhere. | `support.md`, ADR 0049 |
| 2 | **Referrals.** A short code per member, a sign up question, `/join?ref=` links, the referrer shown in the approvals drawer and the members table, dashboard cards for admins and members. | `referrals.md` |
| 3 | **Search and the bell.** One search (press `/` or Ctrl K) across members, startups, mentors, jobs, events, news and courses, recent terms, a results page, and an admin search with groups per permission. The bell opens a popover with Unread and All, read state and a cheap unread count. | ADR 0050 |
| 4 | **Learning platform.** Catalogue with filters, a course page, a lecture player with notes and questions, reviews, saved courses, access requests for paid courses, announcements, My learning, and in the console the Add course drawer wizard, a course page with tabs (curriculum, learners, requests, reviews, Q and A, announcements, settings) and the requests list. | `learning.md`, ADRs 0047, 0048 |
| 5 | **Certificates.** Own number (`WO-C-2026-000341`), the template copied onto each certificate, a stored PDF, a public verification page, an admin template editor with a live preview, list, revoke and reissue, and an opt in listing on the member profile. | `certificates.md`, ADR 0051 |
| 6 | **Mentor settings.** A Mentorship section in Settings: weekly schedule with quick fill, session lengths, buffer, notice, booking window, weekly limit, time off and extra time, free or paid pricing, meeting provider, profile, preview as mentee. Mentees book from one calendar in their own time zone. | `mentors.md`, ADR 0048 |
| 7 | **Notifications popover.** Part of 3, built first because the drawer, popover and unread count are shared. | |

Shared pieces added once and reused: `Drawer` (focus trap, Esc, unsaved changes guard), `Popover`, `Stepper`,
`Rating`, `ProgressRing`, `Accordion`, the weekly grid, the certificate sheet. They have light and dark
previews on `/admin/design`.

## Endpoints

83 operations were added (505 in total, up from 423), and one was replaced
(`GET /certificates/{id}/pdf` became `GET /certificates/{id}/download`, which returns a short lived link).
By area:

| Area | Added |
|---|---|
| Support (member) | 8: tickets, messages, reopen, feedback, attachments, public contact |
| Support (console) | 13: inbox, ticket, messages, resolve, reopen, stats, agents, saved replies, attachments |
| Search and notifications | 3 search (results, recents, clear), 1 notification |
| Referrals | 2 on members (referrer search, by code), my referrals under `me`, 2 admin |
| Learning (member) | courses 6, lessons 4, questions 1, notes 1, saved and requests under `me` |
| Learning (console) | courses 8, modules 1, reviews 2, questions 3, answers 2, course requests 3, YouTube title lookup 1 |
| Certificates | 2 member, 3 settings, 3 admin; plus `PATCH /certificates/{id}` and `GET /members/{id}/certificates` |
| Mentorship | `me/mentor/settings`, `availability`, `exceptions`, `preview`, and `GET /mentors/{id}/slots` |
| Console search | 1 |

The full list is in `docs/api/openapi.yaml`, regenerated and validated with `--fail-on-warn`; the front end
types in `frontend/src/api/schema.d.ts` are generated from it.

## Migrations

All apply on an empty database and on a copy of the previous schema with data in it, and every one reverses.

| App | Migrations | Notes |
|---|---|---|
| accounts | 0008 referral fields, 0009 backfill referral codes, 0010 unique code | Expand, backfill, then contract. Every existing account got a code, all unique. |
| globalsearch | 0001 recent searches | New table. |
| support | 0001 tickets, 0002 ticket number sequence | New app; numbers start at 1001. |
| learning | 0003 LMS fields, 0004 backfill course counts, 0005 certificates, 0006 backfill certificate hours, 0007 show on profile | An earlier certificate kept its short code and got the course length as hours. |
| mentorship | 0006 mentor settings, 0007 backfill session length | Sessions made before lengths were kept got the length of their time span (45 stayed 45). |
| uploads | 0007 support attachment purpose, 0008 certificate signature purpose | Constraint updated. |

## Decisions (ADRs)

| ADR | Decision |
|---|---|
| 0047 | Learning keeps `Module` and `Lesson` as storage names; the screens say section and lecture |
| 0048 | While payments are off, paid means a request the owner confirms (courses and mentor sessions) |
| 0049 | Support is in app only; members are told by email but do not reply by email |
| 0050 | Search ranks by similarity inside what the searcher may see |
| 0051 | Certificates are drawn with ReportLab from a shared layout, not through an HTML engine |

## How it was checked

| Check | Result |
|---|---|
| `ruff`, `black --check`, `mypy` (508 files), `bandit`, `pip-audit`, `import-linter` (3 contracts) | All clean. `pip-audit` reports no known vulnerabilities; it skips the project itself, which is not on PyPI. |
| OpenAPI | Generates and validates with `--fail-on-warn` |
| Migrations | Empty database: all apply, no pending model changes. Previous schema with legacy rows: forward, backfills verified, backward to the previous state. |
| Back end tests | BACKEND_RESULT |
| Front end | ESLint clean, TypeScript clean, production build succeeds, 106 unit tests pass across 10 files |
| End to end | E2E_RESULT |
| Visual check | 39 screens in light and dark at 1440, 1024 and 390 pixels, 234 images in `docs/changes/screenshots/` (named `screen-theme-width.jpg`) |

The visual review found and fixed these before the final capture: unread dots that disappeared in dark mode,
white cards (message bubbles, the verification card, the chosen referrer, the course badge) that kept a
white ground in dark mode and made their text unreadable, notification titles running into their time, and
"1 stars" on the review breakdown.

What each test group covers:

- **Authorisation.** Every new endpoint is tested for success, validation errors, no sign in (401), the wrong
  role (403) and someone else's record (404). Examples: a ticket belongs to its member, a certificate to its
  holder, mentor settings to approved mentors.
- **Lifecycles.** Ticket from open to resolved and reopened; referral validation, self referral refused and
  credit only after approval; search visibility (a member who hides their basics is never found); course
  publish checklist and access; progress and completion; certificate issue, verify, revoke and reissue;
  notification read state.
- **Mentor scheduling.** Slots with buffers, notice, window, weekly limit, time off, extra time and calendar
  busy time; a clock change inside the booking window; a concurrent booking of one slot, where exactly one succeeds
  and the other gets "That time is no longer available"; a schedule change that would strand agreed sessions
  is refused until the mentor chooses to keep them.
- **Browser journeys** (`frontend/e2e`): `support.spec.ts` (member sends, admin answers, member replies, admin
  resolves), `referrals.spec.ts`, `member.spec.ts` (search with `/`, bell popover, booking), `learning.spec.ts`,
  `courses-admin.spec.ts` (the wizard), `certificates.spec.ts` (view, download, share, verify, template,
  revoke, profile listing), `mentor-settings.spec.ts`, and `journeys.spec.ts` (paid course request and
  approval, two mentees racing for one time, the referrer's list and admin search for a ticket). Pages with
  new screens are also checked with axe for WCAG 2.2 AA.

## Run it

```bash
make up && make migrate
DJANGO_SETTINGS_MODULE=config.settings.local python scripts/seed_demo.py        # includes the part below
DJANGO_SETTINGS_MODULE=config.settings.local python scripts/seed_admin_demo.py
DJANGO_SETTINGS_MODULE=config.settings.local python scripts/seed_change_requests.py   # safe to repeat
make run                                      # API on :8000
cd frontend && npm run dev                    # web app on :5173

pytest                                        # back end (PostgreSQL needed)
npm run lint && npx tsc --noEmit && npm test  # front end
npx playwright test                           # browser journeys against the seeded stack
SCREENSHOTS=1 npx playwright test e2e/screenshots.spec.ts   # retake the review screenshots
```

Sign in at `/login` with `amaka@demo.test` (member, owns a certificate and a referral chain),
`ada@demo.test` (mentor with a weekly schedule), `tunde@demo.test` (has asked for the paid course) or
`admin@demo.test` (admin; the demo key is in `seed_admin_demo.py`). The password is `Demo-Passw0rd-2026`.

The seed adds: a referral chain (Amaka referred Tunde and Ngozi, who referred others) and other sources;
three more courses (free, paid in naira with a promotion, and a draft); a pending request for the paid
course; four support requests (open, in progress, awaiting the member, resolved); notifications for Amaka;
mentor pricing; and certificates, one of them revoked.

## Left out or changed on purpose

- **Real payments.** Nothing is charged. A paid course is a request an admin approves, and a paid session is
  a request the mentor confirms, with "Payment arranged directly" on every screen and notice that mentions
  the price (ADR 0048). When payments arrive, one function (`mentorship.setup.quote`) and the course access
  path are where the payment step attaches.
- **Replying to support by email.** Members are emailed, and cannot reply by email (ADR 0049).
- **Calendar connection.** The mentor connects their calendar with the private iCal address the platform
  already read. There is no OAuth sign in to Google or Microsoft.
- **Names.** The code keeps `Module` and `Lesson` (ADR 0047).
- **Referral approval in the browser.** The browser tests cover the sign up question, the approvals drawer
  and the dashboards. Approving a new applicant needs their email confirmed, so that last step (credit only
  after approval, and the referrer's list) is covered by the back end tests rather than a browser test.
- **Notices sent through the worker.** Some notices (for example "you now have access to a course") go out
  through the outbox and need the worker and scheduler running. They are tested in the back end, and the
  browser tests do not wait for them.
- **Booking calendar preview.** `/admin/design` shows the weekly grid but not the booking calendar, which
  reads live availability from the API.
- **Member accessibility audit.** The member audit still reports one failure on the Launch (Ventures) page,
  from the venture prefill added earlier by another contributor. It is not part of these changes and was left
  alone.

## Manual smoke test

1. Member: open **Contact support**, send a request with an attachment, see the reference and **View request**.
   Open **My support requests** and see it as Open.
2. Admin: open **Support**, assign it, reply, tick **Internal note** on a second message, then **Send and
   resolve**. Member: see the reply and the notification, then **Resolved**; reopen it.
3. Register choosing **A WO Community member**; the approvals drawer shows the referrer. Open a `/join?ref=`
   link and check the member is already chosen.
4. Press `/` on the member site and in the console. Search for a member, a course and (as admin) a ticket.
   Open a result with the keyboard. Open the bell, mark one read from the popover, then **View all**.
5. Admin: **Add course** with three YouTube links and a price; check that publishing is refused until a
   thumbnail is added. Member: ask for the paid course; admin approves it from **Enrolment requests**; the
   member sees **Continue learning**. Enrol in the free course, finish every lecture, and open the certificate:
   download the PDF, share the link, check `/verify/<number>` says Valid with no email address, turn on
   **Show on my profile** and look at the profile as another member.
6. Mentor: in **Settings > Mentorship** set a weekly schedule, a price and a day off; use **Preview as
   mentee**. Mentee: pick a length, a day and a time (check the zone), send the request; a second mentee
   choosing the same time is told it is gone. Try to remove a day that has an agreed session and check the
   mentor is shown the session and asked.
7. In dark mode, repeat a few of the above and check text and the unread dot are readable at 390 pixels.
