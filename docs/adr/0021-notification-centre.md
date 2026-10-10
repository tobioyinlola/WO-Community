# 0021. The notification centre

Status: accepted (Stage 2)

## Decisions

- **One function, `notify(user_id, type, payload, dedupe_key)`,** is the only way a module tells a
  member something. It checks the member's preference for each channel, writes the in-app
  notification and sends the email if wanted. Nothing is sent to the person who caused the event,
  to anyone who is not an active member, or twice for the same `dedupe_key`.
- **Layering.** `notifications` sits below `feed`, so it cannot know about feed events. The feed
  subscribes to its own events (`MemberMentioned`, `CommentAdded`, `ReportHandled`) with small tasks
  that call `notify`. Account events (approval) are handled inside `notifications` as before.
- **Idempotent delivery.** Each handler passes the outbox event id as the dedupe key, and the table
  has a partial unique index on (member, key). A redelivered event, or two workers racing, cannot
  notify twice.
- **Wording is not stored.** A notification holds a type and a payload of ids. Titles and links are
  produced when it is read or emailed, so text can improve without a data fix and a person who later
  hides their profile is never named. Names are resolved as the recipient may see them; someone
  hidden from the recipient appears as "Community member".
- **Types today:** comment on your post, reply to your comment, mention, registration approved, and
  the outcome of a report you filed (told "removed or hid" or "reviewed, no action", never more).
  Registration rejection stays email only, because a rejected person cannot log in. Admin queues are
  counts (`GET /admin/queues`), not notifications.
- **Preferences** decide each channel per type (comments, mentions, approvals, moderation, and the
  rest). Approval email cannot be switched off. Comment, reply and mention emails are capped at ten
  an hour per member and kind, because other members can trigger them; the in-app notification is
  still created.
- **Polling, not push.** `GET /notifications` is meant to be called about every 30 seconds with
  `If-None-Match`. The ETag is a hash of the member's notification count, unread count and last
  change plus the query, from one aggregate over their own rows; an unchanged list answers 304 with
  no body. `POST /notifications/read` marks given ids (up to 100) or everything; ids that are not the
  caller's are ignored.
- **Retention.** A daily job deletes read notifications after 90 days and any after 180.

## Deviation from the design, and why

The design lists notifications among tables to partition by time from the first migration. This
table is updated (read marks) and is purged by age after at most 180 days, so a plain table with the
(member, created) indexes and the daily purge is simpler and enough at the expected volume. If
volume proves otherwise, partitioning by month can be added with the same approach used for the
audit log and analytics events.

## Consequences

Email notices are plain text. Digest emails, notices for jobs, events and mentorship, and admin
notices by email arrive with those modules. The mention and comment notices queued in the feed
slices are now delivered.
