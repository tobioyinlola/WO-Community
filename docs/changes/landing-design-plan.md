# Landing page design upgrade: plan

A restyle of the public landing page (`frontend/src/pages/public/Landing.tsx`) and the public site
header and footer (`frontend/src/layouts/PublicLayout.tsx`, shared with Explore, News and the legal
pages). The sections, their order, the copy, the links, the data fetching and the routes do not change.

The reference screenshots and the design system file were not attached to the request, so the
treatments follow the written brief and the design system already in the repository
(`frontend/src/styles/tokens.css`, `docs/design-decisions.md`). Only brand tokens are used: forest, cream,
sand (`--cream-300`), gold, white, Hanken Grotesk, Lucide icons.

## What exists today

| Order | Section | Content |
|-------|---------|---------|
| 1 | Header (shared) | Forest band: logo, Home / Explore / News, Sign in, Request access |
| 2 | Hero | Eyebrow, headline with one gold word, paragraph, two buttons, an arched frame holding the WO mark |
| 3 | What you get | Rule and eyebrow, headline, six feature cards (icon, title, text) |
| 4 | Membership | Eyebrow, headline, four bullets, a forest card with a button |
| 5 | Coming up, From the community | Section titles with links, three event cards, three news cards |
| 6 | Footer (shared) | Logo and line, three link columns, copyright |

There are no stats, steps, testimonials, FAQ, problem and solution blocks or carousels, so those
treatments are not applied and nothing is added in their place.

## Treatment per section

| Section | Treatment | Files |
|---------|-----------|-------|
| Header | Floating pill on the cream page: border, forest fill; after 24 px of scroll a blurred, slightly more transparent fill. Gold pill button gets an arrow in a circle. The mobile menu keeps its behaviour and opens as a rounded card. | `PublicLayout.tsx`, `landing.css` |
| Hero | The hero content sits inside one large forest card (`radius-xl`). Fluid display headline, gold word kept. Primary button gold with an arrow circle, secondary outlined, both pills. The arched frame overlaps the card's lower edge and has a gold line drawn around it (inline SVG, drawn once on load, static for reduced motion). | `Landing.tsx` (wrappers), `landing.css`, new `ArrowCircle` |
| What you get | Heading highlight moves from gold text on cream to a forest chip. Cards become tall rounded cards with a circular icon badge; lift on hover only on devices that hover. Cards reveal on scroll, 60 ms apart. | `Landing.tsx`, `landing.css`, new `Reveal` |
| Membership | Becomes the call to action band: one large sand card with the eyebrow, display headline and bullets, and the existing forest card as the highlight card with a pill button and arrow. | `Landing.tsx` (class names), `landing.css` |
| Events and news | Same card language, large radius, hover lift, reveal. | `landing.css` |
| Footer | A large rounded forest card with the existing link columns and copyright, and a giant faded WO COMMUNITY wordmark across the bottom (`aria-hidden`, top to bottom fade). | `PublicLayout.tsx`, `landing.css` |

## Small structural additions (each minimal, listed in the report)

- A wrapper `div` for the hero card, and one for the arch frame and its line graphic.
- An arrow circle `span` inside buttons that already exist.
- A `Reveal` wrapper is the existing grid element itself (a `div` that gains an observer).
- One `aria-hidden` element in the footer for the giant wordmark.

## Global

- Reveal once on scroll (fade and 12 px rise), children 60 ms apart; none for reduced motion.
- Pill buttons with a visible focus ring, arrow nudges 2 px on hover with no layout shift.
- Card lift: translateY -2 px and one shadow step, only under `(hover: hover)`.
- Fluid type with `clamp()`, 16 px side gutters on mobile, no horizontal scroll from 360 to 1536 px.
- `prefers-reduced-motion`: no reveals, no line drawing, no transitions.

## Not applied (no matching section)

Stats bento, problem and solution cards, steps with a connecting line, testimonials, FAQ accordion,
carousel with arrows, round social icon buttons (the footer has no social links to restyle).

## Round two (added on request)

The treatments listed above as not applied were added afterwards, along with the suggestions: stats
bento (from a new public counts endpoint), the feature cards as a linked carousel, steps, on your own
or in the community, a questions accordion, member quotes and footer social buttons (both shown only
when real content is supplied), a meta description and `robots.txt`. See the report for details and
for which words are new and need the owner's approval.
