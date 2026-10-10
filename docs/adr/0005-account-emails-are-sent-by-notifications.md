# 0005. Account emails are sent by `notifications`, not `accounts`

Status: accepted (Stage 1)

## Context

`accounts` (level 1) must trigger verification and password reset emails, but it cannot depend on
`integrations` (same level) or `notifications` (level 3).

## Decision

`accounts` publishes domain events (`UserRegistered`, `RegistrationRepeated`,
`PasswordResetRequested`) through the outbox. `notifications` subscribes, and its tasks call two
public `accounts` services: `issue_email_token` and `get_contact`. The raw token is created inside
the handler, emailed once and never stored; the outbox payload carries only the user id, so tokens
never sit in the outbox table or the broker.

## Consequences

If a handler is retried it issues a second token and sends a second email. That is acceptable for
verification and reset links, which are single use and short lived. Email composing stays in one
module, which is where the rest of the platform's notification logic will live.
