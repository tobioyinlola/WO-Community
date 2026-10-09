# 0009. Invitations

Status: accepted (Stage 1)

## Decisions

- **Token handling.** The link is made when the email is built and only its SHA-256 is stored, so
  the raw token exists in the email alone. Resending clears the hash, so the previous link stops
  working at once. Revoking or registering also clears it.
- **Exactly one email per request.** Each create or resend stamps the invitation with a fresh
  `send_nonce`, carried in the outbox event. The email task sends only if the nonce still matches
  and no link exists yet, so a resend before the first email goes out sends one email, and a retried
  event sends none. The link and the email are produced in one transaction: if sending fails, the
  link is rolled back and the retry starts over.
- **Who can be invited.** Roles `member` and `mentor` only; admin roles are never granted by
  invitation. A mentor invitation also grants the member role. An address that already has an
  account, or a live invitation, is refused with a clear code (`already_registered`,
  `already_invited`). An invitation past its expiry is superseded by a new one. The database
  enforces one live invitation per address (a partial unique index), so races cannot create two.
- **Statuses.** Stored: sent, opened, registered, revoked. `expired` is computed (unused and past
  its expiry, 7 days), so no job is needed to keep it correct.
- **Registering through an invitation.** The token must be live and issued to the same address
  (case-insensitive). The account is created active, email verified (receiving the link proves
  control of the mailbox), with `approval_source = invitation` and the inviter as approver, and the
  member gets the "approved" email. Consents and password rules still apply. A token that is
  expired, revoked, used, unknown or for another address is ignored as if none were sent, and the
  person goes through normal approval. If the address already has an account the response is the
  usual uniform 202, even with a valid token.
- **Response shape.** Registration answers 201 `{approved: true}` when an invitation applied and
  202 otherwise. Only someone holding a valid token can see the difference.
- **Bulk import.** JSON body with the CSV text (the API accepts JSON only), up to 500 rows and
  256 KB, columns `email`, `role`, `message`. A malformed file is rejected whole; bad rows are
  reported and skipped while valid rows are invited. Limited to 10 uploads per hour. Cell values are
  stored as plain text and never interpreted; any future CSV export must neutralise leading `=`,
  `+`, `-` and `@`.
- **Opened.** `POST /auth/invitations/inspect` returns the invited address, role and message so the
  registration page can prefill, and marks the invitation opened. It does not consume the link.

## Consequences

Admins see Sent, Opened, Registered and Expired as the requirements ask, plus Revoked. A link is
valid for one registration only.
