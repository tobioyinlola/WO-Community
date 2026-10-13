# Production readiness audit

Written before the deployment changes, so it describes what the repository did at the start. The
"Fixed in" column says which change dealt with each item. Paths use the final layout, with the Django
project in `backend/` and the React app in `frontend/`.

## Things that assumed a developer machine

| Where | What it assumed | Risk in production | Fixed in |
|-------|-----------------|--------------------|----------|
| `config/settings/base.py` `DATABASES` | `DATABASE_URL` only, SSL left to `DB_SSLMODE` | Fine, but the name differs from what Railway sets for other variables | kept; production adds SSL |
| `base.py` `CACHES` | `REDIS_CACHE_URL`, default `redis://localhost:6380/1` | A missing variable fell back to localhost silently | one `REDIS_URL` is required in production |
| `base.py` `CELERY_BROKER_URL` | default `redis://localhost:6380/0` | Same | derived from `REDIS_URL` |
| `base.py` `FRONTEND_BASE_URL` | default `http://localhost:5173`; used in every email link | Emails would link to localhost | `FRONTEND_URL` is required in production and must be https |
| `base.py` `API_BASE_URL` | default `http://localhost:8000`; used in one-click unsubscribe headers | Unsubscribe links broken | required in production and must be https |
| `base.py` `EMAIL_FROM_*` | default `no-reply@localhost` | Mail rejected or marked as spam | already required for Resend; now also checked for a real domain |
| `base.py` `MEDIA_BASE_URL` | default `http://localhost:9000/wo-media` | Broken images | already required; now must be https |
| `base.py` `CLAMD_HOST` | default `localhost` | Uploads can never pass the scan | `MALWARE_SCANNER` is required; docs say how to run ClamAV |
| `config/settings/local.py` | `DEBUG = True`, `localhost` hosts and CORS, fake Google verifier, fixed encryption key | Must never be used in production | production reads `config.settings.production` only; a check refuses `local` when `DEBUG` or fake adapters are on |
| `config/celery.py` | defaults to `config.settings.local` | A worker started without the variable would run development settings | the Docker image sets `DJANGO_SETTINGS_MODULE=config.settings.production` |
| `frontend/vite.config.ts` | `/api` proxied to `http://localhost:8000` | Development only; the proxy is not part of a build | kept, development only |
| `frontend/playwright.config.ts` | `http://localhost:5173` | Test only | kept |
| `frontend/src/api/client.ts` | `VITE_API_BASE_URL`, empty means same origin | A production build without it calls `app.<domain>/api`, which Vercel serves as the SPA | renamed `VITE_API_URL`, required for a production build |
| `.env.example` | Local values only | Nothing tells you what production needs | backend and front end examples now list every variable |

## DEBUG, SQLite, local disk, console email

- **DEBUG**: `base.py` sets `False`, `local.py` sets `True`, `production.py` sets `False`. No code reads
  `DEBUG` to change behaviour apart from Django itself. Now also `DEBUG` is read from the environment in
  production and must be false.
- **SQLite**: not used anywhere. PostgreSQL features are required (partitioned audit table, triggers,
  `django.contrib.postgres`).
- **Local disk media**: no `MEDIA_ROOT`, `FileField` or `ImageField` exists. Uploads go straight from the
  browser to object storage through the storage adapter in `apps/integrations/storage`. The default
  adapter is an in memory fake, so a deployment that forgets `STORAGE_ADAPTER` would lose files; production
  already refuses that.
- **Console email**: the default adapter is a fake that keeps messages in memory. Production requires
  `EMAIL_ADAPTER` to be set explicitly.
- **Static files**: `STATIC_ROOT` was set but nothing served the files. The API serves JSON only and has
  no Django admin, so static files only matter for the API schema page. WhiteNoise now serves them.

## Gaps found

1. **Cloudflare R2 does not support browser form uploads (presigned POST).** The upload flow used a
   presigned POST. A presigned PUT works on R2. The adapter and the front end now support both, chosen
   by `STORAGE_UPLOAD_METHOD`.
2. **No `/health/` route.** The probes were `/health/live` and `/health/ready`. `/health/` now checks the
   database and Redis in one call.
3. **No WhiteNoise, no gunicorn config.** The image started gunicorn with fixed flags and port 8000.
   Railway sets `PORT`.
4. **Celery queues.** Work is split across seven queues. A single `celery worker -B` only reads
   `default`, so mail, exports, analytics, media and AI tasks would wait forever. The documented command
   names every queue.
5. **`NUM_PROXIES` defaults to 0.** Behind Railway the client address would be the proxy, so rate limits
   would count every visitor as one. Production now needs it set to 1.
6. **`CSRF_TRUSTED_ORIGINS` not set.** Required for the Django CSRF check across `app.` and `api.`.
7. **Cookie settings.** `REFRESH_COOKIE_SECURE` defaulted to true but `SESSION_COOKIE_SECURE` and
   `CSRF_COOKIE_SECURE` were set only in production. They stay there. See "Login method" below.
8. **`JWT_PRIVATE_KEY` / `JWT_PUBLIC_KEY`** are required in production and must be set as Railway
   variables (multi line keys written with `\n`).
9. **Repository layout.** The Django project sat at the repository root beside `frontend/`. It now lives
   in `backend/`, so each deploy target has a root directory of its own.

## Login method

The API signs members in with a short lived access token (10 minutes) that the browser keeps in memory
and sends as `Authorization: Bearer`, plus a refresh token in an HttpOnly cookie named `wo_refresh`.
The cookie is `Secure`, `HttpOnly`, `SameSite=Lax`, limited to the path `/api/v1/auth/`, and is set by
`api.<domain>`.

`app.<domain>` and `api.<domain>` share one registrable domain, so they are the same site. `Lax`
cookies are sent on those requests, and no cookie `Domain` is needed (the cookie belongs to the API
host only, which is what you want). Cross origin requests need CORS with credentials, which is already
on, and the origin list comes from `CORS_ALLOWED_ORIGINS`.

## Secrets in history

Reported in `docs/deployment/go-live-checklist.md` after the history scan.
