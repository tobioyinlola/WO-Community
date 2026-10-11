# Toolkit Stage T5: hardening, staff tools and evaluation

Design in ADR 0045. Security review in `docs/toolkit-security-review.md`; runbook in
`docs/runbooks/toolkit.md`; module guide in `apps/toolkit/README.md`.

## Staff endpoints (under `/api/v1/toolkit/admin`)

| Endpoint | Permission | What it does |
|---|---|---|
| `GET/PUT /deck-templates` | `toolkit.manage` | List all (including off); create or replace one, validated by building a deck from it. |
| `GET/PUT /prototype-templates` | `toolkit.manage` | Same for prototypes, validated against the registry. |
| `GET /plan-sections`, `PATCH /plan-sections/{n}` | `toolkit.manage` | Edit wording, inputs, dependencies, on or off. The summary cannot be switched off. |
| `GET/POST /score-rubrics` | `toolkit.settings` | List; add a version (weights must total 100, verdicts must cover 0). |
| `POST /score-rubrics/{v}/activate` | `toolkit.settings` + recent MFA | Make a version the one in use. |
| `GET /usage`, `GET /usage.csv` | `toolkit.manage` | AI use by day, prompt or agent; up to 366 days. |
| `GET /quality` | `toolkit.manage` | Refused answers and failed jobs, last 7 days. |
| `GET /settings` | `toolkit.settings` | Flags and providers, no secrets. |

## Checks added

- `manage.py toolkit_evaluate` (also in CI): 20 fictional ventures, 270 checks.
- Access matrix over every route; data export and erasure completeness; job fairness; metrics.

## Operational changes

- Jobs: `TOOLKIT_MAX_ACTIVE_JOBS`, `wo_toolkit_*` metrics, `toolkit.purge_exports` hourly,
  `toolkit.weekly_nudges` on Mondays.
- Production startup refuses a fake model or research provider while any tool is on.
