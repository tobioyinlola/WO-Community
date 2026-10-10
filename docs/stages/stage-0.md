# Stage 0: Foundations

## What was built

- **Tooling:** `pyproject.toml` with pinned dependencies, `Dockerfile` (Gunicorn, non-root),
  `docker-compose.yml` (PostgreSQL 16, Redis 7, mail catcher, S3 compatible storage, API, worker,
  beat), `Makefile`, `.env.example`, pre-commit, `.importlinter`, and `make ci`, which runs every
  gate.
- **Settings:** split per environment. `base` reads and validates environment variables
  (`config/env.py`); `production` carries the security baseline (HTTPS redirect, HSTS with preload,
  secure cookies, proxy header, required signing keys). `manage.py check --deploy` passes with
  warnings treated as failures.
- **`core`:** UUIDv7 ids, base models (timestamps, soft delete, user stamps), problem-details error
  format, cursor and offset pagination, strict serializers that reject unknown fields, role and
  permission matrix, policy framework with default deny, request id and security header
  middleware, structured JSON logging with redaction, Sentry scrubbing, health endpoints,
  OpenAPI view, transactional outbox, Celery base task with dead letter capture.
- **`accounts`:** `User` (case insensitive unique email, status, approval fields, token version),
  `UserRole`, Ed25519 signed access tokens, revocation by token version, bearer authentication,
  `GET /api/v1/me`.
- **`audit`:** append only, month partitioned log with a per day hash chain, `record()`,
  `verify_day()`, partition and verification tasks.
- **`integrations`:** email adapter interface and an in-memory fake.
- **Celery:** queues `critical`, `default`, `email`, `media`, `exports`, `analytics`; late acks,
  bounded retries with jitter; beat schedule for the outbox publisher and audit upkeep.

## Run and test

```bash
make up && make migrate && make test
make ci        # every gate
```

Result at the end of the stage: 66 tests passing; `ruff`, `black --check`, `mypy`, `bandit`,
`import-linter` and `pip-audit` clean; migrations apply to an empty database with no model drift;
the OpenAPI schema validates without warnings; `check --deploy` passes.

## Assumptions

- Python 3.12 and Django 5.2 LTS (patched to 5.2.17). Dependencies were bumped from the first
  draft after `pip-audit` flagged known issues in Django, DRF, PyJWT, black and pytest.
- Messaging and the Venture Launch Toolkit are not present in any form.
- The audit, outbox and access token decisions are recorded in `docs/adr/0001` to `0004`.
- Local compose ports are 5433/6380/8026 to avoid clashing with other local stacks.
- The postgres image is `postgres:16-alpine`; it includes the extensions the design needs.

## Deferred

- **Tracing and metrics:** structured logs, request ids and Sentry are in place. OpenTelemetry
  traces and a metrics endpoint are not yet wired; schedule them with the infrastructure work.
- **Infrastructure as code** for staging (separate repository) and the staging deployment.
- **Audit head hash anchoring** in write-once object storage (needs the storage adapter).
- **Only the email adapter** exists. Calendar, meeting, storage, malware scan, analytics and payment
  adapters arrive in the stages that use them.
- **Idempotency-Key storage** is built with the first endpoint that needs it (Stage 1 or later).
- **Migration safety lint** (`django-migration-linter` or similar) is not yet in CI.
- **Container image build and scan** in CI; the Dockerfile has not been built in this environment.
- **Gunicorn** was not run locally (it does not run on Windows); the image and compose file are
  ready for it.
