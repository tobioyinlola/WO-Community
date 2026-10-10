# 0023. The jobs and opportunities board

Status: accepted (Stage 2)

## Decisions

- **Applications are not handled.** A job applies by an external https link or an email address, as
  specified. The platform shows the target to members and nothing more. Client events
  (`job_viewed`, `job_apply_clicked`, `job_shared`) already exist in the analytics registry.
- **Who posts.** Any active member can post for one of their startups, or name a hiring
  organisation. Admins (`jobs.moderate`: content editors and above) post for the community or
  partners; those jobs always carry an external link, name an organisation or startup, go live at
  once and have no poster card. A member may post five jobs a day.
- **Review is a setting, not a deploy.** A single `JobSettings` row (super admin, `settings.manage`)
  decides whether member jobs wait for an admin (the default) or go live at once, and the default
  term in days (60). Pending jobs are listed at `GET /admin/jobs?status=pending`, counted in
  `GET /admin/queues`, and approved or rejected. A rejection needs a reason, which the poster sees
  and is told. Approval, rejection, unpublishing and removal are audited.
- **Lifecycle:** pending, published, closed, expired, rejected, removed. A job expires at the end of
  its deadline day (UTC) or, with no deadline, after the default term. A beat job every 15 minutes
  marks lapsed jobs expired, and the board also hides any job past its expiry the moment it lapses
  in case the job is late. An hourly job notifies the poster once per term when three days remain.
  The poster can renew a published, expired or closed job for a new term (optionally with a new
  deadline) or close it. Renewing a job that had ended announces it again to alerts. A renewed job
  is not re-reviewed because it was already approved. Editing a published job also does not send it
  back for review; the report and removal tools are the control for later misuse, and this is
  recorded here because it is a choice, not an oversight.
- **Visibility.** Members see live jobs whose poster is still an active member (so a suspension
  removes their jobs at once), plus their own jobs in any state except removed. Pending and rejected
  jobs are visible only to their poster and to admins.
- **Text and apply targets** are cleaned the same way as posts: rich text through the allow list,
  plain fields stripped of markup, links must be https on public hostnames, emails validated and
  lower-cased. A job needs a startup or an organisation.
- **Board search** combines Postgres full text (a stored, indexed vector over title, organisation,
  location and description) with forgiving matching on title and organisation, and typo tolerance
  that is switched off when the query uses quotes or exclusions. Filters: type, remote, startup,
  location and how recently it was posted. Results are newest first with keyset paging.
- **Public pages for sharing.** `GET /public/jobs`, `/public/jobs/{slug}` and
  `/public/jobs/sitemap` need no login, are cacheable with ETags like the directory, and the
  detail carries Open Graph fields and a share link. They never include the poster's identity, the
  poster's id or an apply email address (an email-apply job shows only the method, so scrapers get
  nothing). Going live, closing, expiring and removal purge the CDN paths through the adapter.
- **Saving and alerts.** Members save up to 200 jobs; ended jobs stay in their list with a status.
  They keep up to five alerts of saved filters, instant or daily. Instant alerts fire when a job
  goes live (approval counts, not submission), at most one notice per member per job; daily alerts
  send one digest per day with a count of new matches. Notices follow the new `jobs` notification
  preference, and instant alert emails are capped like other member-triggered mail.
- **Search.** Jobs are also searchable from the member-area search.

## Consequences

The public jobs are not in the directory's main sitemap because the directory module cannot depend
on jobs; the front end should merge `GET /public/jobs/sitemap`. Reporting a job, application
tracking and employer analytics are not built. Alerts are matched in memory when a job goes live,
which is fine at the expected number of alerts and can move to a query if it grows.
