# Running the production settings on your machine

This runs the same Docker image Railway builds, with `DEBUG` off, gunicorn, the worker and scheduler,
a real virus scanner, a mail catcher and an S3 compatible store, against the built front end. It is how
the deployment changes were checked. Nothing here goes to a real service.

## What you need

- Docker, with PostgreSQL and Redis from `docker-compose.yml` (`docker compose up -d db redis`).
- A mail catcher on port 1026 (the web page is on 8026): `docker compose up -d mail`.
- ClamAV: `docker compose --profile scanner up -d clamav` (the first start takes a minute or two while
  it loads its signatures).
- An S3 compatible store that your browser and your containers can both reach by the same address,
  because signed upload links name the host. Use the address of your machine on the network (not
  `localhost`, which means something different inside a container). MinIO from `docker compose up -d storage`
  works, or any S3 emulator.
- Node, for the front end.

## 1. Environment file

Make a file outside the repository, for example `prod.env`. Every name is explained in
`backend/.env.example`. The values that matter for a local run:

```
SECRET_KEY=<random>
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
DATABASE_URL=postgres://wo:wo@db:5432/wo_prod
DB_SSLMODE=disable
REDIS_URL=redis://redis:6379/2
CORS_ALLOWED_ORIGINS=http://localhost:4173
FRONTEND_URL=http://localhost:4173
API_BASE_URL=http://localhost:8001
NUM_PROXIES=1
LOCAL_PRODUCTION_RUN=true          # only for a local run: lifts the https checks, never on a real host
JWT_PRIVATE_KEY=...                # PEM with line breaks written as \n
JWT_PUBLIC_KEY=...
FIELD_ENCRYPTION_KEYS=<fernet key>
EMAIL_ADAPTER=apps.integrations.email.smtp.SmtpEmailAdapter
EMAIL_SMTP_HOST=<mail catcher container name>
EMAIL_SMTP_PORT=1025
EMAIL_FROM_TRANSACTIONAL=WO Community <no-reply@mail.example.com>
EMAIL_FROM_MARKETING=WO Community <community@news.example.com>
STORAGE_ADAPTER=apps.integrations.storage.s3.S3Storage
STORAGE_ENDPOINT_URL=http://<your machine's address>:9000
STORAGE_REGION=auto
STORAGE_UPLOAD_METHOD=put          # the R2 path
STORAGE_ANCHOR_OBJECT_LOCK=false
STORAGE_ACCESS_KEY_ID=...
STORAGE_SECRET_ACCESS_KEY=...
MEDIA_BASE_URL=http://<your machine's address>:9000/wo-media
MALWARE_SCANNER=apps.integrations.malware.clamd.ClamdScanner
CLAMD_HOST=<clamav container name>
MEETING_GOOGLE_MEET_ADAPTER=apps.integrations.meetings.google.GoogleMeetProvider
GOOGLE_MEET_CLIENT_ID=x
GOOGLE_MEET_CLIENT_SECRET=x
GOOGLE_MEET_REFRESH_TOKEN=x
TOOLKIT_FEATURE_SCORE=false        # and PLAN, FORECAST, DECKS, PROTOTYPES, PARTNER
```

Create the four buckets (`wo-quarantine`, `wo-media`, `wo-private`, `wo-anchor`) in the store, and make
`wo-media` readable.

## 2. Build and start

```
cd backend
docker build -t wo-api:prodtest .
docker run --rm --network <compose network> --env-file prod.env wo-api:prodtest python manage.py migrate --noinput
docker run --rm --network <compose network> --env-file prod.env -e ADMIN_PASSWORD=... wo-api:prodtest \
  python manage.py create_super_admin --email you@example.com
docker run -d --name api    --network <compose network> --env-file prod.env -e PORT=8001 -p 8001:8001 wo-api:prodtest
docker run -d --name worker --network <compose network> --env-file prod.env wo-api:prodtest \
  celery -A config worker -B -l info --concurrency 2 -Q critical,default,email,media,exports,analytics,ai
```

The compose network is named after the repository folder (`docker network ls`). Check
`http://localhost:8001/health/`: it should say `{"status":"ok","database":"ok","redis":"ok"}`.

## 3. Build and serve the front end

```
cd frontend
VITE_API_URL=http://localhost:8001 npx vite build --mode localprod --outDir ../dist-local
VITE_API_URL=http://localhost:8001 npx vite preview --mode localprod --outDir ../dist-local --port 4173
```

`--mode localprod` skips the production build's check that the API address is https, which a local run
cannot satisfy. A real build (`npm run build`) keeps the check.

## 4. Look at it

- `http://localhost:4173`: sign in, open a course, upload an image.
- `http://localhost:8026`: the mail catcher. Request a password reset and the email appears here.

To run the same checks in a browser:

```
cd frontend
E2E_PRODUCTION_RUN=1 E2E_BASE_URL=http://localhost:4173 npx playwright test e2e/production-run.spec.ts
```

It checks: sign in across the two hosts with an HttpOnly, Secure, Lax refresh cookie set by the API; a
course page; an image that goes to storage with a signed PUT, is scanned and rebuilt by the worker,
and is then served from the media address; and a password reset email that arrives in the mail catcher
with a link to the app, in both HTML and plain text, signed "Best regards, The WO Community Team".
