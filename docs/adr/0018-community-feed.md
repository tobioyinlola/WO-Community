# 0018. Community feed: posts, comments and reactions

Status: accepted (Stage 2, first slice)

## Decisions

- **A `feed` module** at the same level as `directory` and `memberarea`. It reads profile and startup
  data only through their selectors and services, and it publishes domain events that the
  notification centre will consume. Follows, reports and link previews are separate slices.
- **Members only.** Every endpoint needs an active member. Writing needs the `feed.post` permission.
  A post is never visible to visitors or pending accounts.
- **Rich text is cleaned on the server and the cleaned HTML is what we store** (`nh3` allow list).
  Posts may contain paragraphs, line breaks, bold, italic, bulleted and numbered lists, two heading
  levels, quotes and `http`/`https` links; comments allow only paragraphs, bold, italic and links.
  Everything else is removed, not escaped. Links get `rel="noopener nofollow ugc"`. The plain words
  are stored beside it (`body_text`) for length limits and later search. Limits are applied to the
  cleaned text: 3,000 characters for a post, 1,500 for a comment.
- **Images** are the existing upload pipeline with a new purpose, `post_image`: up to ten per post,
  each claimed once, re-encoded to WebP, with optional alt text. Editing sends the whole list, where
  an entry keeps an image (`image_id`) or adds one (`upload_id`), so order, removal and addition
  are one operation. Images dropped by an edit or by deleting the post are deleted from storage once
  the change commits. A failure anywhere leaves the post uncreated and the uploads unspent.
- **Counters are exact, not eventual.** The design suggests counters updated asynchronously. At the
  planned volume (about 9,000 posts and 60,000 comments or reactions a day) a locked row update in
  the same transaction is simple and always right, and avoids a drift-repair job. Reaction totals
  per kind live in a small JSON map on the row. Counter writes deliberately do not change
  `updated_at`, so a reaction never invalidates an author's ETag mid-edit. If a single post ever
  becomes hot enough to contend, counters move to a queue without changing the API.
- **Engagement order.** "Most engaged" sorts on reactions plus twice the comments, stored on the post
  and indexed.
- **Keyset pagination in both directions.** Cursors name the sort and scope they belong to and are
  rejected if tampered with or reused under another sort. Pinned posts are returned separately on the
  first page of the shared feed so they never repeat in the pages that follow.
- **Visibility.** A post exists for members only while it is not removed, its author is still an
  active member (so a suspension or removal takes their posts and comments down at once), and it is
  not hidden. A hidden post is still visible to its author, marked as hidden and not editable.
  Authors who hide their profile basics from members appear as "Community member".
- **Comments** are one level deep (a reply's parent is always a top-level comment). Deleting a
  comment removes its replies and corrects the post's count. Comments and reactions are refused on
  hidden or removed posts.
- **Reactions** follow the design: one row per member, target and kind, so a member can both like
  and celebrate. Adding the same one again changes nothing.
- **Moderation** (`feed.moderate`, community admin and above, MFA required): pin, unpin, feature,
  unfeature, hide, unhide and remove, each written to the audit log with an optional reason. Removal
  is a soft delete so content can be recovered.
- **Abuse limits.** A member may write 20 posts and 200 comments a day (settings). Feed reads are
  rate limited.
- **Mentions** are sent by the client as a list of member ids alongside the text (maximum ten). Only
  active members, other than the author, are notified. The feed publishes `MemberMentioned` and
  `CommentAdded` events into the outbox; nothing consumes them until the notification centre exists.
- **Analytics.** `post_created`, `comment_created` and `post_reacted` are recorded with categories
  only, never text.

## Consequences

The feed API is complete for reading and writing. Still to build in this area: follows and the
Following feed, reporting and the moderation queue, link preview cards (with their SSRF controls),
and delivery of the mention and comment notices through the notification centre.
