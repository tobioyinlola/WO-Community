# 0004. Authentication loads the user row on each request

Status: accepted (Stage 0), revisit if profiling shows a cost

## Context

The design says access tokens are verified without a database call. Policies also need the current
account status (pending, suspended, removed) and roles, and a suspended account must stop working
at once.

## Decision

`JWTAuthentication` verifies the signature and expiry locally, checks the cached minimum token
version, then loads the user by primary key (one indexed query). The token version in the claim must
equal the stored one, so a role change or suspension invalidates tokens even if the cache entry is
lost. Roles are read from the database when a policy needs them, not trusted from the claim.

## Consequences

One cheap query per authenticated request in exchange for immediate revocation and no stale roles.
If this shows up in profiles, cache the user record in Redis keyed by id and token version.
