# Toolkit Stage T4: pitch decks

Design in ADR 0041.

| Endpoint (under `/api/v1/toolkit`) | What it does |
|---|---|
| `GET /deck-templates` | Investor pitch, demo day, accelerator, teaser. |
| `GET/POST /ventures/{id}/decks` | List; create from a template (filled from the profile). |
| `GET/PATCH/PUT/DELETE .../decks/{id}` | Read; patch operations (`base_version`, 409); rename or mark ready; delete with its images. |
| `GET .../decks/{id}/shown` | The deck with linked figures and signed image addresses, for preview and presenting. |
| `GET .../decks/{id}/check` | Gaps, dense slides, missing notes, figures not found in the profile or forecast. |
| `POST .../decks/{id}/assist` | Reworded text for one slide. A proposal only. |
| `POST .../decks/{id}/export` | `pptx` or `pdf`; a job whose result is an export. |
| `GET .../decks/{id}/versions`, `POST .../versions/{v}/restore` | History and going back. |
| `GET/POST .../decks/{id}/assets`, `DELETE .../assets/{asset}` | Images (5 MB, PNG, JPEG, WebP). |

## Rules enforced

- Only the listed element types and layouts; plain text; named palette and font.
- A patch is all or nothing and validated as a whole; stale versions are 409.
- Figures come from the forecast through links; typed figures are checked.
- Images are re-encoded and private; a venture's erasure removes them.

## Share links

| Endpoint | What it does |
|---|---|
| `POST /ventures/{id}/shares` | Make a read only link to a deck, plan summary or score summary, with an optional password and expiry. The token is shown once. |
| `GET /ventures/{id}/shares` | Your links, with view counts (never the token). |
| `DELETE /ventures/{id}/shares/{share}` | Revoke at once. |
| `GET /public/share/{token}` | Anonymous read. 401 `password_required`, otherwise the content; every other failure is 404. |
| `POST /public/share/{token}` | Open a password link. Ten wrong tries in 15 minutes is 429. |

Design in ADR 0042.
