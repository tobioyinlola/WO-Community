# Change requests: plan

Written before any code, after reading the repository. For each change: what is already there, what
is added or changed, and the migrations and endpoints involved. Decisions taken along the way are
recorded in `docs/adr/` (0047 onward) and in the report at the end.

Conventions to follow (copied from the nearest examples): views are thin and declare a `policy`
(`apps/core/policies.py`); logic lives in services and selectors; roles and permissions are in
`apps/core/rbac.py` and mirrored in `frontend/src/admin/permissions.ts`; events go through the outbox
(`apps/core/outbox.py`) to handlers; third parties sit behind adapters in `apps/integrations`; lists
page with `{count, next, previous, results}` or a keyset cursor; every view carries OpenAPI
annotations and `docs/api/openapi.yaml` plus `frontend/src/api/schema.d.ts` are regenerated.

## What exists

| Area | State |
|---|---|
| Notifications | `Notification` (payload, `read_at`, dedupe key), keyset list with ETag and `unread_count`, mark read, preferences, email handlers. Front end: bell links to a page, no popover. |
| Search | `GET /search` (`apps/memberarea/search.py`) with searchers for members, startups, jobs, mentors, events, news, each applying visibility rules. No courses, no admin groups, no recents, no highlight. The top bar field is not wired to it. |
| Learning | `Course`, `Module`, `Lesson` (YouTube video id validated), `Enrolment`, `LessonProgress`, `CourseRating`, `Certificate` (code, holder name snapshot) and a PDF module. Authoring and learner endpoints exist. Missing: catalog filters, landing page, player tabs, Q and A, notes, wishlist, reviews text, announcements, access requests, prices with promotions, admin drawer wizard, learners and requests tabs. |
| Mentorship | `MentorProfile`, `AvailabilitySlot` (weekly and one off, exclusion constraints), `MentorSession`, calendar connection, booking. Missing: Settings section with the quick editor, session lengths and buffers as settings, time off, pricing, paid requests, preview as mentee. |
| Support | Nothing. Contact support is a `mailto:` link in the member layout. |
| Referrals | Nothing on the model. An analytics event name mentions it. |
| Shared UI | No right side drawer, popover or stepper in the member library. The admin console has a slide over (`ApprovalDrawer`) built on Radix dialog. |

## Order and scope per step

### 1. Shared pieces
- Front end: a shared `Drawer` (Radix dialog, right side, sizes, unsaved changes guard), `Popover`,
  `Stepper`, `Rating`, `ProgressRing`, `Accordion`, with a section on `/admin/design`.
- Notifications popover for the member and admin top bars; `GET /notifications/unread-count` (ETag),
  `POST /notifications/read-all`, `target_url` in the item. No migration (payload already carries
  ids; the URL is derived when read).
- Global search: extend `GET /search` with grouped output, highlight, courses, pages, recents
  (`SearchRecent` table, max 8 per user) and admin groups; wire the top bars, `/` and `Ctrl K`;
  `/search?q=` page. Trigram and `unaccent` already enabled by the directory migration.

### 2. Support tickets
New app `apps/support`: `SupportTicket`, `SupportMessage`, `SupportAttachment`,
`SupportCannedReply`. Permission `support.manage` for community admins and super admins. Member and
admin endpoints as in the brief. Notifications and email through existing handlers. Replace every
mailto and support address in code and docs.

### 3. Referrals
Fields on the registration record: `referral_source`, `referral_detail`, `referred_by`,
`referral_code_used`; `referral_code` on the user with a backfill migration. Endpoints for referrer
search, my referrals, admin summary and top referrers. Sign up form, approval drawer, members table
columns, admin dashboard card, member dashboard card.

### 4. Learning
Extend the `learning` app: course fields (subtitle, language, bullets, requirements, audience,
promo video, promotion prices, `enrolment_active`, unlisted status, learners count, duration),
`EnrolmentRequest`, `CourseReview` (text on the rating), `LectureQuestion`, `LectureAnswer`,
`LectureNote`, `CourseAnnouncement`, `WishlistItem`. Naming stays with the existing `Module` and
`Lesson` models rather than renaming to section and lecture (the API and UI say "section" and
"lecture"). Catalog, landing page, player, my learning, admin drawer wizard, management page.

### 5. Certificates
Extend `Certificate` (number format `WO-C-YYYY-NNNNNN`, hours, revoked_at, pdf key) and add
`CertificateSettings`. HTML template rendered to PDF, public verification page, admin template
preview.

### 6. Mentor settings
`MentorSettings`, `MentorSessionPrice`, exceptions (blocked or extra dates), Settings section,
preview as mentee, paid session requests while payments are off. Reuses `AvailabilitySlot` for the
weekly ranges and the existing booking exclusion constraint.

### 7. Seed, end to end tests, screenshots, report.

## Decisions to record
- 0047 Learning keeps `Module` and `Lesson` as the storage names.
- 0048 Paid courses and paid mentor sessions are requests while payments are off.
- 0049 Support is in app only; no reply by email.
- 0050 Search ranking and visibility.
