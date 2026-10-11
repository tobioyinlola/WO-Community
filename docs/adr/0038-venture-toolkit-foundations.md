# 0038. The venture launch toolkit: structure and foundations

Status: accepted (toolkit stages T0 and T1)

## Structure

- **One Django app per module** under `apps/toolkit/` (`ventures`, `jobs`, `ai`, `scoring`,
  `plans`, `forecasts`, `decks`, `prototypes`, `partner`, `sharing`, `admin_api`), each with its own
  models and migrations. A single large app would have given one migration history and no place for
  the dependency rules to bite. Import-linter enforces the order in `.importlinter`; a second
  contract keeps the forecast engine free of any framework or other module.
- **The module order decides where code lives.** Things the model layer needs from ventures stay in
  ventures; the profile assistance endpoints live in `ai` because they call it; sharing sits above
  decks and prototypes because it renders them.
- **API prefix** `/api/v1/toolkit/`. Each tool has a feature flag (`TOOLKIT_FEATURE_*`); a tool that
  is switched off answers 404 as though it did not exist.

## The model layer

- **One interface, any provider.** `LLMProvider` has `generate_text` and `generate_structured`. The
  shipped real implementation speaks the chat completions HTTP API that many services offer, so
  changing provider is `AI_BASE_URL`, `AI_API_KEY` and model names, not code. No provider name is
  hard coded outside `providers/`. A fake implementation returns deterministic output (the
  smallest value that satisfies the schema, or what a test scripts per prompt id) so CI and local
  development run offline.
- **Routing and resilience.** `AI_MODEL_ROUTING` picks a model per kind of task so routine steps
  can use a cheaper one; `AI_FALLBACK_PROVIDER` takes over after a temporary failure; five failures
  in a minute open a short breaker. Provider calls ask not to be stored (`store: false`) and carry
  no member identifiers.
- **Prompts are files**, versioned, with schemas, loaded by id. Member text and fetched pages are
  inserted only as delimited data blocks; delimiter characters inside them are neutralised, and
  the standard system text says that such blocks are never instructions.
- **Answers are checked in code.** A structured answer is validated against its schema; an
  invalid one is asked for again with the reason, up to twice, and then the step fails with a safe
  message. Free text from a model is also screened before it is shown (instruction leakage).
- **Usage, not credits.** Every call writes an `AIRun` (agent, provider, model, prompt id and
  version, tokens, duration, estimated cost, outcome) and never the content. A daily ceiling per
  member returns 429. Nothing models balances or prices, so credits can be added later.
- **Rules in code.** Legal, tax and investment advice and requests to invent customers, traction or
  reviews are declined by `safety.screen` before any model is called; the prompts repeat the rule,
  but the code does not depend on a model complying.

## Research

Facts are shared and not personal. A fact needs a source and a verbatim quote that must appear in
the fetched page (whitespace and case aside), which is what stops a model from "finding" a
statistic the page never made. Sources are deduplicated by address and content hash, search results
are cached by question, region and day, and the web provider fetches only domains an admin
approved (an empty list approves nothing) through the guarded client used for link previews.

## Jobs

A job is created in the request, handed to a worker after commit, and polled. Kinds register a
handler; the runner picks up only queued jobs (so a duplicate delivery does nothing), reports
progress, stops a cancelled job at its next step, and always ends it in a state the member can see.
A crash shows a generic message, never the exception. A temporary problem is retried with backoff
and then reported as "temporarily unavailable". A reaper fails jobs a dead worker abandoned.
`Idempotency-Key` makes a repeated start return the same job (unique per member and kind).

## The profile

- Stored as validated JSON (one document per venture, versioned on every change) because the
  wizard saves a step at a time; competitors and team are rows. Validation is per field with
  pydantic so each error names its field, and blank or null clears a field.
- Provenance per field is recorded (`member`, `imported`, `ai_suggested_accepted`). Suggestions and
  proposals are returned, never saved by the server.
- Staleness is a static map from fields to outputs (`schema.DEPENDENTS`). Changing a field flips
  outputs that were `ready` to `needs_refresh` and lists the fields that caused it.
- Deleting hides a venture at once and erases it, with everything made from it, after a grace period
  (default 14 days) by a daily job that also removes files and shares; the member can restore it
  until then or export all of it as JSON.
- Another member's venture is a 404 on every route, including writes. A named mentor can be granted
  read access (`VentureGrant`), honoured by read endpoints only.
