 or # Toolkit Stage T2: validation score and business plan
 or 
 or Design in ADR 0038 (foundations) and ADR 0039 (plan).
 or 
 or ## Validation score
 or 
 or | Endpoint (under `/api/v1/toolkit`) | What it does |
 or |---|---|
 or | `POST /ventures/{id}/score` | Start a score job (202; `Idempotency-Key` honoured; 400 names missing required fields). |
 or | `GET .../score/latest` | The report: overall score and verdict, per area score, evidence, gaps, next actions, disclaimer. |
 or | `GET .../score/history` | Scores over time for a chart. |
 or | `GET .../score/summary` | A one page version safe to share. |
 or 
 or The numbers come from a versioned rubric (eight weighted areas) and sourced facts, never from a
 or model. An area without enough evidence is reported as such and left out of the total.
 or 
 or ## Business plan
 or 
 or | Endpoint | What it does |
 or |---|---|
 or | `POST /ventures/{id}/plan/generate` | Write all sections, or `sections: [n]` only; `overwrite_edited` to replace your edits. |
 or | `GET .../plan` | The latest plan: every section's status, staleness, open questions. |
 or | `GET/PATCH .../plan/sections/{n}` | Read a section with citations; save an edit (`base_version`, 409 on conflict). |
 or | `POST .../plan/sections/{n}/assist` | A proposed rewrite (shorten, expand, rewrite_for_investors, simplify, add_data, localise). Saves nothing. |
 or | `GET .../plan/readiness` | What blocks sharing the plan. |
 or | `GET .../plan/versions`, `POST .../plan/versions/{v}/restore` | Saved versions and going back. |
 or | `POST .../plan/export` | Word or PDF (`{"format": "docx"\|"pdf"}`); a job whose result is an export. |
 or | `GET /exports/{id}` | The file's details and a fresh signed download link (15 minutes). Files are kept 7 days. |
 or 
 or ## Rules enforced
 or 
 or - Sections never contain a figure that is not in the venture's data or a cited source.
 or - Missing inputs become questions, not text.
 or - Edited sections survive regeneration. Suggestions are saved only by the member.
 or - Out of date is per section, from the fields that changed after it was written.
 or 
 or ## Not yet in this stage
 or 
 or - Forecast figures in the financial sections (stage T3 supplies the headline).
