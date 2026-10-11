# WO Community

WO Community is the members' home of WithOnyeka, a network for the people building Africa's
companies: **founders** starting them, **operators** running them, **investors** backing them and
**mentors** who have done it before. It is where a member goes to be found, to find the right
person, to hear what is happening, to learn, and to take an idea from a sentence to something they
can put in front of an investor.

## What members can do

| Area | What it gives a member |
|---|---|
| **Directory** | A searchable, privacy-aware directory of members and startups, with a profile each person controls. |
| **Feed** | Posts, comments and reactions from the community, with reporting and moderation behind it. |
| **Jobs** | Roles and opportunities with expiry, saved jobs and alerts. |
| **Events** | Meetups and demo days, with registration and calendar details in the member's own time zone. |
| **Learning** | Courses with lesson progress and certificates. |
| **Mentoring** | Find a mentor, request and book a session, give feedback; mentors apply, set availability and accept. |
| **News** | Editorial stories and community wins. |
| **Admin console** | For staff: approve or decline new members, invite people, review jobs and wins, act on reports, decide mentor applications and watch the numbers. Admin accounts must use two step sign in. |
| **Launch toolkit** | A private workspace per venture: a validation **score**, a 44 section **business plan**, a two-year financial **forecast**, **pitch decks**, clickable **prototypes** and a **venture partner** to talk things through. Everything is written from the member's own answers, anything proposed is shown before it is applied, and anything can be shared by link or with a chosen mentor. |

Visitors who are not members can read the public site, browse public startups and jobs, and ask for
access. New accounts are reviewed before they see the community.

## How it is built

- **Back end** (`apps/`, `config/`): a Django modular monolith with Django REST Framework, PostgreSQL,
  Redis and Celery. The API is described by an OpenAPI schema (`docs/api/openapi.yaml`), errors follow
  RFC 9457 problem details, lists use cursor pagination, and edits to shared records carry an ETag
  or version so two tabs cannot overwrite each other silently.
- **Front end** (`frontend/`): React 18, TypeScript and Vite. Its API types are generated from the
  back end's OpenAPI schema, so a change to the API that breaks the app fails the type check. The
  look follows the WO design system (see `frontend/README.md`).
- **Toolkit** (`apps/toolkit/`): long running work (scoring, plans, exports, prototypes) runs as
  jobs the browser follows. AI features sit behind an adapter with a fake for tests and are
  advisory: they never state a figure that is not in the member's data or a cited source.
- **Security**: short lived access tokens in memory, a refresh token in an HttpOnly cookie, every
  view denied unless it declares a policy, uploads scanned and re-encoded, and a review in
  `docs/toolkit-security-review.md`.

Decisions and their reasons are in `docs/adr/`; what each stage delivered is in `docs/stages/`.

## Run it locally

Requirements: Python 3.12, Docker.

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
make install
cp .env.example .env
make up          # PostgreSQL 16, Redis 7, mail catcher, S3 compatible storage
make migrate
make run         # http://localhost:8000
make worker      # in a second terminal
make beat        # in a third terminal
```

Host ports default to 5433 (PostgreSQL), 6380 (Redis) and 8026 (mail UI) so the stack does not
collide with databases already running on a developer machine. Override with `DB_PORT`,
`REDIS_PORT` and `MAIL_UI_PORT`.

Useful URLs: `/health/live`, `/health/ready`, `/api/v1/ping`, `/api/v1/schema/`.

Emails go to an in-memory fake by default. For real mail, set `EMAIL_ADAPTER` to the Resend adapter and
follow *Setting up Resend* in `docs/runbooks/core-alerts.md`.

Uploads use an in-memory storage and scanner by default. To try real ones, set
`STORAGE_ADAPTER=apps.integrations.storage.s3.S3Storage` with the MinIO container's endpoint, create the
`wo-quarantine`, `wo-media` and `wo-private` buckets (the private one holds course documents
and must not be public), and start ClamAV with `docker compose --profile scanner up -d`.

## Run the whole thing

```bash
# back end (see above for the first time set up)
make up && make migrate
make run                      # API on http://localhost:8000
make worker                   # jobs: scores, plans, exports (needed for the toolkit)
DJANGO_SETTINGS_MODULE=config.settings.local python scripts/seed_demo.py   # a demo community

# front end
cd frontend
npm install
npm run dev                   # http://localhost:5173, /api is proxied to the back end
```

For the admin console, also run `DJANGO_SETTINGS_MODULE=config.settings.local python scripts/seed_admin_demo.py`.
It gives `admin@demo.test` two step sign in with a known demo key (so the browser tests can work out
the codes), adds `editor@demo.test` (a content editor who has not set up two step sign in yet), and
adds a job, a reported post and a win waiting for review. Run it again to add more.

The demo data includes members to sign in as (password `Demo-Passw0rd-2026`): `amaka@demo.test`
(member), `ada@demo.test` (mentor), `pending@demo.test` (awaiting approval), `admin@demo.test` and
`editor@demo.test` (admin roles).

On Windows the Celery worker needs the solo pool: `celery -A config worker --pool=solo -l info`.

### Front end checks

```bash
cd frontend
npm run lint && npm run typecheck && npm test && npm run build
npm run e2e                   # real browser against the running API and demo data
npm run generate:api          # refresh src/api/schema.d.ts after the API changes
```

The end to end tests use a browser that is already installed (`E2E_BROWSER=chrome` or `msedge`,
Edge by default) so nothing is downloaded. They need the API, the worker and the demo data running.
Some limits are daily (for example new job posts), so many repeated runs on one database can hit
them; clear the cache (`redis-cli -n 1 FLUSHDB` in the local container) to reset.

## Quality gates

`make ci` runs everything the pipeline runs: `ruff`, `black --check`, `mypy`, `bandit`,
`pip-audit`, `import-linter`, the test suite, OpenAPI generation and `check --deploy`.
Tests need PostgreSQL (`make up`); SQLite is not supported.

## Layout

See `docs/adr/` for the reasons behind structural decisions and `docs/stages/` for what each stage
delivered. Modules live in `apps/`; a module may import a lower level module only through its
public services or events (enforced by `.importlinter`).

## Conventions

- Views are thin. Business rules live in services; reads live in selectors.
- Every view declares a `policy`; a view without one is denied (`apps/core/permissions.py`).
- Serializers reject unknown fields (`StrictSerializer`).
- Money is integer minor units plus a currency code. Timestamps are timezone aware, stored in UTC.
- Third party services sit behind adapters in `apps/integrations` with a fake for tests.
- Configuration comes from environment variables and is validated at start up (`config/env.py`).
