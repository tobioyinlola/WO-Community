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

## Still to do in Stage 1

1. Admin approval of registrations and the pending queue; member management (approve, reject with
   reason, suspend, reinstate, remove).
2. Invitations (single and bulk) that approve on registration.
3. Admin MFA (TOTP and recovery codes) and step-up for destructive actions.
4. Profiles and startups with per-field visibility; registration capturing name, location and
   startup details (these need the profile models, so they land with that slice).
5. Public directory read model, search, filters, featured items, caching, sitemap feed.
6. Real transactional email adapter (provider still undecided), analytics capture and events.
7. Google sign-in (proposed to follow once email and password login is settled).

## Notes

- The password check uses Django's validators (length 10, common passwords, similarity). A
  breached-password lookup is not wired yet.
- Idempotency-Key storage is still not needed; it arrives with the first booking or enrolment flow.
