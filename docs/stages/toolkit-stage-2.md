# Toolkit Stage T2: validation score and business plan

Design in ADR 0038 (foundations) and ADR 0039 (plan).

## Validation score

| Endpoint (under `/api/v1/toolkit`) | What it does |
|---|---|
| `POST /ventures/{id}/score` | Start a score job (202; `Idempotency-Key` honoured; 400 names missing required fields). |
| `GET .../score/latest` | The report: overall score and verdict, per area score, evidence, gaps, next actions, disclaimer. |
| `GET .../score/history` | Scores over time for a chart. |
| `GET .../score/summary` | A one page version safe to share. |

The numbers come from a versioned rubric (eight weighted areas) and sourced facts, never from a
model. An area without enough evidence is reported as such and left out of the total.

## Business plan

| Endpoint | What it does |
|---|---|
| `POST /ventures/{id}/plan/generate` | Write all sections, or `sections: [n]` only; `overwrite_edited` to replace your edits. |
| `GET .../plan` | The latest plan: every section's status, staleness, open questions. |
| `GET/PATCH .../plan/sections/{n}` | Read a section with citations; save an edit (`base_version`, 409 on conflict). |
| `POST .../plan/sections/{n}/assist` | A proposed rewrite (shorten, expand, rewrite_for_investors, simplify, add_data, localise). Saves nothing. |
| `GET .../plan/readiness` | What blocks sharing the plan. |
| `GET .../plan/versions`, `POST .../plan/versions/{v}/restore` | Saved versions and going back. |
| `POST .../plan/export` | Word or PDF (`{"format": "docx"}` or `"pdf"`); a job whose result is an export. |
| `GET /exports/{id}` | The file's details and a fresh signed download link (15 minutes). Files are kept 7 days. |

## Rules enforced

- Sections never contain a figure that is not in the venture's data or a cited source.
- Missing inputs become questions, not text.
- Edited sections survive regeneration. Suggestions are saved only by the member.
- Out of date is per section, from the fields that changed after it was written.

## Not yet in this stage

- Forecast figures in the financial sections (stage T3 supplies the headline).
