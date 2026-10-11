# Front end design decisions

Notes where the brief left a choice. Everything else is built exactly as the design system says.

## Setup

- **Location:** `frontend/` in this repository, so the API and the web app share history and CI.
  The brief calls the back end a separate project; moving the folder to its own repository later
  only needs the `web` job in `.github/workflows/ci.yml` to move with it.
- **Fonts:** Hanken Grotesk (400 to 800) and JetBrains Mono (500) are self-hosted from the
  `@fontsource` packages instead of the Google Fonts link, so production needs no change to the
  content security policy. The family names are unchanged, so the tokens work as written.
- **Tailwind:** not used. Components use the class layer in `components.css`.
- **Component names:** the brief lists twelve components. `Input` also exports `Textarea` and
  `Select`, and `Checkbox` also exports `Radio`, `Switch` and `ChoiceGroup`.

## Added rules (all tokens, in `src/styles/extras.css`)

- **Modal entrance:** rise 12px and fade over `duration-slow` with `ease-emphasized`, disabled under
  `prefers-reduced-motion`; full width with rounded top corners under 640px, as the brief says.
- **Top bar under 768px:** the mark alone and the links behind a menu button. The brief says the bar
  "collapses to mark plus menu"; the disclosure panel is the simplest accessible form of that.
- **Page header rule:** `wo-page-rule`, a `stroke-3` rule with a right-aligned eyebrow, used by
  every page.
- **Display steps:** the three breakpoint steps for `display-*` and `stat-xl` from section 4.
- **Layout helpers:** `wo-container`, `wo-stack`, `wo-row`, `wo-grid` for page composition.

## Open items

- **Logo files** were not supplied with the brief. `TopNav` takes the four paths and falls back
  to the name in text if a file is missing, so nothing breaks. Add the files to `public/assets`.
- **Icons:** `lucide-react` (the matching set) is installed and used for the menu button only so
  far; filled icons on a sand tile are added with the first screen that needs them.
- **Contrast** of the token pairs was taken from the brief; the screens built later should be
  checked in both themes before release.

## Screens (member app and toolkit)

- **Roles:** the API has no role field. Role words (Founder, Operator, Investor, Mentor) are shown
  from a member's badges and what they are open to, and are never invented.
- **Legal pages** are short summaries with a note that the full text is issued by the company; the
  full documents were not supplied.
- **Logos** are still missing; every place that shows one falls back to the name in text.
- **Emoji:** none. Reactions use icons and words.
- **Deck and prototype previews** draw colours from the deck's own saved palette, because that is the
  member's content, not interface chrome. Everything around the preview uses tokens.
- **Forecast chart:** a plain SVG with two lines (solid for revenue, dashed for cash) in token
  colours, with a text label and a table of the 24 months as the accessible equivalent.
- **Alert and empty state bodies** are `div`s rather than `p`s so they can hold lists and several
  paragraphs without invalid markup.
- **Money** is typed in whole units and stored in minor units; dates read "10 Oct 2026", times use
  the 24 hour clock with a zone ("15:00 WAT"), and the currency symbol comes before the amount.
- **Not yet built:** the admin console, and the toolkit's prototype editor beyond wording changes
  (structure editing is left to templates and drafts).
