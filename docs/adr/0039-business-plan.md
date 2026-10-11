# 0039. The business plan: sections, sources and what the model may say

Status: accepted (toolkit stage T2, plan)

## Decisions

- **44 sections in 11 chapters, stored as data.** The product document's section list was not
  available when this was built, so `plans/catalog.py` defines a catalogue that covers a standard
  plan (summary, problem, solution, market, competition, model and go to market, operations, team,
  financials, risk, appendix). It seeds `PlanSectionDef` rows; titles, guidance, required inputs,
  dependencies and an on/off switch are edited in the database (admin API in T5), not in code.
  Replacing the catalogue with the product owner's list is a data change.
- **A section is a short list of plain text blocks** (paragraph, heading, bullets, table) with
  citation numbers, validated by `plans/content.py`. No markup is stored, so a section can be
  shown, exported and shared without sanitising at the edge.
- **No invention.** A section whose required inputs are missing is not written; it is marked
  `needs_input` with a question for the founder. For the rest, the model is given only the fields
  the section depends on and the facts research found, and every figure in its answer is checked
  against those. A figure that appears in neither is removed: the section is asked for again once
  with a note, and any sentence still carrying it is dropped. Small numbers and years are not
  treated as claims.
- **Citations come from facts, not from the model's memory.** The model cites by position in the
  list of facts it was shown; positions outside the list are dropped. Each citation links to a
  stored source (URL, publisher, retrieval date).
- **The member's words win.** A section the member saved is `edited` and is kept on regeneration
  unless they pass `overwrite_edited`. Rewrite actions (shorten, expand, rewrite for investors,
  simplify, add data, localise) return a proposal and save nothing; accepting one is an ordinary
  save with its citations.
- **Staleness is exact per section.** Each section records the profile version it was written
  from; a section is out of date if a field it depends on changed in a later version, or the
  forecast it uses has a newer version. The venture-level output state still drives the board.
- **Concurrency.** A section save carries `base_version`; a mismatch is 409.
- **Versions.** Each generation, partial rewrite and restore saves a snapshot (20 kept,
  `PLAN_VERSIONS_KEPT`). Restoring first saves the current text, so it can be undone.
- **One research pass per plan.** Facts are gathered once for the topics all sections need, from
  the sector and regions only (the same rule as the score), and shared across sections.

## Consequences

- The forecast headline comes through `forecasts.selectors.headline` and is `None` until the
  forecast tool exists; financial sections then say what is missing rather than inventing numbers.
- Executive summary is written last from the finished sections and passes the same figure check.
