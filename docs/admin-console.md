# The admin console

The console lives at `/admin`, in `frontend/src/admin`. It is for people with an admin role
(content editor, community admin, super admin) and opens only after the account has passed two step
sign in.

## Layout

Everything floats on the cream canvas: nothing touches the edge of the window.

- **Sidebar** (`shell/Sidebar.tsx`): a card 264px wide that collapses to an 80px rail. The toggle in
  its header, or the `[` key, switches it, and the choice is kept in this browser. A group opens and
  closes with its chevron (`aria-expanded`), and the group that holds the page being shown opens by
  itself. In the rail each group is one icon with a flyout beside it that lists its pages (it opens on
  hover, focus or click), single items get a tooltip, and a waiting count becomes a dot. Below 1024px
  it becomes a drawer with a scrim, a focus trap and Esc to close.
- **Top bar** (`shell/TopBar.tsx`): a pill-shaped card that stays in view. A search field opens the
  command palette, then a chip with the number of requests waiting for approval, the local time with
  its zone, help, notifications and the account menu (theme, keyboard shortcuts, sign out).
- **Page header**: the shared `PageHeader` restyled in `admin.css`: a small eyebrow, a sentence case
  40px title, a one line subtitle and a toolbar of pill controls on the right.
- **Content**: cards on a `space-4` to `space-6` rhythm, at most 1440px wide.

Pages not built yet appear in the sidebar with a "Soon" tag and open an honest placeholder page
(`Stub.tsx`) instead of being hidden, so the map of the console is complete.

## Pages

| Route | What it does |
|---|---|
| `/admin` | Dashboard: four key figures (one solid forest), a month against last month bar chart with five measures, what needs attention, recent activity |
| `/admin/members` | The master list: filters, saved views, summary strip, sortable and selectable table, bulk actions, columns, density, export |
| `/admin/approvals` | The queue of people asking to join, with tabs and counts, and the slide over request drawer |
| `/admin/settings` | Profile, community (job board), security, roles and team, appearance |
| `/admin/invitations`, `mentors`, `reports`, `jobs`, `wins`, `news`, `events`, `courses`, `email`, `lists` | The other working sections |
| `/admin/design` | Every console component in light and dark, with sample data, for review |

## Keyboard

| Keys | Does |
|---|---|
| `Ctrl K` or `Cmd K` | Open the command palette: pages, quick actions, member search |
| `[` | Collapse or expand the sidebar |
| `?` | List the shortcuts |
| `J` and `K` | Next and previous request (in Approvals) |
| `Enter` | Open the highlighted request |
| `A` | Approve the open request |
| `R` | Start rejecting it; the reason is typed in the drawer |
| `Esc` | Close a panel, drawer or dialog |

## Components

All in `src/admin`, built on the design tokens and the existing design system components.

- `shell/`: `Sidebar`, `TopBar` with `UserMenu`, `CommandPalette`, `Shortcuts`, `nav.ts` (the map and
  who sees what), `prefs.ts` (preferences kept in this browser).
- `kit/`: `KpiCard`, `Delta` (change chip: always an arrow and a sign), `Segmented`, `BarChart`
  (hatched future days, last month marker, tooltip, arrow keys, table view), `DataTable` (TanStack
  Table: server sorting, ticks, sticky header and first column, density), `TableBits` (`StatusChip`,
  `MeterBar`, `FilterChips`, `StatStrip`, `BulkBar`, `Pager`, `ColumnsMenu`, `DensityToggle`),
  `SavedViews`, `undo`.
- `ApprovalDrawer.tsx`, `Settings.tsx`, `AdminDesign.tsx`, and the pages above.

Menus, dialogs and tooltips use Radix primitives, the palette uses cmdk, and icons are Lucide at 1.5px.

### Tokens

Colours, radii, shadows, spacing, type and motion are all tokens (`--bg-*`, `--text-*`, `--border-*`,
`--chart-*`, `--space-*`, `--radius-*`, `--shadow-*`, `--duration-*`). Cards use `--adm-card`, which is
white in the light theme and the surface colour in the dark one. The active navigation pill and the
primary button are `--bg-brand`; the highlighted figure card shows its number in `--text-highlight`.
The stylesheets are `styles/admin.css` (frame), `admin-kit.css` (cards, figures, chart) and
`admin-table.css` (tables, drawer, settings).

## Undo

Approving or rejecting someone cannot be taken back once they have been told, so the decision is held
for 8 seconds with an Undo button on the toast and only then sent (`kit/undo.ts`). The request leaves
the list at once. The hold lives in the browser: closing the tab inside the window drops the decision
instead of sending it.

## Connecting to the API

The console talks to the real API through the typed client in `src/api`; there is no mock layer.
Lists page by `limit` and `offset` and answer `{count, next, previous, results}`. Two endpoints exist
for the console beyond the common ones: `GET /admin/members/{id}/application` (profile, first startup
and timeline of an applicant; each read is logged) and the `ordering` parameter on the members list
(email, joined, last sign in, status).

## Where this differs from the brief, and why

- **Real data, not sample data.** The brief asked for a mock adapter. The back end exists and every
  figure here comes from it, so a mock would only have to be thrown away.
- **A custom chart, not a charting library.** The bar chart is plain HTML and CSS. It is lighter and
  gives exact control of hatched days, markers, the tooltip and keyboard use.
- **No row virtualisation.** The API caps a page at 100 rows, so a table never holds more than that.
- **Fewer filters and columns on Members.** The API filters on search, status, role, email
  confirmation and joined date, and returns name, country and startup. It has no timezone, stage,
  sector, tag, registration type or profile completeness filter, and no group by.
- **Approvals.** Members have no "information requested" state or message flow, so there is no such
  tab or button. Registration does not ask why someone wants to join or where they heard of us, and
  there is no trust score, so the drawer shows what exists: profile, startup, pitch, completeness and
  timeline.
- **Settings.** Only what the system can change is offered: the job board (approval and default
  length), a read only toolkit summary, security, the list of people with a role, and appearance. There
  is no community name, currency or week setting because nothing uses them, and no "delete community" or
  "export everything" because the back end has neither.
- **The Billing page** is not listed, as the brief says to hide it until payments are enabled.
- **Logos.** The logo files have not been supplied, so the name is set in the brand typeface where the
  logo goes (`Logo.tsx` swaps the files in when they arrive).
- **Navigation item radius** uses `--radius-md` (12px) rather than 14px, to stay on the token scale.
