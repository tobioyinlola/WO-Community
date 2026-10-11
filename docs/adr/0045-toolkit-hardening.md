# 0045. Toolkit hardening: fairness, observability, evaluation and what staff can see

Status: accepted (toolkit stage T5)

## Decisions

- **Per member job cap.** At most `TOOLKIT_MAX_ACTIVE_JOBS` (4) queued or running jobs per member;
  more answers 429. Combined with the daily model call ceiling and the job time limit this bounds
  what one account can take from the shared workers without a priority scheme. A repeated
  idempotency key is answered before the cap, so retries are never refused.
- **Metrics without content.** Jobs ended (by kind and status), time from queued to ended, model
  calls (by prompt and outcome) and tokens, plus gauges for queued, running and oldest queued jobs
  read at scrape time through a collector hook (`core.metrics.add_collector`) so the core knows
  nothing of the toolkit.
- **Staff manage content, not ventures.** The admin API edits templates, plan sections and the
  score rubric (validated before they are stored, audited, rubric activation needs a recent MFA
  check) and reads usage and a quality queue built from identifiers, counts and sizes. There is
  no route that returns a member's venture to staff.
- **A fixed evaluation set.** `manage.py toolkit_evaluate` runs 20 fictional ventures through the
  deterministic parts (profile rules, score stability, forecast balance in every scenario, which
  plan sections a profile can support, every deck template, refusals) and fails the build on any
  regression. It uses no model, so it is cheap and exact; answer quality from a real model is
  judged separately when credentials are available.
- **The access matrix is generated.** One test walks the URL configuration and tries every
  toolkit route as an anonymous caller, an unapproved member and another member, so a route added
  without authorisation fails the build instead of waiting for a review.
- **Production refuses unsafe configuration.** With any tool on, the fake model or research
  provider, a missing provider key or an empty research allow list stops startup.
- **Data lifecycle is tested end to end.** One test builds a venture with every kind of output and
  proves the export contains all of it and that erasure removes every row and every file.

## Not done

- A load test against real infrastructure with a real provider (the fairness test is in process).
- An independent security review and a penetration test (`docs/toolkit-security-review.md` is a
  self review).
- Real provider and research smoke tests: no credentials were available.
