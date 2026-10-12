# Runbook: venture launch toolkit

Queues: `ai` (model work), `exports` (documents). Workers: `make worker` runs both; production
runs `worker-ai` on its own so slow model calls cannot delay exports or the rest of the platform.

## Jobs are waiting (`wo_toolkit_jobs_queued` high, or `wo_toolkit_oldest_queued_seconds` over 300)

1. Is an `ai` worker running and consuming (`celery -A config inspect active_queues`)?
2. Is the model provider slow or failing? Check `wo_toolkit_ai_runs_total{outcome!="ok"}` and
   `GET /api/v1/toolkit/admin/quality`. A provider outage shows as `timeout` and `error`.
3. One member cannot hold more than `TOOLKIT_MAX_ACTIVE_JOBS` (default 4) at once, so a single
   account cannot be the cause of a long queue; look for a wide spike instead.
4. Scale `worker-ai` first. Raising `AI_DAILY_RUN_CEILING` does not speed anything up.

## Jobs stuck in `running`

`toolkit.reap_stuck_jobs` runs every 10 minutes and fails jobs that have not moved for 30 minutes
with `internal_error`; members see a clear message and can start again. If many are stuck, a
worker is being killed mid-job: check memory limits and the 30 minute soft time limit.

## Model provider down or returning bad output

1. `AI_FALLBACK_PROVIDER` takes over after temporary failures; five failures in a minute open a
   breaker for a short while (jobs fail fast with `temporarily_unavailable`).
2. If both are down, switch the tools off without a release: set `TOOLKIT_FEATURE_PLAN=false`
   (and others) and restart. A tool that is off answers 404; nothing is lost.
3. A rising `invalid_output` rate for one prompt (`/admin/quality`) means that prompt or the model
   changed. Roll the model back (`AI_MODEL_*`) or fix the prompt file and deploy.

## The daily ceiling is reached for a member

`AI_DAILY_RUN_CEILING` (default 400 model calls per member per day) answers 429 with the
reset time. Do not raise it for one member; look at `/admin/usage` first. A plan costs about 50
calls, so heavy regeneration is the usual cause.

## Research returns nothing

`RESEARCH_ALLOWED_DOMAINS` must list the sites; `RESEARCH_SEARCH_URL` and `_KEY` must be set.
With no sources, scores show `insufficient_data` for market and risk and plans leave sourced
sections without figures: this is correct behaviour, not a failure.

## A member reports a wrong number

Forecast figures come only from the engine. Reproduce with the saved assumptions
(`GET .../forecast/result`) and the venture export; the same assumptions always give the same
numbers. If the engine is wrong that is a bug: add a case to `forecasts/tests/test_engine.py`.
Plan text figures are checked against the venture's data and sources; if one slipped through,
capture the prompt id and version from `AIRun` and add a case to the evaluation set.

## A share link was leaked

The owner revokes it (`DELETE /ventures/{id}/shares/{id}`) and it stops at once. Staff cannot
list or revoke member links; the token is not stored, only its hash.

## Erasing a venture

Deleted ventures are erased after `VENTURE_DELETE_GRACE_DAYS` (14) by
`toolkit.erase_deleted_ventures`. Files in the private bucket go first, then rows. To erase now:
`ventures.services.erase_due(now=...)` with a time past the grace period, after the member (or a
legal request) confirms. The audit log keeps that it happened, never what was in it.

## Alerts

| Alert | Condition | Severity |
|---|---|---|
| Toolkit queue backlog | `wo_toolkit_oldest_queued_seconds > 300` for 10 minutes | page |
| Toolkit job failures | failed share of `wo_toolkit_jobs_total` over 15 minutes above 20% | page |
| Model refusals | `wo_toolkit_ai_runs_total{outcome="invalid_output"}` share above 15% for a prompt | ticket |
| Spend | estimated cost per day above budget (`/admin/usage`) | ticket |
