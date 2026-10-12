# 0049. Support conversations happen in the app; a member is told by email but does not reply by email

Status: accepted

## Context

Support used to be a `mailto:` link. Replying by email needs inbound mail handling: parsing quoted
text and signatures, matching a message to a ticket, rejecting forged senders, scanning attachments and
keeping private notes out of the thread. None of that exists, and each piece is a place where a
person's message can be lost or mis-filed.

## Decision

- A request is opened and answered in the app. The thread, the status, the attachments and the
  internal notes live in `SupportTicket`, `SupportMessage` and `SupportAttachment`.
- Members are told in the app and by email when the team replies or resolves a request. The email
  carries the first words of the reply and a link to the request. It says not to reply to it.
- Administrators are told in the app only, so a busy inbox does not become a second place to work.
- A visitor with no account can send one request through the public form. They receive an
  acknowledgement, and the team writes back from the team address by hand. Their request has no thread
  in the app.
- Attachments go through the upload pipeline (type and size limits, private storage, short-lived
  download links). At most three files of 5 MB each.
- The response-time target is a setting (`sla_hours`) and only drives a visible "overdue" flag.

## Consequences

- No inbound mail to secure. A forged message cannot be added to someone's thread.
- A member who prefers email still gets the answer in their inbox but must open the app to continue
  the conversation. Replying to the notification is the single behaviour people may expect and will
  not get; the email says so plainly.
- If inbound mail is wanted later it can be added as another way to create a `SupportMessage` without
  changing the model.
