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
