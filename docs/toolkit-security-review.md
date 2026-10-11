# Venture launch toolkit: security review

Scope: everything under `apps/toolkit`, the `/api/v1/toolkit/` routes, its jobs, files and the
model and research adapters. This is a self review against the Stage 5 brief; an independent
review and a test with real provider credentials are still to be done before launch.

## What is being protected

Founders write down ideas, finances and plans that are not public and may be worth a lot. The
platform holds them for the member alone. The model layer is the main new way for that content
to leave, so most controls are about it.

## Threats and controls

| # | Threat | Control | Where | Verified by |
|---|---|---|---|---|
| 1 | Another member reads or changes a venture | Every venture route resolves the venture through the caller (`owned_venture`, `readable_venture`); someone else's is a 404, not a 403 | `ventures/permissions.py` | `admin_api/tests/test_access_matrix.py` walks every route from the URL configuration |
| 2 | Routes added later forget authorisation | Views without a policy are denied; the matrix test discovers new routes by itself | `core/permissions.py` | matrix test, anonymous and unapproved |
| 3 | A shared link leaks, or is guessed | 192 bit token, only its hash stored, constant time compare, optional password, expiry, revocation; every failure is the same 404; per address and per link throttles | `sharing/` | `sharing/tests`, ADR 0042 |
| 4 | Staff read member ventures | Admin endpoints change templates, rubrics and plan sections and read counts and sizes only; there is no admin route to a venture | `admin_api/` | matrix test (admin routes), `test_admin_api.py` |
| 5 | Member text is sent to a provider that trains on it or keeps it | Calls carry `store: false`, no member identifiers and no account email; provider and model are configuration; nothing outside `ai/providers` names a provider | `ai/providers/http.py` | `ai/tests` |
| 6 | Prompt injection through the idea text or a fetched page | Member text and pages go into delimited data blocks with the delimiter neutralised; prompts say data is not instructions; outputs are schema validated; nothing a model returns is executed or saved as an action | `ai/prompts.py`, `ai/runner.py` | `ai/tests`, `partner` tests |
| 7 | The model invents a figure, source or claim | Scores and forecasts are computed in code; plan and partner text has every figure checked against the venture's data and cited facts and unsupported ones are removed; facts are kept only when their quote is found in the page | `plans/content.py`, `partner/service.py`, `ai/research/service.py` | `plans/tests`, `partner/tests`, evaluation set |
| 8 | The model writes to a member's profile | Never directly: proposals become change sets the member applies, with undo, and are recorded as accepted suggestions | `partner/service.py` | `partner/tests` |
| 9 | Research is used to reach internal addresses, or leaks the idea | Only allow listed domains, fetched through the safe client (no private ranges, bounded size and time); queries are built from sector and region only | `ai/research/web.py`, `ai/research/gather.py` | `ai/tests`, `scoring/tests` |
| 10 | A deck or prototype carries script, markup or links | Both are validated data from allow lists; text is plain; no address a member typed is stored; navigation is between the prototype's own screens | `decks/schema.py`, `prototypes/spec.py` | `decks/tests`, `prototypes/tests` |
| 11 | A hostile image | Signature checked, malware scanned, decoded and re-encoded (drops metadata and appended data), size and pixel limits, private bucket, signed short lived links | `decks/service.py`, `uploads/images.py` | `decks/tests` |
| 12 | Exports are stolen from storage | Private bucket, random keys, 15 minute links, deleted after 7 days and with the venture | `jobs/exports.py` | `plans/tests`, `admin_api/tests/test_lifecycle.py` |
| 13 | One member exhausts capacity or budget | At most 4 active jobs per member, a daily ceiling on model calls, a per job time limit, a breaker on provider failures | `jobs/services.py`, `ai/runner.py` | `jobs/tests/test_fairness.py` |
| 14 | Spreadsheet formula injection in exports | Cells that start with `=`, `+`, `-` or `@` are neutralised in the usage CSV; the forecast spreadsheet writes only numbers and its own formulas | `admin_api/service.py`, `forecasts/export.py` | `admin_api/tests` |
| 15 | Data is kept after a member leaves | Export of everything, 14 day grace, then erasure of rows and files; usage rows keep counts and sizes and lose the venture | `ventures/services.py` | `admin_api/tests/test_lifecycle.py` |
| 16 | Secrets in code or logs | Keys only from the environment; startup refuses a fake provider in production with tools on; job payloads and member text are not logged | `config/settings/production.py` | `scripts/deploy_check.py` |
| 17 | Advice the platform must not give | Legal, tax and investment requests and requests for made up proof are declined in code before any model call | `ai/safety.py` | `partner/tests`, evaluation set |

## Known limits

- Injection resistance is containment, not detection: a hostile page can still make a model say
  something odd. The consequences are limited because model output never acts without the member.
- The refusal rules are patterns. They catch plain requests, not every phrasing; the prompts add a
  second line and the disclaimer on scores and plans makes the scope explicit.
- Mentors with read access see everything the owner sees until it is revoked; there is no
  per section grant yet.
- Share links show what existed when opened (decks and summaries are live). A member who wants a
  frozen copy exports a file instead.
- The `can_comment` grant flag exists and no comment feature uses it yet.
- A real provider and a real research source have not been exercised: tests use the fake ones.
