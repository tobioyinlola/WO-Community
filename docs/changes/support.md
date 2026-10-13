# Support tickets

Contact support is a request inside the product. There is no support email address anywhere.

**Members.** "Contact support" (sidebar, account menu, the waiting for approval page) opens a right
side drawer: category, subject (5 to 120), message (20 to 4000), up to three files (PDF or image,
5 MB each, scanned and kept privately). Sending shows the reference (SUP-1042) and a link. "My
support requests" (`/app/support`) lists them with a status chip (Open, In progress, Awaiting your
reply, Resolved); a request page shows the conversation, a reply box, and for 14 days after
resolution a Reopen button and a thumbs up or down. People who cannot sign in use `/help`, which is
throttled, has a hidden field for bots, and is answered by email.

**Admins** (permission `support.manage`: community admin and super admin). `/admin/support` is the
inbox: figures, tabs with counts, filters (search by number, subject, name or email; category;
assignee; priority), a sortable table, and the request in a drawer with J and K to move. In the
drawer: change status, assignee, priority and category; reply with light formatting, insert a saved
reply, attach files; tick "Internal note" to leave a note members never see; Send reply, Send and
resolve, Resolve, Reopen. Saved replies are managed at `/admin/support/replies`. The dashboard lists
requests nobody answered within `SUPPORT_SLA_HOURS` (24 by default) under "Needs your attention".

**Notifications.** Members hear about a reply or a resolution in the app and by email; the email
carries the reply and a link, never invites a reply by email, and is sent with no Reply-To even if
`EMAIL_REPLY_TO` is set. Admins hear in the app about new requests and member replies (the assignee
for replies).

**API.** Member: `/support/tickets` (list, create with an `Idempotency-Key`), `/support/tickets/{id}`
and its `messages`, `reopen`, `feedback`; `/support/attachments/{id}/download`; public
`/support/contact`. Admin: `/admin/support/tickets` (filters, counts, pagination), `{id}`, `messages`,
`resolve`, `reopen`; `stats`, `agents`, `canned-replies`, `attachments/{id}/download`.
Status and assignee changes are written to the audit log.

**Decisions.** Ticket numbers come from a database sequence starting at 1001. A message is stored as
cleaned HTML plus its plain words. A member's reply to a request support has answered puts it back to
In progress; a reply to one nobody has answered leaves it Open. A resolved request cannot be replied
to until it is reopened.
