# Toolkit Stage T1: the venture profile

Design in ADR 0038.

| Endpoint (under `/api/v1/toolkit`) | What it does |
|---|---|
| `GET/POST /ventures` | List and start ventures (3 at a time by default; `from_startup_id` copies a startup profile). |
| `GET/PATCH/DELETE /ventures/{id}` | Read, rename or archive, delete (erased after a 14 day grace period). |
| `POST /ventures/{id}/restore` | Undo a delete inside the grace period. |
| `GET /ventures/{id}/export` | Everything held about the venture as one JSON document. |
| `GET /ventures/{id}/package` | The board: completeness, what is missing for a score, each output's state. |
| `GET/PATCH /ventures/{id}/profile` | Read; save some fields (`{"fields": {...}, "base_version": n}`). |
| `POST .../profile/import-startup` | Fill from a startup profile the member owns or is on the team of. |
| `GET .../profile/versions` | The history of changes. |
| `POST .../profile/suggest` | Up to three wordings for a text field. Nothing is saved. |
| `POST .../profile/fill-from-text` | Proposed fields from a paragraph, already validated. Nothing is saved. |
| `/ventures/{id}/competitors`, `/team` | Rows beside the profile (up to 8 and 20). |
| `GET /jobs/{id}`, `POST /jobs/{id}/cancel` | Poll and stop jobs. |

## Rules enforced

- Six fields are required before a score can run: name, startup idea, target regions, problem,
  solution, revenue models. They are not required to *save* a step.
- Target countries are allowed only with Africa among the target regions and must be African.
- Every value is validated and cleared with null or a blank; markup is removed from text.
- Provenance is recorded per field (`member`, `imported`, `ai_suggested_accepted`). Suggestions
  and proposals are never written without the member's own save.
- Changing a field marks the outputs made from it `needs_refresh` and lists the fields.
- A stale `base_version` is 409. Every change is a numbered version.
- Another member's venture does not exist (404), including for writes.

## Deferred

- Sharing a venture with a mentor account (`VentureGrant`) is modelled and honoured by reads; the
  endpoints that create grants arrive with the partner (Stage T4).
