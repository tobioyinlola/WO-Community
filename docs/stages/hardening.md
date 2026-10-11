# Hardening pass

Done after Stage 3. Design and trade-offs are in ADR 0036 (operations) and ADR 0037 (the small
product gaps).

## Operations

| Item | Result |
|---|---|
| Audit head hash anchoring | Daily, to an Object Lock bucket; mismatches and broken chains are logged at error level. |
| Raw analytics archival | Expired partitions are written to Parquet and recorded before they can be dropped. |
| Rejected registration purge | 90 days, daily job, audited by id only. |
| Tracing and metrics | OpenTelemetry (off until configured) and a token protected `/metrics`. |
| Migration safety lint | `make lint-migrations` on new migrations; run in CI. |
| Container build and scan | In CI: build, start, scan for high and critical vulnerabilities. |
| Schema drift and deployment check | In CI. |
| Media queue egress | Its own worker process and network in compose; the rule is in `docs/deployment.md`. |
| Marketing sending domain | A checklist in `docs/deployment.md` (this is operational work). |
| Sitemaps | `GET /public/sitemaps` lists every public page of every kind. |

## Product gaps

| Item | Result |
|---|---|
| Suspension and removal emails | Suspended, reinstated and removed members are emailed with the reason. |
| Reporting news comments | `POST /editorial-comments/{id}/reports`; one queue with the feed's. |
| Follow notices and suggestions | A once only notice; `GET /me/follow-suggestions`. |
| Link preview admin | List, refetch, block and unblock domains. |
| News: following, notices, digest | `GET /me/news/following`; notices; opt-in weekly digest. |
| Events and news in search | `types=events,news,courses` on `GET /search`. |
| Attendee list to the organiser | `POST /admin/events/{id}/attendees/send` to `organiser_email`. |
| Newsletter analytics events | Already recorded; the notes were out of date. |
| Dashboard detail | Mentor supply and demand; per course completion and ratings. |

## Still open

- **Infrastructure as code** for a specific cloud: needs the provider and account decisions.
  `docs/deployment.md` is the specification.
- **The CDN purger**: needs the provider decision.
- **Payments (Stage 4)**: needs the provider and scope.
- Running the DNS and email domain warm-up steps, and creating the buckets with the right policies,
  are tasks for whoever deploys.
