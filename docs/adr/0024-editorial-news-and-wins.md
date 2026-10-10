# 0024. Editorial: news, awards, partnerships, banners and win submissions

Status: accepted (Stage 2)

## Decisions

- **Item types** are those in the requirements: award, celebration, partnership, funding, news and
  announcement. An item has a title, rich text body (the same allow list as posts), optional cover,
  optional external https link, up to five linked startups and a flag for comments.
- **Who writes:** content editors and above (`editorial.manage`), with a recent MFA check. Every
  create, edit, publish, schedule, unpublish, removal and comment moderation is audited.
- **Lifecycle:** draft, scheduled, published, removed. Publishing is an explicit action. Scheduling
  sets a future `publish_at`; a worker (every minute) publishes due items and stamps them with the
  scheduled time rather than the time the worker ran, so the date shown is the one the editor chose.
  Unpublishing returns an item to draft and also cancels a schedule. Removal hides it from everywhere
  and keeps the row. Edits use ETag and If-Match. Counters (reactions, comments) do not change the
  ETag, so an editor is not blocked by members reacting.
- **Linked startups** are shown to a viewer only if that startup's basics are visible to them, so
  linking a startup that hides itself leaks nothing. Public pages show only publicly visible ones.
- **Public website.** An editor marks an item `public`; only published public items appear in
  `GET /public/news` and `/public/news/{slug}`, which are cacheable with ETags, carry Open Graph
  data and a share link, and never include comments, reactions or any member details. Publishing,
  editing, unpublishing and removal purge the CDN paths through the adapter.
- **Comments and reactions on items.** Members can react (like, celebrate, insightful) and comment
  (flat, 1,500 characters, 100 a day) on published items. An editor can switch comments off per item
  (existing comments stay visible, new ones get 409) and can hide, unhide or remove any comment, with
  the count recalculated from what readers can see. Feed posts and editorial items are different
  tables because the modules cannot depend on each other, so this repeats a little logic rather than
  coupling them.
- **Banners.** Only announcements can be pinned. They need an end time, may have a start time, and
  can run for at most 90 days. `GET /banners` returns announcements whose window is open now, soonest
  to end first, at most five.
- **Win submissions.** A member submits an award, funding or partnership with an https evidence link,
  optional details and optionally one of their own startups. At most three can wait at once and five
  can be sent a day. Editors approve or reject; rejecting needs a reason. Approving does not publish
  anything: it creates a **draft** story pre-filled from the submission (linked on the submission) for
  an editor to polish and publish. The member is told the outcome by notification and email, with the
  reason on rejection.
- **Counts.** `GET /admin/queues` now includes `wins_awaiting_review`.

## Consequences

Members cannot yet report an editorial comment; moderators remove them directly. Notifying members
when something is published, a news digest and a "following" view of news are not built.
Editorial items are not in member search. The public news pages are separate from the directory's
sitemap, as with jobs, for the same layering reason.
