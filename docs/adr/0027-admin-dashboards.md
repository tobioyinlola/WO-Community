# 0027. Admin dashboards and summary tables

Status: accepted (Stage 2)

## Decisions

- **The console reads small tables, never raw events.** A job turns recent activity into one number
  per metric per day (`DailyMetric`: day, metric, optional dimension, value) and the dashboard
  endpoints read only that. Tested: the home page issues no query against the analytics event table.
- **Refreshing.** `adminconsole.refresh_dashboard` runs hourly and recomputes the last two days
  (so yesterday is finalised and late events are caught) plus a snapshot of today. Every number is
  overwritten with the current truth, so re-running, running twice or running late never double
  counts. `POST /admin/dashboard/refresh` (super admin) queues one on demand and a longer backfill is
  one function call. `refreshed_at` is shown so nobody mistakes stale figures for live ones.
- **What is stored per day:** new registrations, members who logged in (distinct people, so two
  logins are one), weekly and monthly active members as rolling windows ending that day, the average
  hours from registration to a decision, and the count of every analytics event (`events.<name>`).
  That last family means every funnel step, post, comment, reaction, job, win and profile update is
  already charted without a separate job for each.
- **Snapshots** of the current shape, stored against the refresh day: active and pending members,
  registrations in 7 and 30 days, retention at 30, 60 and 90 days, live jobs, members by country,
  startups by sector and by stage. Retention is the share of members approved at least N days ago who
  logged in during the last N days, and stays blank until someone is old enough to measure.
- **Endpoints:** `GET /admin/dashboard` (home: queues, community, activity, email, and learning,
  mentorship and revenue marked `available: false` until those modules exist),
  `/admin/dashboard/metrics` (what can be charted), `/series` (one metric, one point per day, zeros
  filled in for counts and blanks for averages, at most 366 days) and `/funnel`.
- **The funnel** runs directory view, registration started, a step completed, email verified,
  approved, with the share carried on from the previous step and from the start. The first steps
  are reported by visitors' browsers and only for people who agreed to analytics, so they understate
  real traffic; this is stated in the API description. The later steps are server-side and exact.
- **Access.** `dashboard.view` is held by community admins and super admins (with MFA); content
  editors do not get it. Forcing a refresh needs `settings.manage`.
- **Queue counts** moved into one function shared by `GET /admin/queues` and the dashboard.

## Consequences

Per-module detail (mentor supply and demand, course completion, revenue) arrives with those
modules by adding their daily numbers to the same table. Marketing tags are still computed when a
segment is used rather than stored in a `MemberTag` table; that is cheap at this size and can change
without altering the API. Charts of directory traffic by page and visitor-to-registration
conversion by source need richer client events than exist today. Raw event archival to columnar
files is still a hardening task.
