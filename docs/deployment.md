# Deploying the platform

This is what the application needs from the environment it runs in. Infrastructure as code for a
specific cloud lives in a separate repository, because it depends on the provider and account
choices that have not been made; this page is the input to it, so the code can be written without
reading the application.

## Processes

| Process | Command | Notes |
|---|---|---|
| API | `gunicorn config.wsgi:application` (the image default) | Stateless; run at least 2. Set `PROMETHEUS_MULTIPROC_DIR` to a writable temp directory when running several workers per container. |
| Worker | `celery -A config worker -Q critical,default,email,exports,analytics` | Every queue except `media` and `ai`. The `exports` queue also builds the toolkit documents; its image needs the fonts those files use. |
| AI worker | `celery -A config worker -Q ai` | Toolkit model calls. Give it its own concurrency and time limits; it needs the model provider's address and key and no other credentials beyond the database and broker. |
| Media worker | `celery -A config worker -Q media` | Fetches web pages and pictures for link previews. See *Egress* below. |
| Beat | `celery -A config beat` | Exactly one. Schedules live in `CELERY_BEAT_SCHEDULE` (database scheduler). |
| Migrations | `python manage.py migrate` | A release step before the new API starts, run by one process. |

All processes use the same image and the same environment, apart from the media worker's network.

## Backing services

- **PostgreSQL 16.** The migration role must be allowed `CREATE EXTENSION btree_gist` (once, or let
  an administrator create it). The application role must not have `UPDATE` or `DELETE` on
  `audit_auditlog`. Statement and idle-in-transaction timeouts are set on the role.
- **Redis 7** for the broker and the cache (separate databases).
- **Object storage (S3 compatible)** with four buckets:

  | Bucket (setting) | Public | Notes |
  |---|---|---|
  | `STORAGE_QUARANTINE_BUCKET` | never | Raw uploads. Delete objects older than a day by lifecycle rule as a backstop. |
  | `STORAGE_MEDIA_BUCKET` | through the CDN only | Re-encoded images. Served from a cookieless domain (`MEDIA_BASE_URL`). |
  | `STORAGE_PRIVATE_BUCKET` | never | Course documents and analytics archives. Signed links only. |
  | `STORAGE_ANCHOR_BUCKET` | never | **Created with S3 Object Lock enabled.** The daily audit head hash is written in COMPLIANCE mode and cannot be changed or deleted for `AUDIT_ANCHOR_RETENTION_DAYS` (7 years by default). The application credentials need `PutObject` and `PutObjectRetention` on it, and must not have `BypassGovernanceRetention`. |

- **ClamAV** (`clamd`) reachable by the workers, for `MALWARE_SCANNER`.
- **Email provider** (Resend) and the sending domains below.
- **A collector** for traces (`OTEL_EXPORTER_OTLP_ENDPOINT`) and a Prometheus scraper for
  `GET /metrics` (`METRICS_TOKEN`, bearer). Both are optional and off until configured.

## Configuration

`.env.example` lists every setting. Production refuses to start without the signing keys,
`FIELD_ENCRYPTION_KEYS`, a real storage adapter, the malware scanner, `MEDIA_BASE_URL`, the email
adapter and a real default meeting provider with its credentials. `scripts/deploy_check.py` runs
Django's deployment check against the production settings with placeholders, and CI runs it inside
the built image.

## Egress for the media worker

Link previews make the server fetch addresses members typed, so that worker is the one process
that talks to the open internet on someone else's behalf. The application refuses non-public
addresses itself (ADR 0022), and the network should refuse them as well so one mistake is not
the only barrier:

- Run the media worker in its own subnet or security group.
- Allow outbound TCP 80, 443, 8080 and 8443 to the public internet, DNS, and the object storage and
  Redis/Postgres endpoints it needs. Deny RFC 1918 ranges, link-local (including the cloud metadata
  address 169.254.169.254), loopback and unique-local IPv6 for everything else.
- Do not give it more credentials than it needs: it needs the database, the broker, the media and
  quarantine buckets and the malware scanner, and no email or meeting credentials.

`docker-compose.yml` already runs it as a separate service on its own network to show the shape;
compose cannot enforce an allow list, so enforcement belongs to the platform's network layer.

## Sending domains for email

Transactional mail (`EMAIL_FROM_TRANSACTIONAL`) and newsletters (`EMAIL_FROM_MARKETING`) should use
different subdomains so a marketing complaint cannot hurt password resets, for example
`mail.example.org` and `news.example.org`.

1. Add both domains in the email provider and publish the DNS records it gives: SPF (a TXT record
   including the provider), DKIM (the CNAME or TXT keys), and the return-path record.
2. Publish DMARC at `_dmarc.example.org`: start with `p=none` and a reporting address, read the
   reports for two weeks, then move to `p=quarantine` and finally `p=reject` once every legitimate
   sender passes.
3. Add `List-Unsubscribe` handling: the application already sends one-click unsubscribe headers and
   honours the provider's bounce and complaint webhooks (`RESEND_WEBHOOK_SECRET`).
4. Warm up the marketing domain: send the first newsletters to the most engaged members only (the
   segment `founder_active`), roughly 200 on day one, doubling each day while bounces stay under 2%
   and complaints under 0.1%. Campaigns pause themselves if the provider rejects the domain.
5. Test with a seed list of mailboxes at the major providers before the first full send.

## CI

`.github/workflows/ci.yml` runs lint, types, security, module boundaries, migration safety (new
migrations only), tests, API description drift and the deployment check; then builds the image,
checks it starts and scans it for high and critical vulnerabilities; and scans the history for
secrets.

## CDN (Cloudflare)

Set `CDN_PURGER=apps.integrations.cdn.cloudflare.CloudflarePurger`, `CLOUDFLARE_API_TOKEN` (Cache
Purge on the one zone only), `CLOUDFLARE_ZONE_ID` and `CDN_ORIGIN_URL` (the public host behind
Cloudflare). See ADR 0046. Authenticated routes and share links send `private, no-store` and must
not be cached by a rule.
