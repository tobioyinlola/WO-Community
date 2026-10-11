# Toolkit Stage T0: foundations

The Venture Launch Toolkit extends this backend. It lives in `apps/toolkit/` as a set of small
Django apps, one per module, with their own models and migrations (labels start `tk_`). Modules
depend downward only, which `import-linter` enforces (`.importlinter`, contract
"Toolkit module dependency levels"):

```
admin_api, partner   (top)
sharing
decks | prototypes | plans | scoring
forecasts            (its calculation engine imports nothing: a second contract enforces that)
ai
jobs
ventures             (bottom)
```

The toolkit as a whole sits above the other apps in the main layers contract, so it may use
accounts, profiles, startups, mentorship, notifications and the shared adapters, and nothing
below may import it.

## What exists

| Part | Where | Notes |
|---|---|---|
| Jobs | `toolkit/jobs` | `AIJob`, a runner, a registry of job kinds, cancel, stuck job reaper, polling with ETag and 304. Retried when a step reports a temporary problem. |
| Model adapter | `toolkit/ai/providers` | One interface (text and structured), a fake, and a provider for any service that implements the common chat completions API. Routing per task, an optional fallback, a breaker. |
| Prompts | `toolkit/ai/prompt_files` | Versioned files with a JSON schema for structured answers. Every call records the prompt id and version. |
| Runner | `toolkit/ai/runner.py` | Daily ceiling, schema validation, up to two retries of an invalid answer, a usage record for every call. |
| Research | `toolkit/ai/research` | Provider interface, a fake, a web provider limited to approved domains. A fact is kept only if its quote is on the page. Cached per question and day. |
| Safety | `toolkit/ai/safety.py` | Declines legal, tax and investment advice and requests to fabricate proof, in code. |
| Sharing primitives | `toolkit/sharing` | Unguessable tokens (192 bits, only a hash stored), optional password and expiry, revoke, view counts. |
| Permissions | `toolkit/ventures/permissions.py` | `toolkit.use` for approved members, `toolkit.manage` for community admins, `toolkit.settings` for super admins. A tool that is switched off answers 404. |

## Running it

- Workers: `celery -A config worker -Q ai` for model work and `-Q exports` for files. Local
  development needs nothing else: `AI_PROVIDER=fake` is the default and no call leaves the process.
- To use a real service set `AI_PROVIDER=http`, `AI_BASE_URL`, `AI_API_KEY` and `AI_MODEL_DEFAULT`
  (see `.env.example`).
- Tests: `pytest apps/toolkit`. They run offline against the fakes.

## Assumptions

- Chat completions is the one wire format implemented. It is widely supported, so a provider
  change is configuration; a provider with a different API needs a second adapter class.
- Structured answers use the service's JSON schema response format and are checked again in code.
- Estimated cost uses `AI_PRICE_PER_MILLION_TOKENS` (empty by default, so cost reads zero until
  prices are configured).
