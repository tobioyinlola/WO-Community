# 0041. Pitch decks: structured data, patched, with linked figures

Status: accepted (toolkit stage T3, decks)

## Decisions

- **A deck is validated data, not a document.** Slides hold elements from a short allow-list
  (heading, text, bullets, metric, table, image, linked). Every string is plain text, there are no
  styles beyond a named palette and font (plus one accent colour in `#RRGGBB`), and a link address
  the member typed is never stored. An image element refers to an uploaded image by id and must
  carry a description. Anything else is refused by name, so a deck is safe to show, export and
  share without sanitising at the edge.
- **The deck templates (investor pitch 13 slides, demo day 8, accelerator 10, teaser 5) are
  seeds.** The product document's slide structures were not available when this was built; they
  live in the database and are edited through the admin API in T5.
- **Created from the profile, in the founder's words.** Creation copies profile text into slides
  (trimmed at a sentence); it does not call a model. A field the founder has not filled leaves an
  empty element with its source recorded, so the deck check can say what to add.
- **Figures are linked, not copied.** `linked` elements name a forecast figure, a quarterly series,
  the team or the competitors, and are looked up each time the deck is shown, so a slide cannot
  disagree with the forecast. Typed numbers are the founder's and are checked (below).
- **Saves are JSON patch.** `add`, `remove`, `replace`, `move` over `/slides` and `/theme`, all or
  nothing, validated as a whole after applying, with `base_version` and 409 for a stale edit.
  Versions are snapshotted at most every five minutes (or on a labelled save), 30 kept, so
  autosave does not flood history.
- **The deck check is advice.** Empty sources, dense slides, missing notes, missing forecast and
  figures in text that appear nowhere in the profile, forecast or team are listed by slide.
- **A model may reword one slide** (shorten, punchier, simplify) and only returns a proposal. A
  rewrite that introduces a figure not already on the slide or in the venture is dropped.
- **Images** are limited to PNG, JPEG and WebP up to 5 MB, signature checked, scanned, decoded and
  re-encoded to WebP (dropping metadata and anything appended), and kept in the private bucket;
  they are only reachable through short lived signed addresses.
- **Export** to PowerPoint (python-pptx, speaker notes kept, native chart for series) and PDF
  (reportlab canvas) from one layout plan so the two look alike. Drawing the PDF directly avoids
  running a headless browser on workers; the cost is simpler layouts, which suit the fixed set of
  elements.
