# WO Community web

React 18 + TypeScript on Vite. The look is the design system in `docs/design-decisions.md`:
tokens in `src/styles/tokens.css`, the component classes in `src/styles/components.css`, and typed
components in `src/components`.

```
cd frontend
npm install
npm run dev        # http://localhost:5173, API requests under /api go to localhost:8000
npm run lint && npm run typecheck && npm test && npm run build
```

Open `/design` to see every component in the light and dark themes side by side.

## Rules

- Components use semantic tokens only (`--bg-*`, `--text-*`, `--border-*`, `--action-*`). The lint
  rule rejects a raw hex colour in code.
- Theme is `data-theme="light|dark"` on `<html>`; it follows the system until a member chooses,
  and the choice is kept in `localStorage` under `wo-theme`.
- Fonts are self-hosted from npm (`@fontsource`), so no request goes to a font service.
- Logos live in `public/assets` (see the README there).

## What is in the app

- **Public site**: landing, explore, news, legal pages, request access, sign in and recovery.
- **Member app** (`/app`): home, feed, directory, jobs, events, learning, mentoring, news,
  notifications, profile and settings.
- **Launch toolkit** (`/app/launch`): ventures, and for each one the overview, profile, score,
  business plan, forecast, pitch decks, prototypes, venture partner and sharing. A shared link opens
  at `/share/:token` for people who are signed out.
- **Admin console** (`/admin`, in `src/admin`): overview, members, invitations, mentor applications,
  reports, jobs and wins review, news, events (with attendees and check in), courses (modules and
  lessons), email (newsletters, audiences, templates), the lists members choose from (sectors,
  stages, skills), and security. It opens only for admin roles, and only after the account has passed
  two step sign in (the screen walks a new admin through setting it up). Sensitive actions ask for a
  fresh code when the server wants one. Paid courses, demo day pitch slots and newsletter images
  are not in the console yet.
- `npm test`: unit tests for components and form helpers.
- `npm run e2e`: signs in through the real form and walks the public site, every member area,
  mentoring, the whole toolkit and the admin console (it works out the demo admin's authenticator
  codes itself). Needs the API, a Celery worker and the demo data (see the root README).
- `e2e/accessibility.spec.ts` checks every screen with axe (WCAG 2.2 AA rules a tool can judge)
  and for sideways scrolling at 360, 768, 1024 and 1280 px, in light and dark. It does not replace
  trying the app with a screen reader.
