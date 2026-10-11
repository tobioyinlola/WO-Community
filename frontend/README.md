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
