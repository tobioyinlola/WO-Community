# Landing page design upgrade: report

A restyle of the public landing page and of the header and footer it shares with Explore, News and the
legal pages. Plan: [landing-design-plan.md](landing-design-plan.md). Pictures still needed:
[landing-media-needed.md](landing-media-needed.md).

The reference screenshots and the design system file were not attached to the request. The treatments
follow the written brief and the design system in the repository (`tokens.css`, `docs/design-decisions.md`).
If the screenshots are sent, the spacing and proportions can be tuned against them.

## What changed, per section

| Section | Change |
|---------|--------|
| Header | A floating pill on the cream page with a hairline border. After 24 px of scroll it takes a blurred, slightly see-through fill and a shadow. The gold button has an arrow in a circle. The mobile menu behaves as before and opens as a rounded card. The wordmark fallback no longer shows a blue link underline. |
| Hero | The content sits in one large rounded forest card. Fluid headline (one gold word, as before), pill buttons: gold with an arrow circle, and outlined. The arched frame overhangs the card's lower edge and has a gold line drawn around it once on load (static with reduced motion). |
| What you get | The highlight in the heading is a forest chip with a gold word, not gold text on cream. The six cards are tall and rounded with a circular forest badge, lift 2 px on hover (only where hover exists) and appear on scroll, 60 ms apart. |
| Membership | Now the call to action band: one large sand card holding the eyebrow, headline and bullets, with the existing forest card as the highlight card and an arrow button. |
| Coming up, From the community | Same card language: large radius, hover lift, reveal on scroll. |
| Footer | A large rounded forest card with the same link columns and copyright, and a giant faded WO COMMUNITY wordmark at the bottom. The logo fallback text is now readable on the card (it was forest on forest in the light theme). |

Global: buttons are pills with a visible focus ring; the arrow nudges 2 px on hover without moving the
layout; fluid type; reveals and drawing are off under `prefers-reduced-motion`.

## Files

- Changed: `frontend/src/pages/public/Landing.tsx`, `frontend/src/layouts/PublicLayout.tsx`,
  `frontend/src/main.tsx` (one import), `frontend/index.html` (preload of the 800 and 400 weights of the
  display font), `frontend/eslint.config.js` (Node globals for the review tools).
- New: `frontend/src/styles/landing.css`, `frontend/src/ui/Reveal.tsx` (+ test),
  `frontend/src/ui/ArrowCircle.tsx`, `frontend/e2e/landing.spec.ts`,
  `frontend/tools/landing-capture.mjs`, `frontend/tools/landing-contrast.mjs`.
- Docs: this report, the plan, the media list, and `landing-screenshots/`.

## Structure check

`tools/landing-capture.mjs` records every heading, link, button and paragraph of the header, the page
and the footer. Before and after are **identical**
(`landing-screenshots/before-structure.json`, `after-structure.json`): same sections in the same
order, same copy, same links and routes, same data fetching. The small structural additions, all
presentational:

1. A wrapper `div` around the hero content (the card), and a `div` around the arched frame that also
   holds the gold line `svg`.
2. An arrow circle `span` inside five buttons that already existed (hidden from assistive technology).
3. The three grids and the membership split are now `Reveal` wrappers: the same `div` with scroll
   behaviour, nothing added.
4. A wrapper `div` around the footer content (the card) and one `aria-hidden` `div` for the giant wordmark.

## Checks

| Check | Result |
|-------|--------|
| Type check, lint, unit tests (138), production build | pass |
| New Playwright spec `landing.spec.ts` (14 tests) | pass: content intact, no sideways scroll at 360, 768, 1024, 1280 and 1536 px, axe at 360 and 1440 px in both themes, floating header state, mobile menu by keyboard, Tab walk with a focus ring on every stop, reduced motion |
| Existing `public-and-auth` and `accessibility` specs, run with the new spec (33 tests) | 32 pass, including the width and axe audit of `/` and every other public page in both themes. The one failure, "a member awaiting approval sees the holding page", is dev data: `pending@demo.test` was approved by earlier test runs, so it no longer gets the holding page. It does not touch the landing page. |
| Axe color-contrast, both themes, 1440 px | 0 violations, 75 pairings passed. Undecided (axe cannot compute these): the decorative "WO" in the hero frame (cream on the frame fill, about 4:1, large text, was already so), and the giant footer wordmark (decorative, `aria-hidden`, faded on purpose) |
| Keyboard walk | Header links, buttons and the menu button all take focus in order with a visible ring; the mobile menu opens and closes with Enter |
| Reduced motion | No pending reveals, no line animation, no hover lift |

### Lighthouse, mobile profile, median of five runs (built files, same server setup)

| | Before | After |
|---|---|---|
| Performance | 91 | 94 |
| Accessibility | 100 | 100 |
| Best practices | 96 | 96 |
| SEO | 82 | 82 |
| Largest contentful paint | 2786 ms | 2654 ms |
| Layout shift | 0.012 | 0 |

The first measurement after the restyle showed performance 87 and layout shift 0.115: the hero picture
moved when the display font swapped in. Preloading the font fixed it.

### Screenshots

`landing-screenshots/`: `before-` and `after-` at 360, 768 and 1440 px, light and dark, plus
`after-360-menu-open.png`. The app is light only (a decision in `ThemeProvider`), so the dark theme is
checked by setting `data-theme="dark"` directly; no visitor can reach it today.

## Not applied (no matching section, and nothing was added)

Stats bento, problem and solution cards, steps with a connecting line, testimonials, FAQ accordion,
carousel with round arrows, round social icon buttons. The six feature cards have no links, so they do
not get the tag chip and pill button of the reference list cards. This also means the carousel,
accordion and count-up code the brief mentions does not exist, and so has no tests.

## Suggestions (structural, not made)

- A stats row (members, mentors, events) would suit the bento treatment, if real figures can be shown.
- A short FAQ would use the accordion treatment and could answer how admission works.
- Social links in the footer, if the community has channels, for the round icon buttons.
- Link each feature card to the page it describes (Explore, Learn, Jobs, Events) so they can carry the
  pill button with an arrow.
- SEO is 82 before and after. Lighthouse names two causes: the page has no meta description, and there is
  no valid `robots.txt` (the site answers that address with the app's page). Adding both would raise it.

## Unfinished

- The reference screenshots were not available, so proportions were set from the written brief.
- The hero picture and the logo files still need to be supplied (see the media list).
