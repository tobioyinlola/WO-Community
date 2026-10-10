# Stage 2: Engagement

Scope from the brief: feed, comments, reactions, follows, reports and moderation, jobs and
opportunities with expiry and alerts, editorial and win submissions, events and demo days,
notification centre and preferences, campaigns and segments, admin queues.

## Slice 1: posts, comments, reactions and moderation (done)

Design and trade-offs are in ADR 0018.

| Endpoint | What it does |
|---|---|
| `GET /posts` | The feed. `sort` (newest, engaged), `scope` (all, mine), `category`, `country`, `cursor`, `limit`. Pinned posts come separately on the first page. |
| `POST /posts` | Write a post: category, rich text, up to 10 images, optional startup, mentions. 20 a day. |
| `GET/PATCH/DELETE /posts/{id}` | Read, edit (ETag and If-Match) or delete your own post. |
| `GET/POST /posts/{id}/comments` | Comments oldest first with replies; comment or reply. 200 a day. |
| `PATCH/DELETE /comments/{id}` | Edit or delete your own comment. |
| `POST /posts/{id}/reactions`, `DELETE /posts/{id}/reactions/{kind}` | Like, celebrate or insightful. Same for `/comments/{id}/reactions`. |
| `POST /admin/posts/{id}/{pin,unpin,feature,unfeature,hide,unhide,remove}` | Moderation; audited. |

## Slice 2: follows and the Following feed (done)

Design and trade-offs are in ADR 0019.

| Endpoint | What it does |
|---|---|
| `POST /follows` | Follow a member or a startup (`{type, id}`). Idempotent. Up to 500. |
| `DELETE /follows/{member\|startup}/{id}` | Unfollow. Idempotent. |
| `GET /me/following` | Who you follow, newest first, optionally one type. |
| `GET /posts?scope=following` | Posts by people you follow, and posts made for startups you follow. |

Post and comment authors, and the startup on a post, now carry a `following` flag.

## Still to do in Stage 2

1. Reports, the moderation queue (Open, Reviewed, Actioned) and moderation of comments.
2. Link preview cards with SSRF protection.
3. Notification centre and delivery of mention and comment notices.
4. Jobs and opportunities, news and win submissions, events and demo days, campaigns and segments,
   admin queues.
5. The CDN purger (provider decision still pending; revisit before Stage 2 ends).
