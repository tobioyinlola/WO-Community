# Venture launch toolkit

Tools that help a founder go from an idea to something they can show: a profile, a validation
score, a business plan, a financial forecast, a pitch deck and a clickable prototype, with a
partner to talk it through. Everything is private to the venture's owner.

## Modules (`apps/toolkit/<name>`, labels `tk_<name>`)

| Module | Owns |
|---|---|
| `ventures` | Ventures, the profile and its rules, competitors, team, outputs' state, mentor grants, export and erasure |
| `jobs` | Long operations: queueing, idempotency, polling, cancel, fair limits; generated files and signed links |
| `ai` | Model calls (adapter, fake, routing), prompts, research and sources, safety rules, usage records |
| `scoring` | The rubric, the deterministic engine, assessments |
| `plans` | The 44 section catalogue, generation, edits, versions, export |
| `forecasts` | The pure calculation engine, assumptions, versions, spreadsheet and PDF |
| `decks` | Templates, validated slide data, patch saves, checks, images, export |
| `prototypes` | The component registry, templates, validated specification, drafting |
| `partner` | Conversations, change sets, decision log, weekly next steps, mentor suggestions |
| `sharing` | Share links and the public read endpoint |
| `admin_api` | Staff content and reports, the evaluation set |

The order above is the dependency rule (`.importlinter`): a module may use those listed after
it, never before. `forecasts/engine` imports nothing but the standard library.

## Rules that hold everywhere

- Numbers in a score or forecast come from code, never from a model. A model writes words
  around them, or proposes values that a member accepts.
- Nothing a model produced is written without the member's explicit action.
- No payments, credits or paywalls; only AI use is recorded (counts and sizes, no content).
- Money is integer minor units with a currency; times are UTC.
- Every route is default deny and answers 404 for another member's venture.

## Running it

```
docker compose up -d db redis
make migrate && make run            # API
make worker                         # ai and exports queues
make toolkit-evaluate               # the offline quality set
```

`AI_PROVIDER=fake` (the default) and the fake research provider run everything offline.
Settings are listed in `.env.example`; the runbook is `docs/runbooks/toolkit.md`.

## Adding things

- A prompt: `ai/prompt_files/<id>/v<N>.md` and `schema.json`; call it with `runner.structured`.
- A job: write `fn(ctx) -> dict`, register it in the module's `handlers.py`, start it with
  `jobs.start`, return `accepted(...)` from the view.
- An export: write the file bytes and call `jobs.exports.store`; register an exporter and an
  eraser with `ventures.register_exporter` and `register_eraser`.
- A route: set `policy`, resolve the venture with `owned_venture` or `readable_venture`; the access
  matrix test will pick it up and fail if it leaks.
