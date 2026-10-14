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

## Structure check (the first restyle; round two adds sections, see below)

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

## Round two: the treatments that had no section, and the suggestions

Added at the request of the owner, in page order: hero, **numbers**, **what you get (carousel)**,
**steps**, **on your own or in the community**, membership band, **member quotes (when there are
any)**, events and news, **questions**, footer (with **social buttons** when there are links).

| Addition | What it is | Where the content comes from |
|----------|------------|------------------------------|
| Numbers bento | Four rounded tiles with very large numerals: one soft gradient tile, one white, two sand. They count up once when scrolled into view (the real figure is always in the page for screen readers; static with reduced motion). Each tile links to what it counts. | A new public endpoint, `GET /api/v1/public/stats`, that counts what a visitor can see: startups listed, founders listed, courses open to visitors and open roles (the same lists as the sitemap). Nothing about individual members. A zero count is left out, and the block disappears if fewer than two remain. |
| Feature carousel | The six cards are now a scroll-snap row with a partly visible next card, round Previous and Next buttons, arrow keys and touch. Each card has a picture slot, a tag chip, a circular icon badge, the same title and text, and a pill button with an arrow that goes to the page it is about: Explore founders, courses, jobs or events, and Request access for mentors and the toolkit (which are for members). | The existing card copy. Tags are the area names (Directory, Mentors, Launch toolkit, Courses, Jobs, Events). |
| Steps | Four numbered steps joined by a thin line (vertical on phones). | Restates the sign up and approval flow the site already describes. |
| On your own, or in the community | Three rows: a muted dark card with a number and a red cross, an arrow, and a bright gold card with a number and a check; stacked on phones. | The right hand side is the existing feature copy. **The left hand side (the three "on your own" sentences) is new wording and should be read and approved by the owner.** |
| Questions | A rounded accordion: circular chevrons, a dark filled chevron on the open one, one open at a time, smooth height, `button`, `aria-expanded` and `aria-controls`. | Six answers, each restating something the site already says (who can join, what happens after a request, profile control, mentors, jobs, support). No timings, prices or promises were invented. |
| Member quotes | A carousel of rounded quote cards. | **Nothing is shown yet.** There are no real quotes to use and none were invented. The section appears when real, approved quotes are added to `TESTIMONIALS` in `frontend/src/pages/public/landingContent.ts`. |
| Footer social buttons | Round icon buttons that open in a new tab. | **Nothing is shown yet.** The community's own addresses were not available. Add them to `SOCIAL_LINKS` in the same file (LinkedIn, X, Instagram, YouTube are supported). |
| Meta description | A description for search results in `index.html`. | Taken from the README's own description. |
| `robots.txt` | Allows the public site; keeps crawlers out of `/app`, `/admin` and shared links. | |

Tests added: unit tests for the accordion, carousel, count-up, the numbers (shown, linked, hidden at
zero), the feature links, quotes and social links (absent, then present), and a content guard that any
future quote or link is complete and https; browser tests for the numbers, the carousel with buttons
and arrow keys, the feature links, the one-at-a-time questions, and the meta description and
`robots.txt`. The width, axe and contrast tests cover the new sections in both themes.

Measured again after round two (Lighthouse mobile, median of five runs): performance **93** (91
before the redesign), accessibility **100** (100), best practices **96** (96), SEO **100** (82; the
meta description and `robots.txt` fixed it), layout shift **0** (0.012), largest contentful paint
2787 ms (2786 ms). Axe color-contrast: 0 violations and 134 pairings passed in each theme. The
undecided ones are decorative (the hero frame wordmark, the faded footer wordmark) or sit on the soft
gradient tile, which was worked out by hand: text on that tile is at least 6.3:1 in the light theme and
6.9:1 in the dark theme.

The original page is intact: every heading, link, button and paragraph of the first version is still
present, and the title is unchanged. The additions are listed by `tools/landing-capture.mjs`.

## Still not done

- Round social icon buttons and member quotes need real content (see above).
- Picture slots on the feature cards still show the placeholder (see the media list).

## Unfinished

- The reference screenshots were not available, so proportions were set from the written brief.
- The hero picture and the logo files still need to be supplied (see the media list).
