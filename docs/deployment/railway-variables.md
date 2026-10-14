# Railway variables

Every environment variable the API reads in production, with what it does and where the value comes
from. The same list, with comments, is in `backend/.env.example`.

The API and the worker run the same settings, so **both services need the same variables**. Use
Railway shared variables (or reference the API's values from the worker) so you set each one once.

## Check before you deploy

```
cd backend
python manage.py check_env
```

`check_env` reads the variables of the shell it runs in, applies the production rules, and prints
**every** missing or invalid variable in one report, with a hint for each. It never prints a secret, it
does not start the server, and it exits with 1 when something is wrong. On Railway, run it against the
real values with `railway run python manage.py check_env` (Railway CLI, linked to the service), or open a
shell with `railway ssh`.

The same check runs first whenever the API or the worker starts. A deploy that is missing variables
now fails once, with all of them listed in the deploy log, instead of once per variable:

```
The production settings are not complete: 3 problems.
  1. EMAIL_ADAPTER: Environment variable EMAIL_ADAPTER is required.
     Hint: One of: apps.integrations.email.resend.ResendEmailAdapter; ...
  2. JWT_PRIVATE_KEY: JWT_PRIVATE_KEY is not a readable PEM private key.
     Hint: An Ed25519 PEM key on one line with \n between the lines and no quotes. ...
  3. API_BASE_URL: API_BASE_URL must be a public https address, got 'http://localhost:8000'.
     Hint: Use the full address, for example https://api.example.com
```

## Generate the secrets

From the `backend` folder:

```
python scripts/generate_secrets.py
```

It prints four lines, `NAME=value`, and writes nothing to disk:

| Line | Format |
|------|--------|
| `DJANGO_SECRET_KEY` | a 64 byte URL safe random string |
| `FIELD_ENCRYPTION_KEYS` | one Fernet key (44 characters) |
| `JWT_PRIVATE_KEY` | Ed25519 private key, PKCS#8 PEM |
| `JWT_PUBLIC_KEY` | the matching public key, SubjectPublicKeyInfo PEM |

**JWT key format.** The code reads each key as PEM text. In Railway paste it as **one line with a
literal backslash and `n` between the lines**, with no quotes:

```
-----BEGIN PRIVATE KEY-----\nMC4CAQAw...\n-----END PRIVATE KEY-----
```

The settings turn each `\n` back into a line break. A value with real line breaks also works where the
Railway editor keeps them, but the one line form is the safe one. It is not base64: do not encode it.
The check refuses a key that is not Ed25519, is not readable, or whose public half does not belong to
the private key.

Keep the output out of the repository and out of chat. Never commit `.env`, `.pem` files or the output.
A new JWT pair signs every member out. FIELD_ENCRYPTION_KEYS holds comma separated keys, newest first:
to rotate, put the new key in front and keep the old one after a comma, or stored values stop decrypting.

## Required for the API and the worker

| Variable | What it does | Example | Where to get it |
|----------|--------------|---------|-----------------|
| `DJANGO_SECRET_KEY` (or `SECRET_KEY`) | Signs sessions and tokens. Must not be a placeholder; under 50 characters gives a warning. | (64 random characters) | `scripts/generate_secrets.py` |
| `DJANGO_ALLOWED_HOSTS` (or `ALLOWED_HOSTS`) | Host names the API answers to. Never `*`, no `https://`. | `api.example.com` | Your API domain |
| `DATABASE_URL` | PostgreSQL connection. | `postgresql://user:pass@host:5432/railway` | Railway reference `${{Postgres.DATABASE_URL}}` |
| `REDIS_URL` (or `CELERY_BROKER_URL`) | Cache and the Celery queue. | `redis://default:pass@host:6379` | Railway reference `${{Redis.REDIS_URL}}` |
| `FRONTEND_URL` (or `FRONTEND_BASE_URL`) | The front end, https, no path. Used in every link in an email. | `https://app.example.com` | Your front end domain |
| `API_BASE_URL` | This API, https, no path. Used in unsubscribe links. | `https://api.example.com` | Your API domain |
| `CORS_ALLOWED_ORIGINS` | Origins the browser may call the API from, comma separated, https only. | `https://app.example.com` | Your front end domain |
| `NUM_PROXIES` | Proxy hops before the API. Must be at least 1 or every visitor shares one rate limit. | `1` | Always `1` on Railway |
| `JWT_PRIVATE_KEY` | Signs access tokens (EdDSA). See the format above. | `-----BEGIN PRIVATE KEY-----\n...` | `scripts/generate_secrets.py` |
| `JWT_PUBLIC_KEY` | Verifies them. Must match the private key. | `-----BEGIN PUBLIC KEY-----\n...` | `scripts/generate_secrets.py` |
| `FIELD_ENCRYPTION_KEYS` | Encrypts sensitive fields at rest. | (44 characters) | `scripts/generate_secrets.py` |
| `EMAIL_ADAPTER` | Which email sender is used. See "Email" below. | `apps.integrations.email.resend.ResendEmailAdapter` | The list below |
| `STORAGE_ADAPTER` | File storage class. | `apps.integrations.storage.s3.S3Storage` | [cloudflare-r2.md](cloudflare-r2.md) |
| `MALWARE_SCANNER` | Upload virus scanner class. | `apps.integrations.malware.clamd.ClamdScanner` | [railway.md](railway.md) step 4 |
| `MEDIA_BASE_URL` | Public https address of the media bucket. | `https://media.example.com` | [cloudflare-r2.md](cloudflare-r2.md) |
| `MEETING_GOOGLE_MEET_ADAPTER` | The default meeting provider must be a real one (the fake is refused). | `apps.integrations.meetings.google.GoogleMeetProvider` | Fixed value; or use Zoom (below) |
| `AI_PROVIDER`, or the six `TOOLKIT_FEATURE_*` switched off | The launch toolkit needs a real model, or every tool off. | `http`, or `TOOLKIT_FEATURE_SCORE=false` and five more | See "Launch toolkit" below |
| `RESEARCH_PROVIDER` (unless every tool is off) | Source for toolkit research. | `apps.toolkit.ai.research.web.WebResearchProvider` | Fixed value |

## Required when a choice above is made

| Variable | Needed when | What it does | Where to get it |
|----------|-------------|--------------|-----------------|
| `RESEND_API_KEY` | `EMAIL_ADAPTER` is Resend | Sends mail. Starts with `re_`. | Resend, API Keys, Sending access |
| `RESEND_WEBHOOK_SECRET` | Resend | Verifies bounce and complaint webhooks. Starts with `whsec_`. | Resend, Webhooks, Signing Secret |
| `EMAIL_FROM_TRANSACTIONAL` | Resend | From address for account mail. | `WO Community <no-reply@mail.example.com>` on a verified domain |
| `EMAIL_FROM_MARKETING` | Resend | From address for newsletters (a different subdomain). | `WO Community <community@news.example.com>` |
| `STORAGE_ACCESS_KEY_ID`, `STORAGE_SECRET_ACCESS_KEY` | `S3Storage` | Bucket credentials. | Cloudflare R2, API tokens |
| `GOOGLE_MEET_CLIENT_ID`, `GOOGLE_MEET_CLIENT_SECRET`, `GOOGLE_MEET_REFRESH_TOKEN` | Google Meet adapter | Makes meeting links for mentoring sessions. | Google Cloud console |
| `MEETING_DEFAULT_PROVIDER=zoom`, `MEETING_ZOOM_ADAPTER=apps.integrations.meetings.zoom.ZoomProvider`, `ZOOM_ACCOUNT_ID`, `ZOOM_CLIENT_ID`, `ZOOM_CLIENT_SECRET` | Zoom instead of Google Meet | Same job. | Zoom marketplace, Server-to-Server OAuth |
| `AI_BASE_URL`, `AI_API_KEY` | `AI_PROVIDER=http` | An OpenAI compatible API. | Your model provider |
| `RESEARCH_ALLOWED_DOMAINS` | `WebResearchProvider` | Sites research may read, comma separated. | You choose, for example `data.example.org` |
| `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ZONE_ID`, `CDN_ORIGIN_URL` | `CDN_PURGER` is `apps.integrations.cdn.cloudflare.CloudflarePurger` | Clears the cached copy of a changed public page. | Cloudflare dashboard |

## Optional

| Variable | Default | What it does |
|----------|---------|--------------|
| `CSRF_TRUSTED_ORIGINS` | CORS origins plus `API_BASE_URL` | Origins trusted for the CSRF check (https). |
| `DB_SSLMODE` | `require` | Use `prefer` if the database connection fails with an SSL error. |
| `DB_CONN_MAX_AGE` | `60` | Seconds a database connection is kept. |
| `REDIS_CACHE_URL` | `REDIS_URL` | A separate Redis database for the cache. |
| `JWT_ISSUER` | `wo-community` | The `iss` claim of tokens. |
| `REFRESH_COOKIE_SECURE` | `true` | Must stay true (the check refuses false). |
| `REFRESH_COOKIE_SAMESITE` | `Lax` | Right while app and API share one registrable domain. |
| `EMAIL_REPLY_TO`, `EMAIL_LOGO_URL`, `EMAIL_SIGNOFF`, `CAMPAIGN_FOOTER` | empty or built in | Email wording and branding. |
| `EMAIL_WARMUP_START`, `EMAIL_HOURLY_CAP`, `EMAIL_DKIM_SELECTORS` | none, `-1`, `resend` | Sending limits while a new domain warms up; DKIM names the health page checks. |
| `STORAGE_ENDPOINT_URL`, `STORAGE_REGION`, `STORAGE_UPLOAD_METHOD` | empty, `us-east-1`, `post` | For R2: `https://<account>.r2.cloudflarestorage.com`, `auto`, `put`. |
| `STORAGE_QUARANTINE_BUCKET`, `STORAGE_MEDIA_BUCKET`, `STORAGE_PRIVATE_BUCKET`, `STORAGE_ANCHOR_BUCKET` | `wo-quarantine`, `wo-media`, `wo-private`, `wo-anchor` | Bucket names. |
| `CLAMD_HOST`, `CLAMD_PORT` | `localhost`, `3310` | Where ClamAV listens (`clamav.railway.internal`). |
| `GOOGLE_CLIENT_ID` | empty | Turns on Google sign in. Then leave `GOOGLE_TOKEN_VERIFIER` unset (the fake is refused). |
| `ENVIRONMENT`, `RELEASE`, `LOG_LEVEL`, `SENTRY_DSN` | `local`, `dev`, `INFO`, empty | Logging and error reporting. Set `ENVIRONMENT=production`. |
| `METRICS_TOKEN` | empty (closed) | Bearer token for `/metrics`. |
| `WEB_CONCURRENCY`, `GUNICORN_THREADS`, `GUNICORN_TIMEOUT`, `FORWARDED_ALLOW_IPS` | CPU based, `2`, `30`, `*` | Gunicorn tuning (API only). `PORT` is set by Railway. |
| `ADMIN_PASSWORD` | asked for | Read by `manage.py create_super_admin`. Set it only for that one command. |
| `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_TRACE_SAMPLE_RATIO` | empty, `0.1` | Tracing. |
| `LOCAL_PRODUCTION_RUN` | `false` | Trial run on one machine only (see [local-production-run.md](local-production-run.md)). Never on a real deployment. |

The remaining tuning values (`AI_MODEL_*`, `FEED_*_PER_DAY`, `CAMPAIGN_BATCH_*`, `DECK_*`, `PLAN_VERSIONS_KEPT`,
`SUPPORT_SLA_HOURS` and others) are listed with their defaults at the end of `backend/.env.example`. None
of them is needed to start.

## Email

`EMAIL_ADAPTER` takes one of these three values:

| Value | What it does |
|-------|--------------|
| `apps.integrations.email.resend.ResendEmailAdapter` | Real email through Resend. Needs `RESEND_API_KEY`, `RESEND_WEBHOOK_SECRET`, `EMAIL_FROM_TRANSACTIONAL` and `EMAIL_FROM_MARKETING`. |
| `apps.integrations.email.fake.FakeEmailAdapter` | A test adapter that keeps messages in memory. **It sends no real email.** |
| `apps.integrations.email.smtp.SmtpEmailAdapter` | Sends to a local SMTP server (`EMAIL_SMTP_HOST`, `EMAIL_SMTP_PORT`). For a local mail catcher, not for production. |

Any other value is refused with the list above.

**To get the app booting before Resend is ready**, set `EMAIL_ADAPTER=apps.integrations.email.fake.FakeEmailAdapter`
and leave the four Resend variables out. The check passes with a warning:

> EMAIL_ADAPTER is the fake adapter: the app starts, but no email is sent.

**Warning:** with the fake adapter nobody receives verification mail, password resets, approvals or newsletters,
so members cannot finish registering or recover an account. Use it only to prove the deploy boots, then switch to the
Resend adapter. Resend setup (domains, DNS, API key, webhook) is in [resend.md](resend.md).

## Launch toolkit

The toolkit needs one of two things, or the API will not start:

- **A real model**: `AI_PROVIDER=http`, `AI_BASE_URL`, `AI_API_KEY`, and `RESEARCH_PROVIDER=apps.toolkit.ai.research.web.WebResearchProvider`
  with `RESEARCH_ALLOWED_DOMAINS`.
- **Every tool off**: set all six of `TOOLKIT_FEATURE_SCORE`, `TOOLKIT_FEATURE_PLAN`, `TOOLKIT_FEATURE_FORECAST`,
  `TOOLKIT_FEATURE_DECKS`, `TOOLKIT_FEATURE_PROTOTYPES` and `TOOLKIT_FEATURE_PARTNER` to `false`. None of the AI or research
  variables is then needed. This is the quickest way to boot.

## Which service needs what

| Service | Variables |
|---------|-----------|
| **API** (`railway.json`) | Everything above. Also `PORT` (set by Railway) and the optional gunicorn variables. |
| **Worker** (`railway.worker.json`, runs Celery with the scheduler) | The same required variables as the API, because it loads the same production settings and the same check runs when it starts. Functionally it uses the database, Redis, email, storage, scanner, AI and CDN variables; the address and CORS variables are set only so the check passes. Not needed: `PORT` and the gunicorn variables. |

Set every variable once as a Railway shared variable and attach it to both services.
