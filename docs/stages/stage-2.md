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

## Slice 6: jobs and opportunities (done)

Design and trade-offs are in ADR 0023.

| Endpoint | What it does |
|---|---|
| `GET /jobs` | The board: `q`, `type`, `remote`, `startup_id`, `location`, `posted_within_days`, `cursor`, `limit`. |
| `POST /jobs` | Post a job (apply by link or email). Held for review or live at once, per the board setting. 5 a day. |
| `GET/PATCH /jobs/{id}` | Read; edit your own with an ETag. |
| `POST /jobs/{id}/renew`, `/close` | Renew for another term, or close. |
| `GET /me/jobs` | Your jobs in any state. |
| `POST/DELETE /jobs/{id}/save`, `GET /me/saved-jobs` | Save jobs. |
| `GET/POST /job-alerts`, `DELETE /job-alerts/{id}` | Alerts on saved filters, instant or daily. |
| `GET /public/jobs`, `/public/jobs/{slug}`, `/public/jobs/sitemap` | Public, cached pages with Open Graph data. |
| `GET/POST /admin/jobs`, `GET/PATCH /admin/jobs/{id}` | Moderation list (filter `status=pending` for the queue), post for the community or a partner, edit any job. |
| `POST /admin/jobs/{id}/{approve,reject,unpublish,remove}` | Review decisions; audited. |
| `GET/PUT /admin/jobs/settings` | Auto publish or hold for approval; default term (super admin). |

Scheduled: expiry sweep every 15 minutes, three-day warning hourly, daily alert digests hourly.
Notices: job live or rejected (poster), expiring soon (poster, email and in-app), matching alert or
digest (member). Jobs are included in member-area search. Queue counts include
`jobs_awaiting_review`.

## Slice 7: news, awards and win submissions (done)

Design and trade-offs are in ADR 0024.

| Endpoint | What it does |
|---|---|
| `GET /editorial`, `GET /editorial/{id}` | Published items for members; filter by `type`. |
| `GET/POST /editorial/{id}/comments`, `PATCH/DELETE /editorial-comments/{id}` | Comment on an item; edit or delete your own. |
| `POST /editorial/{id}/reactions`, `DELETE /editorial/{id}/reactions/{kind}` | Like, celebrate, insightful. |
| `GET /banners` | Announcements pinned as a banner on the member home right now. |
| `POST /win-submissions`, `GET /win-submissions` | Submit a win with evidence; see your submissions. |
| `GET /public/news`, `GET /public/news/{slug}` | Public, cached pages with Open Graph data. |
| `GET/POST /admin/editorial`, `GET/PATCH/DELETE /admin/editorial/{id}` | Write, list, edit and remove items. |
| `POST /admin/editorial/{id}/{publish,unpublish,schedule}` | Publish now, take down or cancel, or schedule. |
| `PUT/DELETE /admin/editorial/{id}/cover` | Cover image from a finished upload (purpose `editorial_cover`). |
| `POST /admin/editorial-comments/{id}/{hide,unhide,remove}` | Moderate comments. |
| `GET /admin/win-submissions`, `POST /admin/win-submissions/{id}/{approve,reject}` | Review wins; approving drafts a story. |

Scheduled: `editorial.publish_due` every minute. Notices: win accepted or not (member). Queue counts
include `wins_awaiting_review`.

## Slice 8: events and demo days (done)

Design and trade-offs are in ADR 0025. Note: the analytics ingest endpoint moved to
`POST /analytics/events` so `/events` is free for this module.

| Endpoint | What it does |
|---|---|
| `GET /events` | Upcoming (soonest first) or `when=past` archive; filter `type`, `registered=true`. |
| `GET /events/{id}` | Detail with join link, demo day pitch order, and recording and summary once over. |
| `POST/DELETE /events/{id}/register` | Register (capacity enforced) or cancel. |
| `GET /events/{id}/calendar.ics` | Add to any calendar. |
| `GET /public/events`, `/public/events/{slug}` | Public, cached pages with Open Graph data. |
| `GET/POST /admin/events`, `GET/PATCH/DELETE /admin/events/{id}` | Manage events (ETag on edit). |
| `POST /admin/events/{id}/{publish,unpublish,cancel}` | Lifecycle; cancelling notifies registrants. |
| `PUT /admin/events/{id}/slots` | Demo day presenters and pitch order. |
| `GET /admin/events/{id}/attendees`, `/attendees.csv` | Attendee list and CSV (step-up MFA, audited, formula-safe). |
| `POST /admin/events/{id}/attendees/{user}/check-in` | Mark present or not. |

Scheduled: reminders every ten minutes (24 hours and 1 hour before). Notices: registration
confirmed, reminder, cancelled, new times.

## Slice 9: campaigns and segments (done)

Design and trade-offs are in ADR 0026.

| Endpoint | What it does |
|---|---|
| `GET/POST /admin/segments`, `GET/PATCH/DELETE /admin/segments/{id}` | Save audiences built from fixed attributes. |
| `POST /admin/segments/preview`, `GET /admin/segments/{id}/preview` | Members matching, and how many are mailable. |
| `GET/POST /admin/campaign-templates`, `DELETE /admin/campaign-templates/{id}` | Reusable block layouts. |
| `GET/POST /admin/campaigns`, `GET/PATCH/DELETE /admin/campaigns/{id}` | Write newsletters (blocks, merge field `{{first_name}}`). |
| `POST /admin/campaigns/{id}/{test,send,schedule,unschedule,pause,resume,cancel}` | Test to yourself; send, schedule and resume need step-up MFA; pause is the kill switch. |
| `GET /admin/campaigns/{id}/report` | Sent, delivered, opened, clicked, bounced, unsubscribed, complained. |
| `POST /unsubscribe` | One-click, signed link, no login; immediate. |
| `GET/PUT /me/marketing-consent` | A member's yes or no to marketing email. |

Scheduled: `campaigns.start_due` every minute (also rescues stalled sends).

## Stage 2 is feature complete except for admin dashboards

What remains is the admin dashboards and queues beyond counts.

## Still to do in Stage 2

1. Admin dashboards and summary tables (registrations, active members, funnels, engagement).
2. The CDN purger (provider decision still pending; revisit before Stage 2 ends).
3. Hardening follow-ups from this stage: run the `media` queue with an egress allow list; consider
   monthly partitions for notifications if volume warrants; merge the jobs, news and events
   sitemaps into the front end's sitemap; set up the marketing sending domain (SPF, DKIM, DMARC,
   warm-up).
