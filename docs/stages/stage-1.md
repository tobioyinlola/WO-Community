# Stage 1: Identity, profiles, directory (in progress)

## Slice 1: authentication (done)

- **Registration** `POST /api/v1/auth/register`: email, password and the three required consents
  (terms, privacy, conduct) plus optional marketing consent. Consents are stored as versioned
  history. Always answers 202. A repeat registration emails the existing owner instead and is
  indistinguishable to the caller in content and in timing.
- **Email verification** `POST /auth/verify-email`: single use, 24 hour tokens, stored hashed.
- **Login** `POST /auth/login`: short lived access token in the body, refresh token in an HttpOnly
  `SameSite=Lax` cookie scoped to `/api/v1/auth/`. Requires a verified email. Pending accounts can
  log in and see their status, but policies keep them out of member-only areas.
- **Refresh and logout**: rotation on every use, reuse detection, 30 day sliding and 90 day
  absolute lifetime (ADR 0006). Both need an `X-Requested-With` header.
- **Lockout**: 5 failed attempts per account or 30 per address in 10 minutes returns 429.
  Failures are counted per hashed address, so no raw emails are kept in the cache or audit log.
- **Password reset** `POST /auth/password/forgot` and `/auth/password/reset`: always 202, three
  emails per address per hour, 1 hour tokens, and a successful reset revokes every session and
  access token.
- **Sessions** `GET /me/sessions`, `DELETE /me/sessions/{id}`: scoped to the caller; another
  member's session returns 404.
- **Audit**: registration, verification, login, failed login, reset and refresh reuse are recorded.
- **Emails** are composed in `notifications` from outbox events (ADR 0005).

126 tests pass; all gates are clean.

## Slice 2: breached-password check (done)

- `apps/integrations/passwords`: a `BreachChecker` adapter with a fake and a Have I Been Pwned
  implementation. Only the first five characters of the SHA-1 leave the process, with response
  padding. It fails open on timeouts or errors so a provider outage cannot block sign-ups.
- Wired in as a Django password validator, so registration and password reset both enforce it.
  Local and test settings use the fake; other environments default to the real lookup
  (`PASSWORD_BREACH_CHECKER`).
- Outbound traffic to `api.pwnedpasswords.com` must be on the egress allow list.

## Slice 3: admin approval and member management (done)

New module `adminconsole` (the admin API layer) calling `accounts` through its services.

| Endpoint | Permission | Step-up |
|---|---|---|
| `GET /admin/members`, `GET /admin/members/{id}`, `GET /admin/queues` | `members.view` | no |
| `POST /admin/members/{id}/approve`, `/reject` | `members.approve` | no |
| `POST /admin/members/{id}/suspend`, `/reinstate` | `members.suspend` | yes |
| `POST /admin/members/{id}/remove` | `members.remove` | yes |

- Filters on the list (allow-listed): search, status, role, email verified, joined before or
  after; offset pagination capped at 100; no per-row queries.
- Approval and rejection email the member (the rejection includes the reason). Suspension and
  removal end sessions and tokens immediately and are audited with before and after status.
- Rules and the MFA policy are in ADR 0007. These endpoints require an `mfa_at` claim, which the
  MFA flow (slice 4) issues.
- Differs from the catalogue: member status changes are action sub-resources
  (`/approve`, `/suspend`, ...) instead of `PATCH /admin/members/{id}/status`, as the API
  conventions allow for non-CRUD actions.

211 tests pass; all gates are clean.

## Slice 4: admin MFA (done)

Design and trade-offs are in ADR 0008.

- `POST /auth/mfa/enrol` and `/auth/mfa/confirm`: admin accounts set up an authenticator and get
  10 one-time recovery codes. Confirming also marks the current session as MFA-verified.
- `POST /auth/login` returns 202 with an `mfa_token` for accounts with MFA; `POST /auth/mfa/verify`
  finishes the login with a TOTP or recovery code.
- `POST /auth/mfa/step-up`: fresh check for destructive actions. `POST /auth/mfa/recovery-codes`:
  replace the recovery codes.
- `POST /admin/members/{id}/reset-mfa` (super admin, step-up): for a lost authenticator.
- TOTP secrets are encrypted at rest (`FIELD_ENCRYPTION_KEYS`); codes cannot be replayed;
  five wrong codes lock code checks for 10 minutes.
- Access tokens now carry `sid` and, after MFA, `mfa_at`. The admin endpoints from slice 3 are
  now usable end to end.

276 tests pass; all gates are clean.

## Slice 5: invitations (done)

Design and trade-offs are in ADR 0009. All admin endpoints need `invitations.manage` and an MFA
session.

| Endpoint | What it does |
|---|---|
| `POST /admin/invitations` | Invite one person (`email`, optional `role` member or mentor, optional `message`). |
| `POST /admin/invitations/bulk` | Invite many from CSV text; bad rows are reported and skipped. |
| `GET /admin/invitations`, `GET /admin/invitations/{id}` | List with `status` (sent, opened, registered, revoked, expired) and search filters; detail. |
| `POST /admin/invitations/{id}/resend` | New link and expiry; the old link stops working. |
| `POST /admin/invitations/{id}/revoke` | Kill the link. |
| `POST /auth/invitations/inspect` | Public: look up a link to prefill the registration page; marks it opened. |
| `POST /auth/register` with `invitation_token` | Matching address: account is active at once (201 `approved: true`). Otherwise the normal pending flow (202). |

- Only token hashes are stored; exactly one email goes out per create or resend, and a failed send
  leaves no link behind.
- One live invitation per address is enforced by the database.
- Registering through an invitation records `approval_source = invitation` and audits it, and
  sends the "approved" email.

366 tests pass; all gates are clean.

## Slice 6: profiles, startups and visibility (done)

Design and trade-offs are in ADR 0010.

**Registration** now requires the details from the form: `profile` (`full_name`, `country`,
`city`) and `startup` (`name`, `country`, `city`, `sector`, `stage`, `pitch`). They are validated
at the door (ISO country, listed sector and stage, markup stripped) and turned into a founder
profile and a startup by event handlers, for both normal and invited sign-ups.

| Endpoint | What it does |
|---|---|
| `GET/PATCH /me/profile` | Your profile with visibility levels, badges, completeness and next missing field. PATCH needs `If-Match`. |
| `GET/PATCH /me/visibility` | Level (private, members, public) of each profile group. |
| `GET /members/{user_id}` | Another member's profile, only the groups they share with members. 404 if they hide the basics. |
| `POST /startups`, `GET /me/startups` | Create a startup (you become its owner and founder); list the ones you are on. |
| `GET/PATCH /startups/{id}` | Read as the viewer may see it; update (owner or founder; `If-Match`). `directory_opt_in` is owner only. |
| `PATCH /startups/{id}/visibility` | Level of each startup group (basics, description, website, team). |
| `PUT /startups/{id}/traction` | Replace the traction list; every entry has its own level. |
| `POST /startups/{id}/team`, `DELETE .../team/{member_id}` | Add by email (same answer either way) or remove. |
| `GET /reference/sectors`, `/stages`, `/skills`, `/countries` | Public, cacheable lists. |

- AC-17 is enforced by one rule in `core` and tested exhaustively: every field group at every
  level for every kind of viewer, over HTTP for members and at the selector for visitors.
- Completeness scores (profile and startup) name the next field to fill.
- Profile and startup edits publish events that the directory slice will consume.
- Plain-text cleaning, https-only links, bands for revenue and funding.

744 tests pass; all gates are clean.

## Slice 7: the public directory (done)

Design and trade-offs are in ADR 0011. Everything under `/public` is anonymous, cookie-free and
cacheable (`Cache-Control` with five minute life, ETag, `304` on `If-None-Match`).

| Endpoint | What it does |
|---|---|
| `GET /public/startups` | Browse and search listed startups. Filters: `q`, `country`, `sector`, `stage`, `skills` (comma list, all must match), `featured`; `sort` newest or alphabetical (featured always first); `limit` up to 50; `cursor`. |
| `GET /public/startups/{slug}` | Startup page: pitch, public description, website, public traction, founders, JSON-LD. |
| `GET /public/founders`, `GET /public/founders/{slug}` | Founders who made their basics public: only the groups they made public, their listed startups, JSON-LD. |
| `GET /public/sitemap` | Every public page with its last change, for `sitemap.xml`. |
| `POST /admin/startups/{id}/feature`, `/unfeature` | Pin a listed startup to the top (admin, MFA, audited). |

- A read model (`PublicStartup`, `PublicFounder`) is rebuilt from events when a profile, startup,
  approval, suspension or removal changes; an hourly job and `manage.py rebuild_directory` repair
  drift. Normal lag is seconds; the requirement is five minutes.
- Suspended or removed members vanish on the next request (read-time status check), not after the
  refresh. The CDN purge adapter is called on every change (a no-op logger until a CDN exists).
- Search: full text plus partial-word and typo matching on names; quotes and `-term` use exact
  rules. Hostile input is plain text. Private data is not in the index, so it cannot be found.
- Browsing uses keyset cursors (stable while new startups arrive); a search returns its best
  matches only.
- Extensions `pg_trgm` and `unaccent` are created by the first directory migration, so the
  migration user needs permission to create them.

Tests: 119 for the directory (access, caching, filters, ordering and paging, search, privacy,
takedown, refresh, sitemap, featuring, rebuild).

## Slice 8: uploads, profile photos and startup logos (done)

Design and trade-offs are in ADR 0012.

| Endpoint | What it does |
|---|---|
| `POST /uploads` | Reserve an upload (purpose `profile_photo` or `startup_logo`, type, size). Returns a pre-signed form: the file goes straight to storage. |
| `POST /uploads/{id}/complete` | Say the file is there; the checks are queued. Safe to repeat. |
| `GET /uploads/{id}` | Owner-only status; image addresses appear only when `ready`. |
| `PUT/DELETE /me/profile/photo` | Attach a ready upload as your photo, or remove it (`If-Match`). |
| `PUT/DELETE /startups/{id}/logo` | The same for a startup (owner or founder, `If-Match`). |

- JPEG, PNG or WebP up to 5 MB. A worker verifies the real type, scans for malware, rejects absurd
  dimensions and decompression bombs, applies the orientation, and re-encodes to WebP at 1600 and
  320 pixels. Metadata and anything hidden in the file do not survive.
- Failure is closed: if the scanner is unreachable the upload waits and retries, and is never
  published unscanned. Malware detections are audited.
- Photos and logos are part of the basics group, so they follow its visibility and now appear on
  directory cards and pages. Replacing or removing an image deletes its files.
- Completeness gained a photo (15) and a logo (10) component.
- New settings: `STORAGE_ADAPTER`, `MALWARE_SCANNER`, `MEDIA_BASE_URL`, bucket names, S3 credentials
  and `CLAMD_HOST/PORT`. Production refuses to start on the in-memory fakes. A ClamAV container is in
  `docker-compose.yml` under the optional `scanner` profile.

863 tests passed before this slice; the uploads slice added about 160 more. All gates are clean.

## Slice 9: Resend email (done)

Design and trade-offs are in ADR 0013.

- `ResendEmailAdapter` sends through Resend's API with separate transactional and marketing senders,
  a content-based idempotency key on every message, and failures sorted into drop (never
  acceptable), retry (rate limit, outage, timeout) and alert (bad key or unverified domain).
- `POST /webhooks/email/resend` receives delivery reports: Svix signature over the exact bytes,
  five minute replay window, repeat deliveries ignored, stored raw and processed by a worker.
- Delivery outcomes are recorded with hashed addresses; permanent bounces and complaints go on the
  suppression list that marketing sends will check. Raw deliveries are purged after 30 days.
- Every email now carries a category (verification, password_reset, invitation, approved, ...) for
  tracking in Resend.
- Settings: `EMAIL_ADAPTER`, `RESEND_API_KEY`, `RESEND_WEBHOOK_SECRET`, `EMAIL_FROM_TRANSACTIONAL`,
  `EMAIL_FROM_MARKETING`, `EMAIL_REPLY_TO`. Production refuses to start with Resend selected and
  any of these missing.
- Setup steps (domain records, webhook, API key) are in the runbook.

## Slice 10: admin editing of the reference lists (done)

Design and trade-offs are in ADR 0014.

| Endpoint | What it does |
|---|---|
| `GET /admin/reference/{sectors,stages,skills}` | Every entry, retired ones included, with how many records use it. |
| `POST /admin/reference/{kind}` | Add an entry (slug made from the name unless given; can never change afterwards). |
| `PATCH /admin/reference/{kind}/{id}` | Rename, retire or restore, or reposition. |
| `DELETE /admin/reference/{kind}/{id}` | Delete an entry nobody uses (409 if in use: retire it instead). |
| `PUT /admin/reference/{kind}/order` | Set the display order (send every id once). |

- Needs the `reference.manage` permission (community admin and above) and an MFA session.
- Retiring hides an entry from new choices; records that use it keep it and stay editable. This also
  fixed a bug where changing a startup's stage failed once its current sector had been retired.
- Names are unique ignoring case (service and database); every change is audited with before and after.
- A rename rebuilds only the directory pages that show the entry and purges the cached public list.
- Countries stay in code (fixed by ISO 3166); post and course categories will reuse this service.

## Slice 11: product analytics (done)

Design and trade-offs are in ADR 0015.

| Endpoint | What it does |
|---|---|
| `POST /analytics/events` | Browser events in batches of up to 50; invalid ones are reported one by one, valid ones kept. Works signed in or out. |
| `GET/PUT /me/analytics-preferences` | Opt out of analytics entirely, or rejoin. |
| `POST /auth/register` with `anonymous_id` | Links the visitor id to the new member so the funnel is continuous. |

- Every event is defined in a registry with its allowed properties: numbers, flags, fixed words or
  short identifiers, never free text. The browser may report only page-level events; everything about
  actions the server performs is recorded by the server.
- Server events now recorded: `email_verified`, `member_approved` (with source and hours waited),
  `member_rejected`, `member_suspended`, `member_removed`, `invitation_sent`,
  `invitation_registered`, `profile_updated` (with the new completeness).
- Recording happens inside the action's transaction and can never fail it.
- Events are stored in a month-partitioned append-only table and forwarded in order, at least once,
  to a pluggable sink (`ANALYTICS_SINK`; logging only until a tool is chosen).
- Dashboards, summary tables and marketing tags are not built yet; the requirements put them with
  the admin dashboard and campaigns.

## Slice 12: Google sign-in (done)

Design and trade-offs are in ADR 0016.

| Endpoint | What it does |
|---|---|
| `POST /auth/google` | Sign in, or start a sign-up, with a Google ID token. Answers 200 (signed in), 201 (new account), 202 (MFA step needed), 409 `registration_required` (new person, send sign-up details), 401 (bad token or unusable account), 403 (Google address unverified), 404 (not configured), 503 (Google unreachable). |

- Existing members are recognised by address the first time and by Google's stable id afterwards.
- A link to an account whose address was never confirmed discards its password and ends its sessions.
- New people go through the same consents, details and admin approval as a password sign-up; a valid
  invitation approves them at once.
- MFA still applies; Google is never a second factor.
- Off until `GOOGLE_CLIENT_ID` is set; production refuses the fake verifier.

## Slice 13: onboarding checklist, notification preferences and member search (done)

Design and trade-offs are in ADR 0017.

| Endpoint | What it does |
|---|---|
| `GET /me/onboarding` | The four-step checklist (profile, startup, traction, notification preferences) and the profile score. Records `onboarding_completed` once. |
| `GET/PUT /me/notification-preferences` | Type by channel matrix; send only what changes. |
| `GET /search?q=&types=&limit=` | Members and startups, as the searcher may see them, tolerant of typos. |

- Search matches only visible fields and drops anyone who hides their basics or is not active.
- Approval emails cannot be switched off; the newsletter starts off.
- Jobs, courses, posts, mentors and events join search as their modules are built, as does the
  personalised member home summary.

## Still to do in Stage 1

1. A real CDN purger. The provider is undecided; the choice was deferred by the team and must be
   revisited before Stage 2 ends and before any deployment.

## Notes

- Keep at least two super admins: recovering the last one means editing the database.
- `FIELD_ENCRYPTION_KEYS` must be set in every real environment (production refuses to start
  without it). Generate with
  `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
- Rejected registrations should be purged after 90 days; the retention job arrives with hardening.
- Suspension and removal do not email the member yet (only approval and rejection do).
- Idempotency-Key storage is still not needed; it arrives with the first booking or enrolment flow.
