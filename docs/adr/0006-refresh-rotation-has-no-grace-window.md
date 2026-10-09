# 0006. Refresh token rotation has no grace window

Status: accepted (Stage 1)

## Decision

Each refresh token is valid exactly once. Presenting any token other than the current one revokes the
whole session family and is audited (`auth.refresh_reuse_detected`). The family row is locked while
rotating, so two simultaneous refreshes cannot both succeed.

## Consequences

A client that sends two refresh calls at once will lose its session: the second call replays a
rotated token. The front end must serialise refreshes (one in flight at a time, shared by all
requests waiting on a new access token). A short grace window would hide that bug at the cost of
weakening theft detection; revisit only if it causes real logouts.

Refresh endpoints also require an `X-Requested-With` header, which a cross-site form post cannot
send, in addition to the `SameSite=Lax` cookie scoped to `/api/v1/auth/`.
