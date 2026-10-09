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

## Still to do in Stage 1

1. Public directory read model, search, filters, featured items, caching, sitemap feed (uses the
   visibility rule above with the public audience).
2. Photo and logo uploads (pre-signed URLs, scan) so those fields can be set.
3. Admin management of reference lists (the lists are seeded and read-only for now).
4. Real transactional email adapter (provider still undecided), analytics capture and events.
5. Google sign-in (proposed to follow once email and password login is settled).

## Notes

- Keep at least two super admins: recovering the last one means editing the database.
- `FIELD_ENCRYPTION_KEYS` must be set in every real environment (production refuses to start
  without it). Generate with
  `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
- Rejected registrations should be purged after 90 days; the retention job arrives with hardening.
- Suspension and removal do not email the member yet (only approval and rejection do).
- Idempotency-Key storage is still not needed; it arrives with the first booking or enrolment flow.
