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
- The admin console is not part of this app.

## How it is organised

```
src/api        typed client (openapi-fetch), generated schema, errors, session, data hooks
src/auth       provider and route guards
src/components the design system components
src/layouts    public, auth and app shells
src/pages      one folder per area; pages/launch holds the toolkit
src/ui         shared blocks: loading, empty and error states, forms, toasts, fields
src/lib        formatting (dates, money, time zone) and small helpers
e2e            Playwright tests against the live API
```

Data comes through React Query. Failed saves show the server's own message, and field errors sit
beside the field they belong to. Long running toolkit work is a job: the screen starts it, shows
its progress and can stop it. Edits to shared records send the version they were loaded from, so a
conflict is shown as "this changed somewhere else" with a reload button.

## Tests

- `npm test`: unit tests for components and form helpers.
- `npm run e2e`: signs in through the real form and walks the public site, every member area,
  mentoring and the whole toolkit. Needs the API, a Celery worker and the demo data
  (see the root README).
