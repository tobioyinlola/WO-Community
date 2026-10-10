# 0003. Case insensitive email uniqueness through a functional constraint

Status: accepted (Stage 0)

## Decision

`User.email` is unique through `UniqueConstraint(Lower("email"))`. Django's checks `auth.E003` and
`auth.W004` expect a plain unique column, so they are silenced in settings. The manager looks users
up with `email__iexact`, and `create_user` stores the lower cased address.

## Consequences

Registration cannot create `A@x.com` next to `a@x.com`, even under concurrent requests, because the
database enforces it.
