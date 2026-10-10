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

## Slice 3: reports and the moderation queue (done)

Design and trade-offs are in ADR 0020.

| Endpoint | What it does |
|---|---|
| `POST /posts/{id}/reports`, `POST /comments/{id}/reports` | Report with a reason (spam, harassment, misinformation, illegal, inappropriate, other) and optional details. Once per member per item; 20 a day. |
| `GET /admin/reports` | The queue, oldest first. Filters: `status` (default open), `target_type`, `reason`. Offset paging. |
| `GET /admin/reports/{id}` | One report with a look at the content. |
| `POST /admin/reports/{id}/review` | Mark reviewed, no action needed. |
| `POST /admin/reports/{id}/action` | Hide or remove the post or comment; closes every open report about it. |
| `POST /admin/comments/{id}/{hide,unhide,remove}` | Moderate a comment directly. |
| `GET /admin/queues` | Now includes `open_reports`. |

## Slice 4: the notification centre (done)

Design and trade-offs are in ADR 0021.

| Endpoint | What it does |
|---|---|
| `GET /notifications` | Your notifications, newest first; `unread=true`, `cursor`, `limit`. Poll about every 30 seconds with `If-None-Match`: unchanged answers 304. Includes `unread_count`. |
| `POST /notifications/read` | Mark `ids` (up to 100) or `all` as read. |

Delivered now: comments on your post, replies, mentions, the outcome of reports you filed, and
registration approval, each by in-app notice and email according to the member's preferences.
Comment, reply and mention emails are capped at ten an hour per member.

## Slice 5: link preview cards with SSRF protection (done)

Design, the full list of controls and trade-offs are in ADR 0022.

Posts now carry `previews` (title, description, site, picture) for the first two links in their body.
Cards are fetched by a worker, never in a request. The fetcher refuses internal and non-public
addresses at every redirect hop, pins the connection to the address it checked, and caps time and
size. Pictures are scanned and re-encoded before being served from our media domain.

## Still to do in Stage 2

1. Jobs and opportunities with expiry and alerts, news and win submissions, events and demo days,
   campaigns and segments, admin queues.
2. Notices for those modules (job expiry, event reminders) using `notify()`.
3. The CDN purger (provider decision still pending; revisit before Stage 2 ends).
4. Hardening follow-ups from this stage: run the `media` queue with an egress allow list; consider
   monthly partitions for notifications if volume warrants.
