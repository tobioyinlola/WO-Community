# Go-live checklist

Tick each line in order. Steps that only you can do (they need your accounts) are marked **you**.

## Before

- [ ] **you** Domain chosen; its DNS can be edited ([dns.md](dns.md)).
- [ ] CI is green on the branch you deploy (`main`).
- [ ] `docs/deployment/audit.md` read; nothing in it is left open that you care about.
- [ ] No secret in the repository: the history scan below found nothing real.
- [ ] **you** Fresh secrets made for production (never reuse the development ones): `DJANGO_SECRET_KEY`,
      `JWT_PRIVATE_KEY` and `JWT_PUBLIC_KEY`, `FIELD_ENCRYPTION_KEYS`.

## Accounts and services (you)

- [ ] Railway project with PostgreSQL, Redis, `api`, `worker`, `clamav` ([railway.md](railway.md)).
- [ ] Cloudflare R2 buckets, custom media domain, token, CORS, lifecycle and lock rule ([cloudflare-r2.md](cloudflare-r2.md)).
- [ ] Resend domains verified, API key, webhook and signing secret ([resend.md](resend.md)).
- [ ] Vercel project with `VITE_API_URL` ([vercel.md](vercel.md)).
- [ ] DNS records published ([dns.md](dns.md)).

## First deploy

- [ ] API deploy succeeds. If it stops, the log names the missing or unsafe variable.
- [ ] `https://api.<domain>/health/` returns `{"status":"ok","database":"ok","redis":"ok"}`.
- [ ] Worker log shows the worker ready and the scheduler started, once (one replica).
- [ ] First super admin created with `create_super_admin`; two step sign in set up.
- [ ] `https://app.<domain>` loads; a deep link reloads without a 404.

## Smoke test on production

- [ ] Sign in and out. In the browser the `wo_refresh` cookie is Secure and HttpOnly.
- [ ] A course page opens.
- [ ] Upload a profile photo; it shows from `https://media.<domain>`.
- [ ] Upload a support attachment; it opens only through an expiring link.
- [ ] Request a password reset; the email arrives, is branded, links to `https://app.<domain>`.
- [ ] Send a test from Email templates; it shows a verified sender.
- [ ] Email health shows SPF, DKIM and DMARC for both subdomains.
- [ ] A Celery job ran (for example the digest, or the admin alert after a test support request).
- [ ] An admin action appears in the audit log.

## After

- [ ] Sentry (if used) receives a test error.
- [ ] Database backups on in Railway; a restore has been tried once.
- [ ] `EMAIL_WARMUP_START` set before the first newsletter.
- [ ] DMARC reports are read; plan to move from `p=none`.
- [ ] Domain `HSTS` is on (the API sends it). Only add the domain to the browser preload list when
      you are sure every subdomain will stay https.

## Rollback

Decide quickly: a bad release is rolled back first and fixed afterwards.

**API or worker code**
1. Railway, the service, Deployments: pick the last good deployment and **Redeploy** it. Do this for
   `api` and `worker` together so they run the same code.
2. Look at `/health/` and the log.

**Front end**
1. Vercel, Deployments: open the last good deployment and choose **Promote to Production** (or
   Instant Rollback). It takes effect in seconds.

**Database**
- Migrations only move forward. The pre deploy step runs `migrate` before new code takes traffic, so
  a bad migration stops that deploy and the old version keeps serving.
- If a release applied a migration and the old code cannot run against it, do not edit tables by hand.
  Redeploy the fixed code. Migrations in this repository add before they remove (the migration lint
  enforces that), so the previous release keeps working against the new schema.
- Restore from a Railway backup only for data loss. A restore loses everything after the backup, so
  note the time first and tell the admins.

**Configuration**
- Railway keeps variable history; put the old value back and redeploy.
- A wrong `VITE_API_URL` is fixed by changing it in Vercel and redeploying the front end.

**Email**
- If mail goes wrong, set `EMAIL_ADAPTER` back to the fake adapter only as a last resort: it sends
  nothing, so password resets will not arrive.
