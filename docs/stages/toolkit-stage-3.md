# Toolkit Stage T3: financial forecast

Design in ADR 0040.

| Endpoint (under `/api/v1/toolkit`) | What it does |
|---|---|
| `GET /forecast-templates` | The six revenue templates and the assumptions each asks for. |
| `POST /ventures/{id}/forecast` | Start from the profile (template, currency, price, planned funding), or from assumptions you send. 409 if one exists. |
| `GET/PUT /ventures/{id}/forecast` | Read; save assumptions (`base_version`, 409 on conflict, 400 names each bad value). |
| `GET .../forecast/result?scenario=` | 24 months of figures, summary, unit economics and warnings. |
| `GET .../forecast/scenarios` | The three scenarios' summaries side by side. |
| `GET .../forecast/sensitivity` | Which assumptions move the result most. |
| `POST .../forecast/suggest` | Sourced proposals for rates. Saves nothing. |
| `GET .../forecast/versions`, `POST .../versions/{v}/restore` | History and going back. |
| `POST .../forecast/export` | `xlsx` (with formulas) or `pdf`; a job whose result is an export. |

## Rules enforced

- Every number comes from the engine; models propose rates with a source and never write figures.
- Money is integer minor units with a currency; out of range values are refused by name.
- Changing the profile's prices, regions, funding and so on marks the forecast out of date.
- Plan sections that use the forecast are marked out of date when its version moves.

## Not yet in this stage

- Decks, public sharing links (next commits in this stage).
