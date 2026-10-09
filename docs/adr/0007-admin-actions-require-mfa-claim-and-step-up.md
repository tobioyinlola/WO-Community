# 0007. Admin actions require an MFA claim, destructive ones a recent one

Status: accepted (Stage 1)

## Decision

- Access tokens may carry `mfa_at`, the time the session last passed an MFA check. Only the MFA
  flow (a later Stage 1 slice) issues it.
- `policies.admin_permission(code)` requires the permission, an admin role, and an `mfa_at` claim.
  With `step_up=True` the claim must also be newer than `STEP_UP_MAX_AGE_SECONDS` (10 minutes).
  Suspending, reinstating and removing members use step-up; viewing, approving and rejecting do not.
- Missing MFA answers 403 `mfa_required`; a stale check answers 403 `step_up_required`. These are
  raised only after the permission check passes, so a caller without the permission sees a plain
  `permission_denied` and learns nothing about how admin access works.
- Policies receive the token claims as well as the user (`policy(user, claims)`).

## Member standing rules (`accounts.membership`)

- States: pending, active, suspended, removed, rejected. Allowed moves are explicit; anything else
  is 409 `invalid_transition`.
- Approval needs a verified email. Approval grants the `member` role. Rejection, suspension and
  removal need a reason and end every session and access token at once.
- Nobody can act on their own account, and only a super admin (permission `roles.manage`) can
  change an account that holds an admin role.
- Each command locks the target row, so two admins acting at once cannot both succeed.

## Consequences

The MFA flow that issues `mfa_at` is described in ADR 0008. Without it the admin endpoints fail
closed rather than run without MFA.
