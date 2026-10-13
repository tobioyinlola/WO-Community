# Deploying the API on Railway

The API, the worker and the scheduler run from one Docker image built from `backend/`. Railway runs
them as separate services of one project, with PostgreSQL and Redis beside them.

Only you can do the steps below (they need your Railway account). Everything in the repository is
already set up for them.

## 1. Create the project and the databases

1. In Railway, create a new project and choose **Deploy from GitHub repo**. Pick this repository and
   the branch you deploy from (`main` for production).
2. Add **PostgreSQL** (New, Database, PostgreSQL) and **Redis** (New, Database, Redis).
3. The first service Railway made from the repository becomes the API. Rename it `api`.

## 2. The API service

In the service's **Settings**:

| Setting | Value |
|---------|-------|
| Root Directory | `backend` |
| Config as code path | `/backend/railway.json` |
| Builder | Dockerfile (the file sets this) |

`railway.json` already holds the rest: it runs `python manage.py migrate --noinput` before each deploy
(the database is migrated once, by this service), checks `/health/` before sending traffic, and
restarts on failure. The container listens on the `PORT` Railway provides.

**Networking**: add a custom domain `api.<your domain>`. Railway shows a CNAME target and a TXT
record to publish; see [dns.md](dns.md). Railway issues the certificate by itself.

## 3. The worker service

The worker runs Celery and the scheduler in one process:

```
celery -A config worker -B -l info --concurrency 2 -Q critical,default,email,media,exports,analytics,ai
```

`config` is the Django project (it holds `celery.py`). `-B` starts the scheduler inside the worker.
`-Q` names every queue. Without it the worker reads only `default`, and email, exports, analytics,
link previews and AI jobs would wait for ever.

1. New, GitHub Repo, the same repository. Name the service `worker`.
2. Settings: Root Directory `backend`, Config as code path `/backend/railway.worker.json`.
3. Give it the **same variables** as the API (use shared variables, or reference the API's).
4. **Run exactly one replica.** Two workers with `-B` would run every scheduled job twice. When the
   load needs more workers, run a second service without `-B` and with only the queues it should read.

The `media` queue fetches web pages for link previews. See "Egress" in
[../deployment.md](../deployment.md) before you rely on it in production: a single service means
that worker is not on its own network.

## 4. ClamAV (virus scan of uploads)

Production refuses to start without a scanner. Add a service from the Docker image
`clamav/clamav:1.4` named `clamav`, with at least 2 GB of memory and no public domain. Then set on the
API and the worker:

```
MALWARE_SCANNER=apps.integrations.malware.clamd.ClamdScanner
CLAMD_HOST=clamav.railway.internal
CLAMD_PORT=3310
```

## 5. Variables

Set these on the API and the worker. `${{Postgres.DATABASE_URL}}` is Railway's reference syntax.
Every variable, with a comment, is in `backend/.env.example`.

| Variable | Value |
|----------|-------|
| `DJANGO_SECRET_KEY` | a new random string: `python -c "import secrets; print(secrets.token_urlsafe(64))"` |
| `DJANGO_ALLOWED_HOSTS` | `api.<your domain>` |
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` |
| `REDIS_URL` | `${{Redis.REDIS_URL}}` |
| `FRONTEND_URL` | `https://app.<your domain>` |
| `API_BASE_URL` | `https://api.<your domain>` |
| `CORS_ALLOWED_ORIGINS` | `https://app.<your domain>` |
| `CSRF_TRUSTED_ORIGINS` | `https://app.<your domain>,https://api.<your domain>` |
| `NUM_PROXIES` | `1` |
| `JWT_PRIVATE_KEY`, `JWT_PUBLIC_KEY` | Ed25519 PEM keys with line breaks written as `\n` (see `.env.example`) |
| `FIELD_ENCRYPTION_KEYS` | a Fernet key |
| `EMAIL_ADAPTER` | `apps.integrations.email.resend.ResendEmailAdapter` |
| `RESEND_API_KEY`, `RESEND_WEBHOOK_SECRET` | from [resend.md](resend.md) |
| `EMAIL_FROM_TRANSACTIONAL`, `EMAIL_FROM_MARKETING` | for example `WO Community <no-reply@mail.<your domain>>` |
| `STORAGE_ADAPTER` | `apps.integrations.storage.s3.S3Storage` |
| `STORAGE_ENDPOINT_URL`, `STORAGE_REGION`, `STORAGE_UPLOAD_METHOD`, keys, buckets, `MEDIA_BASE_URL` | from [cloudflare-r2.md](cloudflare-r2.md) |
| `MALWARE_SCANNER`, `CLAMD_HOST`, `CLAMD_PORT` | from step 4 |
| `MEETING_DEFAULT_PROVIDER` and its credentials | a real provider; the fake one is refused |
| `AI_PROVIDER` and its keys, or `TOOLKIT_FEATURE_<NAME>=false` for each tool | the toolkit needs one or the other |
| `SENTRY_DSN`, `ENVIRONMENT=production`, `RELEASE` | optional |

If a required variable is missing or unsafe the service stops at start with a message that names it.
Read the deploy log first when a deploy fails.

If the database connection fails with an SSL error, set `DB_SSLMODE=prefer`.

## 6. After the first deploy

1. Open `https://api.<your domain>/health/`. You should see `{"status":"ok","database":"ok","redis":"ok"}`.
2. Create the first administrator. Nobody can invite or approve yet, so use the command. With the
   Railway CLI, open a shell in the API service (`railway ssh`) and run:

   ```
   python manage.py create_super_admin --email you@example.com
   ```

   It asks for the password twice (or reads `ADMIN_PASSWORD`). Sign in at `https://app.<your domain>/login`;
   the account must set up two step sign in the first time.
3. Check the worker log shows `celery@... ready` and `beat: Starting...`.

## Logs, scaling, cost

- Logs are JSON, one line per request, with a request id that also appears in the audit log.
- To handle more traffic, raise the API's replicas. The API is stateless.
- `WEB_CONCURRENCY` (gunicorn workers per replica) and `GUNICORN_THREADS` can be set as variables.

## Rollback

See the rollback note in [go-live-checklist.md](go-live-checklist.md#rollback).
