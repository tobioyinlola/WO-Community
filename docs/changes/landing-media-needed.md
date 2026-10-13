# Landing page: images the owner needs to supply

The restyle uses no stock or borrowed images. Where a design treatment has room for a picture, a
clearly marked placeholder is shown until the real one is added.

| Slot | Where | Today | What to supply |
|------|-------|-------|----------------|
| Hero picture | The arched frame that overhangs the hero card (`.site-hero__frame` in `frontend/src/pages/public/Landing.tsx`) | The WO mark on a forest-tinted fill | A portrait photo of members or a founder, about 760 x 950 px (4:5), as WebP, under 150 KB. It is cropped to the arch, so keep faces in the middle. Give it width, height and descriptive alt text; the hero is above the fold, so do not lazy load it. |
| Logo files | `frontend/public/assets/wo-logo-on-light.png`, `wo-logo-on-dark.png`, `wo-mark-on-light.png`, `wo-mark-on-dark.png` | Not present, so the header and footer show the name as text | The brand logo files as described in `frontend/public/assets/README.md`. |
| Footer background (optional) | Behind the giant wordmark in the footer card | None | An optional faded, dark-toned photo or pattern. Not needed; the card looks complete without it. |

The feature cards, events and news have no picture slots: they have no photos in the current design.
