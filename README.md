# WO Community Backend

REST API for the WO Community platform: a Django modular monolith with Django REST Framework,
PostgreSQL, Redis and Celery. The React front end lives in a separate repository and consumes the
generated OpenAPI schema (`docs/api/openapi.yaml`).

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
`wo-quarantine` and `wo-media` buckets, and start ClamAV with `docker compose --profile scanner up -d`.

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
