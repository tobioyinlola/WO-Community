# 0008. Admin MFA design

Status: accepted (Stage 1)

## Decisions

- **TOTP only** (RFC 6238, 30 second steps, 6 digits) plus one-time recovery codes. Enrolment is
  offered to, and required of, accounts holding an admin role. Members are not asked.
- **Secrets are encrypted at rest** with Fernet keys from `FIELD_ENCRYPTION_KEYS` (several keys
  allowed so a key can be rotated; see `apps/core/crypto.py`). Production refuses to start without
  them. This is a single-layer application key, not the per-record envelope encryption with a KMS
  that the design describes; swapping the key source for a KMS-wrapped data key later does not
  change the model or the callers.
- **No code is accepted twice.** The highest time step used is stored per device, so a captured
  code is useless inside its 30 second window. One step either side of the clock is tolerated.
- **Two step login.** A correct password for an account with MFA returns 202 and a signed
  `mfa_token` (5 minutes, single use once redeemed). No session exists until a code is accepted.
  A typo does not burn the challenge.
- **Lockout.** Five wrong codes in 10 minutes block all further code checks for that account
  (429), whatever the endpoint, so the second factor cannot be brute-forced.
- **MFA state belongs to the session.** Each refresh-token family stores `mfa_verified_at`, and
  every access token carries it as `mfa_at` plus the session id as `sid`. Refreshing keeps the
  original timestamp, so it never makes an old check look new. Admin permissions need an MFA check
  within 12 hours; destructive actions need one within 10 minutes (ADR 0007).
- **Step-up** (`POST /auth/mfa/step-up`) re-checks a code against the live session and returns a
  token with a fresh claim; the new timestamp is also written to the session.
- **Recovery codes:** 10 per set, 48 bits each, stored as SHA-256 hashes, each usable once. A
  recovery code cannot authorise generating a new set.
- **Lost authenticator:** a super admin resets it (`POST /admin/members/{id}/reset-mfa`, step-up
  required). The device and codes are deleted, sessions end, and the admin enrols again at next
  login. Nobody can reset their own.
- **Admins who have not enrolled** can log in (the response says `mfa_enrolment_required`), but
  every admin endpoint answers 403 `mfa_required` until they enrol and confirm.

## Consequences

If the last super admin loses their device, the only route back is an operator removing the device
row directly; keep at least two super admins. Recovery codes shown at enrolment are never
retrievable again.
