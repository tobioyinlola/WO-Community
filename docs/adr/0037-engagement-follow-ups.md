# 0037. Engagement follow-ups

Status: accepted (closes the small gaps recorded in ADRs 0017 to 0027)

## Members are told what happened to their account

Suspension, reinstatement and removal now send an email with the reason, as approval and rejection
already did (`MemberSuspended` and `MemberRemoved` carry the reason). The suspension email says that
anything agreed with others, such as mentoring sessions, was cancelled.

## Comments on news can be reported

Reports of comments on news and wins use the same queue as posts and comments. Editorial owns the
report (`CommentReport`, endpoint `POST /editorial-comments/{id}/reports`, same reasons, one per
member and comment, same daily limit setting as the feed) because only it knows whether a comment can
be seen and how to hide it. The admin console, which sits above both modules, lists the two kinds
together (`target_type=news_comment` filters to the new one), and review, action and detail pick the
right owner by id. Acting hides or removes the comment, closes every open report on it and tells
each reporter. The queue count on `GET /admin/queues` includes both.

## Following

- **A notice when someone follows you** (a startup's owner is told for a startup). Once per
  follower and target for ever, so unfollowing and following again stays quiet. In app only by
  default; the `follows` preference switches it off. There are still no follower lists or counts
  (ADR 0019): the person is told *that* someone followed, not given a list to browse.
- **Suggestions** (`GET /me/follow-suggestions`) are scored from a shared sector, stage and
  country, from how many people you follow already follow the candidate, and from recent activity;
  each carries its reasons. Never someone followed, yourself, an inactive member or anyone whose
  basics are hidden from you.

## News

- **News about what you follow** (`GET /me/news/following`): news and wins featuring a startup you
  follow, or a startup of someone you follow. It lives in the member area module because it needs
  both the editorial and the feed modules.
- **A notice when a story features a startup you follow**, under the `news` preference (in app on,
  email off). A retried event notifies nobody twice.
- **A weekly digest** of the most talked about stories, Monday 08:00 UTC, only for members who
  switched `news_digest` email on (it is off until chosen), at most one per ISO week.

## Link previews can be managed

Moderators can list cards, fetch one again, and block a domain (`/admin/link-previews`,
`/admin/blocked-domains`). A blocked domain and all its subdomains are never fetched; existing
cards for it are taken down at once and their pictures released; posts keep the plain link. The
check is made again when a worker is about to fetch, so a block added while a fetch was queued
still holds. Everything is audited.

## Search and sitemaps

Search gained `events`, `news` and `courses` (title and text matching; people and startups keep
trigram typo tolerance). `GET /public/sitemaps` lists every public page of every kind (startups,
founders, jobs, news, events and courses open to visitors) in one response, built in the member
area module for the same layering reason, so the front end writes one sitemap.

## Events

The attendee list can be emailed (as CSV text) to the event's `organiser_email`, or to the admin who
asks when none is set. The address cannot be chosen at send time, so the list only goes where the
event says; sending needs a fresh MFA check and is audited.

## Dashboards

Mentorship gained supply and demand: weekly capacity, mentors with published times, top expertise
offered and top needs saved, requests, acceptance rate, median reply time, requests unanswered for
48 hours, the no-show rate and the average rating. Learning gained a breakdown of the ten most
enrolled courses with completion rate and rating.

## Already built

The newsletter analytics events (`newsletter_sent`, `_delivered`, `_opened`, `_clicked`,
`_unsubscribed`) were added during the Stage 2 review and had been left in the notes as unbuilt; the
note in ADR 0026 is corrected.

## Consequences

Digest and notice timing is fixed (Monday morning UTC); per-member delivery windows are not built.
Suggestions are recomputed on request from a bounded pool of candidates, which is fine at this size.
A news comment report does not carry a snapshot of the comment: if it is deleted before a moderator
looks, the report shows it as removed with no excerpt.
