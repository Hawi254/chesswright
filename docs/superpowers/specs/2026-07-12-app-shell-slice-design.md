# App-shell slice — design

Status: approved by user, pending self-review + doc-review gate
Date: 2026-07-12
Branch/worktree: `worktree-frontend-spike` (this worktree), continuing directly on
top of commit `ef5c2a8` — not a new branch. Phase 3 of
`docs/scoping/frontend-rewrite-development-path-2026-07-12.md`.

## Context

Phases 1 and 2 of the frontend rewrite are both done: React + Vite was chosen over
Svelte/SolidJS (`docs/scoping/frontend-stack-bakeoff-2026-07-12.md`), and the
frozen-subprocess fork bomb in `api/spike_launcher.py` is fixed and live-verified
against the real frozen binary. Phase 3 — the vertical-slice migration loop — starts
now, with the app shell (topbar, navigation, command palette) as its first slice, per
the roadmap doc's explicit sequencing: this is the actual forcing requirement that
started the whole rewrite (BRIEF §25's finding that Streamlit's custom-component
iframe sandbox can't observe a global ⌘K keydown), so it needs to be proven against
the real chosen stack before any other page is built on top of it.

The roadmap doc deliberately left two things for this brainstorm to resolve rather
than deciding them speculatively: which performance angles apply to this specific
slice, and how `desktop_app.py` serves a mix of already-ported and not-yet-ported
pages during the migration. Both are resolved below.

The existing spike (`api/`, `frontend/`) is the starting point, not a discard: this
slice extends it (adds routing, real component structure, the nav/palette chrome)
rather than restarting from zero. The spike's flat `App.jsx` (fetches 2 Overview
endpoints, renders a single unrouted page) will be **removed** as part of this slice
and its real content deliberately NOT ported forward yet — see Non-goals.

## Goals

- Build a real React app shell — topbar + grouped sidebar navigation + a working
  global ⌘K command palette — that proves Streamlit's actual failure mode (iframe-
  sandboxed custom components can't observe a keydown fired elsewhere on the page)
  does not recur in the new stack, including the specific case of focus being inside
  a text input elsewhere on the page when ⌘K is pressed.
- Reproduce the existing navigation information architecture exactly (same 3 groups —
  Career/Explore/App — same 19-page list and titles/url_paths `dashboard/app.py`
  already defines) rather than redesigning it, since this slice's job is proving the
  tech stack, not revisiting IA.
- Establish the patterns every later Phase 3 page slice will inherit: route-based
  code-splitting, the dev-parallel verification workflow, and reusing
  `dashboard/data/*.py` as the single source of truth for anything currently
  duplicated between the Streamlit app and the new shell.
- Resolve the coexistence question for the whole migration period (see Decisions
  below), not just for this slice.

## Non-goals (explicit)

- **No real page content**, including Overview. The spike's `App.jsx` already renders
  real Overview data against real endpoints, but porting that into the new shell as
  part of this slice would blur the slice's actual scope (proving the shell/palette
  mechanism) with the next slice's scope (porting a real page, per the roadmap's own
  risk-ordering: Overview first because it's already spiked and cheap). Every route
  this slice creates renders a trivial placeholder component instead.
- **No job-status or active-profile indicators in the topbar.** The current Streamlit
  sidebar's `_sidebar_job_status()` and Pro-profile banner are real features, but
  wiring them needs new backend endpoints this slice has no other reason to add. The
  topbar reserves visual space for a future status slot; nothing renders there yet.
- **No dynamic search** (openings/findings fuzzy-matching via
  `dashboard/data/search.py`'s `build_dynamic_candidates`). ⌘K in this slice searches
  only the static page list and the 6 static Settings-section entries — confirmed
  with the user as the right scope for this slice; the Streamlit sidebar's existing
  dynamic search keeps serving that need until whichever later slice ports Settings/
  the relevant data pages.
- **No `desktop_app.py` changes.** See Decisions — this slice is built and verified
  entirely through the standalone dev workflow (`npm run dev` + `api/spike_launcher.py`),
  the same pattern the original spike used. `desktop_app.py` keeps pointing at
  Streamlit unchanged.
- **No global state management library.** Plain React state/Context covers this
  slice's needs (palette open/closed, active nav group). Not picked ahead of a page
  slice that actually needs shared cross-component state (e.g. SRS drills).
- **No TypeScript strictness overhaul of the existing spike code** beyond what this
  slice's own new files need — the spike's `api/` Python code is untouched except for
  the one new endpoint below.

## Decisions

### Coexistence shape: dev-parallel, milestone cutover

Evaluated against `desktop_app.py`'s actual current architecture (read in full for
this brainstorm): exactly one server subprocess, one pywebview window, one URL. Its
native File-menu navigation (`go_to()`) drives `window.evaluate_js("window.top.location.href
= ...")` hardcoded to Streamlit's flat `url_path` scheme — there is no existing
multi-server or multi-window pattern in this codebase to build on.

Three shapes were on the table:
- **Atomic cutover at 100%**: zero coexistence engineering, but zero visible/dogfood
  benefit until the entire 21+ page migration finishes.
- **Iframe-shim** (new shell primary, old Streamlit pages iframed inside it): rejected.
  Keydown events fired while focus is inside an iframe do not bubble to the parent
  document — this reintroduces the exact bug the whole rewrite exists to fix, except
  now scoped to "whenever focus is on any not-yet-ported page," which is most of the
  app for most of the migration. Also requires running two Python server processes
  simultaneously in the packaged app (doubling the Phase 2-style spec-bundling
  surface — see `frontend_rewrite_forkbomb_fixed_2026-07-12` memory for how much
  hidden bundling surface one FastAPI service already exposed), and breaks `go_to()`'s
  hardcoded URL-scheme assumption.
- **Dev-parallel, milestone cutover (chosen)**: every Phase 3 slice is built and
  live-verified against the standalone dev workflow already proven in the spike
  (`npm run dev` on the frontend + `python3 api/spike_launcher.py` for the backend,
  entirely outside pywebview) — zero `desktop_app.py` changes per slice. Real,
  usable dogfood value exists immediately (just run the dev servers) without waiting
  for the full migration. `desktop_app.py`'s single URL only gets swapped from
  Streamlit to the built React static bundle once a real judged milestone is reached
  (not literally 100% of 21 pages) — a decision made once, at that point, with its
  own scoped design rather than smeared across every slice now.

### Performance bar for this slice

Of the roadmap's five flagged angles, two apply here:
1. **Route-based code-splitting** (`React.lazy` per page component), set up now as
   the pattern every later slice inherits — even though today's stub pages are tiny,
   getting the splitting boundary right per-route now avoids a retrofit later.
2. **A measurement checkpoint**: Vite dev-server time-to-interactive and
   `/api/nav/pages` response latency, continuing BRIEF §6aj's measurement discipline.
   This is **not** a frozen-build cold-start measurement — no packaged integration
   exists yet under the dev-parallel decision above, so there is nothing frozen to
   time. Frozen cold-start is deferred to whenever the milestone cutover actually
   happens.

List/table virtualization and re-render-storm avoidance are page-content problems
with no evidence they apply to a shell with no data-heavy pages — deferred to the
board-heavy slices (variation explorer, SRS drills, Opening Tree) where they're
actually real.

### Styling: Tailwind + shadcn/ui

Chosen over hand-rolled CSS for the largest ready-made component/primitive coverage
for a 21+ page build (per the Phase 1 bake-off's ecosystem reasoning) and because
shadcn's `Command` component is a ready-made `cmdk` wrapper — the least custom code
for the exact ⌘K litmus test this slice exists to prove. `dashboard/theme.py`'s
palette is ported into `tailwind.config.js` as named colors for visual continuity
with the still-Streamlit pages during the dev-parallel period:

| Token | Hex |
|---|---|
| `bg` | `#14181F` |
| `bg-secondary` | `#1E2530` |
| `accent-gold` | `#C19A4B` |
| `positive` | `#6FA98C` |
| `negative` | `#B0584F` |
| `text` | `#E8E6E1` |
| `text-muted` | `#E8E6E1` at ~60% opacity |

### Routing: React Router, URL-based

Real paths per page (`/overview`, `/patterns`, etc.), copied exactly from the
existing `url_path`s so a later `desktop_app.py` cutover needs no path remapping and
`go_to()`-style menu navigation stays possible without rework. Gives working browser
back/forward and makes each page directly loadable/testable by URL — both exercised
by this slice's Playwright verification (see Testing).

## Architecture

New/changed files, additive to the existing spike:

**Backend** (`api/main.py`): one new endpoint.
```
GET /api/nav/pages -> data.PAGE_CANDIDATES + data.SETTINGS_CANDIDATES
```
A thin wrapper, no modification to `dashboard/data/search.py` — its existing shape
(`{category, title, url_path}` dicts) is already exactly what the frontend needs, so
per this project's per-slice discipline ("only touch `dashboard/data/*.py` if a
function's shape is genuinely awkward over HTTP"), nothing there changes.

**Frontend** (`frontend/src/`), replacing the spike's flat `App.jsx`:
- `main.tsx` — React Router setup, route table generated from the 19 pages'
  `url_path`s (fetched from `/api/nav/pages` at startup, falling back to a bundled
  static copy — see Error handling).
- `navConfig.ts` — the one hand-maintained piece: `url_path -> "Career" | "Explore" |
  "App"` group bucketing, since that grouping only exists in `dashboard/app.py`'s
  literal `st.navigation({...})` dict, not in any data-layer structure. Comment flags
  it as the thing to keep in sync if `app.py`'s grouping changes.
- `components/Shell.tsx` — topbar + sidebar layout wrapper, renders `<Outlet />` for
  the active route.
- `components/Sidebar.tsx` — the 3 nav groups, active-route highlighting via
  `useLocation()`.
- `components/CommandPalette.tsx` — shadcn `Command` component wrapping `cmdk`,
  global `⌘K`/`Ctrl+K` listener (registered on `document`, not scoped to any
  component — the specific thing that must work regardless of where focus is),
  fuzzy-filters the same page+settings candidate list the sidebar uses, navigates via
  `useNavigate()` on select.
- `pages/PageStub.tsx` — one generic placeholder component parameterized by page
  title, used for all 19 routes.
- `lib/theme.ts` — the palette table above, as Tailwind theme extension.
- `lib/navCandidates.ts` — the bundled static fallback copy of the page/settings
  list (see Error handling).

**Removed**: `frontend/src/App.jsx` (spike-only, superseded by the routed shell).

## Testing / verification

**Vitest unit tests** (new to this repo — first frontend test setup, ships with the
Vite toolchain so no new build-time dependency): nav-group assembly (`navConfig.ts`
logic), ⌘K fuzzy-filter behavior on the static candidate list.

**Playwright live-verification** (this project's standing discipline, matching
`verify-live-dashboard`'s pattern but against the new stack): run against the real
dev API (`api/spike_launcher.py`, unfrozen) —
- Sidebar renders all 19 pages in the correct 3 groups, matching `dashboard/app.py`'s
  `st.navigation({...})` dict exactly.
- ⌘K opens on `Cmd/Ctrl+K` **while focus is inside a text input elsewhere on the
  page** — the literal case Streamlit's iframe sandbox fails, and the actual reason
  this slice exists.
- Typing in the palette fuzzy-filters the list; Enter/click navigates and closes the
  palette.
- Browser back/forward moves between visited pages correctly.
- Loading a page's URL directly (e.g. navigating straight to `/patterns`, not via a
  click) renders the correct stub — proves real routing, not client-side-only state
  that happens to look like routing.
- Zero console errors across all of the above.

## Error handling

The only backend dependency this slice has is `/api/nav/pages`. If it's unreachable
(dev API not running), the shell falls back to `lib/navCandidates.ts`'s bundled
static copy of the same list, with a `console.warn` in dev — the shell must never
blank-screen or show an infinite spinner just because the API isn't up, since nav/
palette chrome has no real reason to depend on live data.

## Success criteria

- `npm run dev` + `python3 api/spike_launcher.py` together render a working shell:
  correct grouped nav, correct routes, working ⌘K including the focus-inside-input
  case.
- All Playwright checks above pass with zero console errors.
- Vitest unit tests pass.
- `docs/scoping/frontend-rewrite-development-path-2026-07-12.md` updated with a Phase
  3 app-shell-slice-done entry once implementation lands.

## Open risks / carried forward

- The milestone-cutover point (when `desktop_app.py` actually swaps its URL to the
  React build) is intentionally not decided here — it depends on how much of the
  migration is done, a future call.
- `navConfig.ts`'s hand-maintained group bucketing can drift from `app.py` if a page
  moves groups without the frontend being updated to match — accepted as a small,
  low-frequency-change piece of duplication rather than justifying a new backend
  field for something that's changed rarely in this project's history.
- Windows/macOS packaging validation remains untested (Linux dev machine only) —
  unaffected by this slice since it makes no packaging changes.
