# App-Shell Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Phase 3 app-shell slice — a React topbar/sidebar/command-palette
shell that proves the new stack can do a real global ⌘K (the thing Streamlit's
iframe-sandboxed custom components can't), reproducing the existing 3-group/19-page
navigation exactly, with every route rendering a placeholder stub (no real page
content yet).

**Architecture:** FastAPI gains one thin new endpoint wrapping the existing
`dashboard/data/search.py` candidate lists. The frontend is rebuilt on TypeScript +
React Router + Tailwind v4 + shadcn/ui's `cmdk`-based `Command` component, replacing
the spike's flat unrouted `App.jsx`. Route paths are generated from a static,
hand-maintained candidate list (routes must exist before any fetch resolves);
sidebar/palette *display* prefers the live API result, falling back to the same
static list if the API is unreachable.

**Tech Stack:** FastAPI (existing), React 18 + Vite 5 (existing, from the spike),
TypeScript, React Router v6, Tailwind CSS v4 (`@tailwindcss/vite`), shadcn/ui + `cmdk`,
Vitest + React Testing Library.

## Global Constraints

- **No `desktop_app.py` changes.** This slice is built and verified entirely through
  the standalone dev workflow (`npm run dev` + `python3 api/spike_launcher.py`).
  `desktop_app.py` keeps pointing at Streamlit, unmodified.
- **⌘K searches only the static page list + 6 Settings-section entries** — no dynamic
  openings/findings search in this slice.
- **No job-status or active-profile indicators** — the topbar has no live data
  dependency beyond `/api/nav/pages`.
- **Route paths must exactly match the existing `url_path` values** in
  `dashboard/app.py`'s `st.Page(...)` calls (e.g. `overview`, `game-endings`,
  `tactical-highlights`) — no renaming.
- **No global state management library** (no Redux/Zustand/Jotai) — plain React
  state/Context only.
- **`dashboard/data/search.py` is not modified** — its existing `PAGE_CANDIDATES`/
  `SETTINGS_CANDIDATES` shape is wrapped as-is.
- **The final verification task (Task 7) must be run by the orchestrating session
  directly, never dispatched to a subagent** — this project's standing directive
  (`orchestrator_runs_tests_not_subagents` memory) is that subagents running their own
  test/server commands can hang waiting on a notification channel that isn't theirs.

---

## Task 1: Backend — `/api/nav/pages` endpoint

**Files:**
- Modify: `api/main.py`
- Create: `tests/integration/test_api_nav.py`

**Interfaces:**
- Produces: `GET /api/nav/pages` → JSON array of `{category: "page"|"setting", title:
  string, url_path: string}`, exactly `data.PAGE_CANDIDATES + data.SETTINGS_CANDIDATES`
  (19 page entries + 6 setting entries = 25 total). Every later frontend task treats
  this as the live-data source for nav/palette display.

- [ ] **Step 1: Write the failing integration test**

Create `tests/integration/test_api_nav.py`:

```python
"""Integration test for the app-shell slice's nav/palette data endpoint.

Mirrors test_api_overview.py's api_client fixture pattern -- see that
file's module docstring for why get_connections() being safe outside
Streamlit matters here too (api.main imports `data`, which pulls in the
same _common connection machinery even though this specific endpoint
never touches a DB connection itself).
"""
import importlib
import pathlib
import shutil
import sys

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
DASHBOARD_DIR = REPO_ROOT / "dashboard"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(DASHBOARD_DIR))


@pytest.fixture
def api_client(migrated_db_path, monkeypatch, tmp_path):
    scratch_config = tmp_path / "config.yaml"
    shutil.copy(REPO_ROOT / "config.yaml", scratch_config)
    monkeypatch.setenv("CHESSWRIGHT_CONFIG_PATH", str(scratch_config))

    import config as _config
    importlib.reload(_config)
    _config.set_player_name("spike_test_player", path=str(scratch_config))
    _config.set_database_path(str(migrated_db_path), path=str(scratch_config))

    import _common
    _common.get_connections.clear()

    import api.main as api_main
    return TestClient(api_main.app)


@pytest.mark.integration
def test_nav_pages_endpoint(api_client):
    resp = api_client.get("/api/nav/pages")
    assert resp.status_code == 200
    body = resp.json()

    assert len(body) == 25  # 19 pages + 6 settings sections

    assert all(set(item.keys()) >= {"category", "title", "url_path"} for item in body)

    page_url_paths = {item["url_path"] for item in body if item["category"] == "page"}
    assert page_url_paths == {
        "overview", "patterns", "openings", "matchups", "game-endings",
        "tactical-highlights", "insights", "points", "evolution",
        "game-explorer", "drill-export", "training-queue", "srs-drills",
        "opening-tree", "opponent-prep", "ask", "settings",
        "analysis-jobs", "batch-impact",
    }

    setting_titles = {item["title"] for item in body if item["category"] == "setting"}
    assert setting_titles == {
        "Anthropic API key", "Live engine settings", "Import an existing database",
        "Chess.com account", "Chesswright Pro", "Support this project",
    }
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m pytest tests/integration/test_api_nav.py -v`
Expected: FAIL — `404 Not Found` (the endpoint doesn't exist yet), assertion on
`resp.status_code == 200` fails.

- [ ] **Step 3: Implement the endpoint**

In `api/main.py`, after the existing `rating_snapshot()` endpoint (the last of the 3
Overview endpoints), add:

```python
@app.get("/api/nav/pages")
def nav_pages():
    return data.PAGE_CANDIDATES + data.SETTINGS_CANDIDATES
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 -m pytest tests/integration/test_api_nav.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add api/main.py tests/integration/test_api_nav.py
git commit -m "$(cat <<'EOF'
Add /api/nav/pages endpoint for the app-shell slice

Thin wrapper over dashboard/data/search.py's existing PAGE_CANDIDATES
and SETTINGS_CANDIDATES -- no changes to that module, its shape is
already exactly what the frontend nav/palette need.
EOF
)"
```

---

## Task 2: Frontend — TypeScript + Vitest toolchain migration

**Files:**
- Delete: `frontend/src/App.jsx`, `frontend/src/main.jsx`
- Create: `frontend/tsconfig.json`, `frontend/tsconfig.node.json`,
  `frontend/src/App.tsx`, `frontend/src/main.tsx`, `frontend/src/setupTests.ts`,
  `frontend/src/App.test.tsx`
- Modify: `frontend/vite.config.js` → `frontend/vite.config.ts`,
  `frontend/index.html`, `frontend/package.json`

**Interfaces:**
- Produces: a working `npm run dev` / `npm run build` / `npm test` / `npm run
  typecheck` toolchain on TypeScript, with a `@/*` → `./src/*` path alias configured
  (needed by shadcn/ui in Task 6 — set up now so Task 6 doesn't need another
  `vite.config.ts` edit). `App.tsx` at this point is a placeholder; Task 5 replaces
  its content with the real route table.

- [ ] **Step 1: Remove the spike's flat JS entry point**

```bash
git rm frontend/src/App.jsx frontend/src/main.jsx
```

- [ ] **Step 2: Install TypeScript + testing toolchain**

```bash
cd frontend
npm install -D typescript@^5.7.0 @types/react@^18.3.0 @types/react-dom@^18.3.0 \
  vitest@^2.1.0 jsdom@^25.0.0 @testing-library/react@^16.0.0 \
  @testing-library/jest-dom@^6.6.0 @testing-library/user-event@^14.5.0
cd ..
```

- [ ] **Step 3: Add TypeScript configs**

Create `frontend/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "baseUrl": ".",
    "paths": { "@/*": ["./src/*"] }
  },
  "include": ["src"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

Create `frontend/tsconfig.node.json`:

```json
{
  "compilerOptions": {
    "composite": true,
    "skipLibCheck": true,
    "module": "ESNext",
    "moduleResolution": "bundler",
    "allowSyntheticDefaultImports": true
  },
  "include": ["vite.config.ts"]
}
```

- [ ] **Step 4: Replace `vite.config.js` with `vite.config.ts`**

```bash
git rm frontend/vite.config.js
```

Create `frontend/vite.config.ts`:

```ts
import path from 'path'
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/setupTests.ts',
  },
})
```

- [ ] **Step 5: Update `index.html` to point at the new TS entry**

In `frontend/index.html`, change:
```html
    <script type="module" src="/src/main.jsx"></script>
```
to:
```html
    <script type="module" src="/src/main.tsx"></script>
```

- [ ] **Step 6: Add npm scripts**

In `frontend/package.json`, update `"scripts"` to:

```json
  "scripts": {
    "dev": "vite --port 5173",
    "build": "vite build",
    "test": "vitest run",
    "typecheck": "tsc --noEmit"
  },
```

- [ ] **Step 7: Write the failing smoke test**

Create `frontend/src/setupTests.ts`:

```ts
import '@testing-library/jest-dom'
```

Create `frontend/src/App.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import App from './App'

describe('App', () => {
  it('renders the Chesswright placeholder', () => {
    render(<App />)
    expect(screen.getByText('Chesswright')).toBeInTheDocument()
  })
})
```

- [ ] **Step 8: Run the test to verify it fails**

Run: `cd frontend && npm test`
Expected: FAIL — `Cannot find module './App'` (no `App.tsx` exists yet; the old
`App.jsx` was deleted in Step 1).

- [ ] **Step 9: Write the minimal implementation**

Create `frontend/src/App.tsx`:

```tsx
export default function App() {
  return <div>Chesswright</div>
}
```

Create `frontend/src/main.tsx`:

```tsx
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'

const rootElement = document.getElementById('root')
if (!rootElement) throw new Error('#root element not found')

ReactDOM.createRoot(rootElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
```

- [ ] **Step 10: Run the test, typecheck, and build to verify everything passes**

Run: `cd frontend && npm test`
Expected: PASS

Run: `cd frontend && npm run typecheck`
Expected: no output, exit code 0

Run: `cd frontend && npm run build`
Expected: `dist/` produced, exit code 0

- [ ] **Step 11: Commit**

```bash
git add frontend/
git commit -m "$(cat <<'EOF'
Migrate frontend toolchain to TypeScript + Vitest

Replaces the spike's flat App.jsx/main.jsx with a TS entry point and
adds the Vitest + React Testing Library toolchain every later
app-shell task's tests depend on. App.tsx is a placeholder here --
Task 5 replaces it with the real route table.
EOF
)"
```

---

## Task 3: Frontend — Tailwind v4 + theme tokens

**Files:**
- Create: `frontend/src/index.css`, `frontend/src/lib/theme.ts`,
  `frontend/src/lib/theme.test.ts`
- Modify: `frontend/vite.config.ts`, `frontend/src/main.tsx`

**Interfaces:**
- Produces: `THEME` constant (`frontend/src/lib/theme.ts`) — `{ bg, bgSecondary,
  accentGold, positive, negative, text, textMuted }`, each a hex/CSS-color string.
  Tailwind utility classes `bg-bg`, `text-text`, `bg-bg-secondary`, `text-accent-gold`,
  etc. become available to every component from this task onward.

- [ ] **Step 1: Install Tailwind v4**

```bash
cd frontend
npm install tailwindcss@^4.0.0 @tailwindcss/vite@^4.0.0
cd ..
```

- [ ] **Step 2: Write the failing theme-tokens test**

Create `frontend/src/lib/theme.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import { THEME } from './theme'

describe('THEME', () => {
  it('matches the dashboard/theme.py palette exactly', () => {
    expect(THEME.bg).toBe('#14181F')
    expect(THEME.bgSecondary).toBe('#1E2530')
    expect(THEME.accentGold).toBe('#C19A4B')
    expect(THEME.positive).toBe('#6FA98C')
    expect(THEME.negative).toBe('#B0584F')
    expect(THEME.text).toBe('#E8E6E1')
  })
})
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd frontend && npm test`
Expected: FAIL — `Cannot find module './theme'`.

- [ ] **Step 4: Implement the theme tokens**

Create `frontend/src/lib/theme.ts`:

```ts
// Ported from dashboard/theme.py's palette (validated for WCAG AA contrast
// there via validate_palette.js) -- kept in sync by hand, same accepted
// duplication risk as navConfig.ts's group bucketing.
export const THEME = {
  bg: '#14181F',
  bgSecondary: '#1E2530',
  accentGold: '#C19A4B',
  positive: '#6FA98C',
  negative: '#B0584F',
  text: '#E8E6E1',
  textMuted: 'rgb(232 230 225 / 0.6)',
} as const
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd frontend && npm test`
Expected: PASS

- [ ] **Step 6: Wire Tailwind into the build and expose the same tokens as CSS**

Modify `frontend/vite.config.ts` — add the Tailwind plugin:

```ts
import path from 'path'
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/setupTests.ts',
  },
})
```

Create `frontend/src/index.css`:

```css
@import "tailwindcss";

@theme {
  --color-bg: #14181F;
  --color-bg-secondary: #1E2530;
  --color-accent-gold: #C19A4B;
  --color-positive: #6FA98C;
  --color-negative: #B0584F;
  --color-text: #E8E6E1;
  --color-text-muted: rgb(232 230 225 / 0.6);
}

body {
  margin: 0;
}
```

Modify `frontend/src/main.tsx` to import it — add as the first line:

```tsx
import './index.css'
import React from 'react'
```

(the rest of `main.tsx` is unchanged from Task 2)

- [ ] **Step 7: Run the full check to verify nothing broke**

Run: `cd frontend && npm test && npm run typecheck && npm run build`
Expected: all three pass/succeed.

- [ ] **Step 8: Commit**

```bash
git add frontend/
git commit -m "$(cat <<'EOF'
Add Tailwind v4 and port dashboard/theme.py's palette

THEME constants + matching Tailwind @theme tokens (bg, bg-secondary,
accent-gold, positive, negative, text, text-muted), for visual
continuity with the still-Streamlit pages during the dev-parallel
migration period.
EOF
)"
```

---

## Task 4: Frontend — nav config, static fallback list, and the candidates hook

**Files:**
- Create: `frontend/src/lib/navCandidates.ts`, `frontend/src/lib/navCandidates.test.ts`,
  `frontend/src/navConfig.ts`, `frontend/src/navConfig.test.ts`,
  `frontend/src/hooks/usePageCandidates.ts`, `frontend/src/hooks/usePageCandidates.test.ts`

**Interfaces:**
- Produces:
  - `PageCandidate` type (`frontend/src/lib/navCandidates.ts`): `{ category: "page" |
    "setting", title: string, url_path: string }`.
  - `STATIC_CANDIDATES: PageCandidate[]` (`frontend/src/lib/navCandidates.ts`) — the
    bundled fallback copy of `/api/nav/pages`'s response.
  - `NavGroup` type (`"Career" | "Explore" | "App"`), `NAV_GROUPS: NavGroup[]`,
    `PAGE_GROUP: Record<string, NavGroup>`, and `groupPages(pages: PageCandidate[]):
    Record<NavGroup, PageCandidate[]>` — all in `frontend/src/navConfig.ts`.
  - `usePageCandidates(): { candidates: PageCandidate[], usingFallback: boolean }`
    (`frontend/src/hooks/usePageCandidates.ts`) — fetches `GET
    http://127.0.0.1:8123/api/nav/pages`, falls back to `STATIC_CANDIDATES` on any
    failure.
- Consumes: nothing from earlier tasks (pure logic + fetch, no UI).

- [ ] **Step 1: Write the failing static-candidates test**

Create `frontend/src/lib/navCandidates.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import { STATIC_CANDIDATES } from './navCandidates'

describe('STATIC_CANDIDATES', () => {
  it('has 19 pages and 6 settings, matching the backend exactly', () => {
    expect(STATIC_CANDIDATES).toHaveLength(25)

    const pageUrlPaths = new Set(
      STATIC_CANDIDATES.filter((c) => c.category === 'page').map((c) => c.url_path),
    )
    expect(pageUrlPaths).toEqual(new Set([
      'overview', 'patterns', 'openings', 'matchups', 'game-endings',
      'tactical-highlights', 'insights', 'points', 'evolution',
      'game-explorer', 'drill-export', 'training-queue', 'srs-drills',
      'opening-tree', 'opponent-prep', 'ask', 'settings',
      'analysis-jobs', 'batch-impact',
    ]))

    const settingTitles = new Set(
      STATIC_CANDIDATES.filter((c) => c.category === 'setting').map((c) => c.title),
    )
    expect(settingTitles).toEqual(new Set([
      'Anthropic API key', 'Live engine settings', 'Import an existing database',
      'Chess.com account', 'Chesswright Pro', 'Support this project',
    ]))
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test`
Expected: FAIL — `Cannot find module './navCandidates'`.

- [ ] **Step 3: Implement the static candidates list**

Create `frontend/src/lib/navCandidates.ts`:

```ts
// Bundled fallback for GET /api/nav/pages -- used only if that request
// fails (see hooks/usePageCandidates.ts). Hand-transcribed from
// dashboard/data/search.py's PAGE_CANDIDATES/SETTINGS_CANDIDATES; kept in
// sync manually, same accepted drift risk as navConfig.ts's group
// bucketing -- both are small, low-frequency-change duplication, not
// worth a build-time codegen step for.
export interface PageCandidate {
  category: 'page' | 'setting'
  title: string
  url_path: string
}

export const STATIC_CANDIDATES: PageCandidate[] = [
  { category: 'page', title: 'Overview', url_path: 'overview' },
  { category: 'page', title: 'Patterns & Tendencies', url_path: 'patterns' },
  { category: 'page', title: 'Openings & Repertoire', url_path: 'openings' },
  { category: 'page', title: 'Matchups & Opponents', url_path: 'matchups' },
  { category: 'page', title: 'Game Endings', url_path: 'game-endings' },
  { category: 'page', title: 'Tactical Highlights', url_path: 'tactical-highlights' },
  { category: 'page', title: 'Insights', url_path: 'insights' },
  { category: 'page', title: 'Where Your Points Go', url_path: 'points' },
  { category: 'page', title: 'Repertoire Evolution', url_path: 'evolution' },
  { category: 'page', title: 'Game Explorer', url_path: 'game-explorer' },
  { category: 'page', title: 'Drill Export', url_path: 'drill-export' },
  { category: 'page', title: 'Training Queue', url_path: 'training-queue' },
  { category: 'page', title: 'SRS Drills ✦', url_path: 'srs-drills' },
  { category: 'page', title: 'Opening Tree ✦', url_path: 'opening-tree' },
  { category: 'page', title: 'Opponent Prep', url_path: 'opponent-prep' },
  { category: 'page', title: 'Ask', url_path: 'ask' },
  { category: 'page', title: 'Settings', url_path: 'settings' },
  { category: 'page', title: 'Analysis Jobs', url_path: 'analysis-jobs' },
  { category: 'page', title: 'Batch Impact', url_path: 'batch-impact' },
  { category: 'setting', title: 'Anthropic API key', url_path: 'settings' },
  { category: 'setting', title: 'Live engine settings', url_path: 'settings' },
  { category: 'setting', title: 'Import an existing database', url_path: 'settings' },
  { category: 'setting', title: 'Chess.com account', url_path: 'settings' },
  { category: 'setting', title: 'Chesswright Pro', url_path: 'settings' },
  { category: 'setting', title: 'Support this project', url_path: 'settings' },
]
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm test`
Expected: PASS

- [ ] **Step 5: Write the failing nav-grouping test**

Create `frontend/src/navConfig.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import { groupPages, NAV_GROUPS, PAGE_GROUP } from './navConfig'
import { STATIC_CANDIDATES } from './lib/navCandidates'

describe('navConfig', () => {
  it('has exactly the 3 expected groups', () => {
    expect(NAV_GROUPS).toEqual(['Career', 'Explore', 'App'])
  })

  it('groups every static page into its correct group, matching dashboard/app.py', () => {
    const pages = STATIC_CANDIDATES.filter((c) => c.category === 'page')
    const grouped = groupPages(pages)

    expect(grouped.Career.map((p) => p.url_path)).toEqual([
      'overview', 'patterns', 'openings', 'matchups', 'game-endings',
      'tactical-highlights', 'insights', 'points', 'evolution',
    ])
    expect(grouped.Explore.map((p) => p.url_path)).toEqual([
      'game-explorer', 'drill-export', 'training-queue', 'srs-drills',
      'opening-tree', 'opponent-prep', 'ask',
    ])
    expect(grouped.App.map((p) => p.url_path)).toEqual([
      'settings', 'analysis-jobs', 'batch-impact',
    ])
  })

  it('assigns every page a group in PAGE_GROUP', () => {
    const pages = STATIC_CANDIDATES.filter((c) => c.category === 'page')
    for (const page of pages) {
      expect(PAGE_GROUP[page.url_path]).toBeDefined()
    }
  })
})
```

- [ ] **Step 6: Run the test to verify it fails**

Run: `cd frontend && npm test`
Expected: FAIL — `Cannot find module './navConfig'`.

- [ ] **Step 7: Implement nav grouping**

Create `frontend/src/navConfig.ts`:

```ts
// The Career/Explore/App grouping below only exists in dashboard/app.py's
// literal st.navigation({...}) dict -- it isn't in any data-layer
// structure PAGE_CANDIDATES could be enriched with without touching
// dashboard/data/search.py's shape. Hand-maintained; keep in sync if
// app.py's grouping changes.
import type { PageCandidate } from './lib/navCandidates'

export type NavGroup = 'Career' | 'Explore' | 'App'

export const NAV_GROUPS: NavGroup[] = ['Career', 'Explore', 'App']

export const PAGE_GROUP: Record<string, NavGroup> = {
  overview: 'Career',
  patterns: 'Career',
  openings: 'Career',
  matchups: 'Career',
  'game-endings': 'Career',
  'tactical-highlights': 'Career',
  insights: 'Career',
  points: 'Career',
  evolution: 'Career',
  'game-explorer': 'Explore',
  'drill-export': 'Explore',
  'training-queue': 'Explore',
  'srs-drills': 'Explore',
  'opening-tree': 'Explore',
  'opponent-prep': 'Explore',
  ask: 'Explore',
  settings: 'App',
  'analysis-jobs': 'App',
  'batch-impact': 'App',
}

export function groupPages(pages: PageCandidate[]): Record<NavGroup, PageCandidate[]> {
  const grouped: Record<NavGroup, PageCandidate[]> = { Career: [], Explore: [], App: [] }
  for (const page of pages) {
    const group = PAGE_GROUP[page.url_path]
    if (group) grouped[group].push(page)
  }
  return grouped
}
```

- [ ] **Step 8: Run the test to verify it passes**

Run: `cd frontend && npm test`
Expected: PASS

- [ ] **Step 9: Write the failing usePageCandidates tests**

Create `frontend/src/hooks/usePageCandidates.test.ts`:

```ts
import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { usePageCandidates } from './usePageCandidates'
import { STATIC_CANDIDATES } from '../lib/navCandidates'

describe('usePageCandidates', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('uses the API result when the fetch succeeds', async () => {
    const apiResult = [{ category: 'page', title: 'From API', url_path: 'from-api' }]
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => apiResult,
    }))

    const { result } = renderHook(() => usePageCandidates())

    await waitFor(() => {
      expect(result.current.candidates).toEqual(apiResult)
    })
    expect(result.current.usingFallback).toBe(false)
  })

  it('falls back to STATIC_CANDIDATES when the fetch fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network error')))

    const { result } = renderHook(() => usePageCandidates())

    await waitFor(() => {
      expect(result.current.usingFallback).toBe(true)
    })
    expect(result.current.candidates).toEqual(STATIC_CANDIDATES)
  })

  it('falls back to STATIC_CANDIDATES when the response is not ok', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 500 }))

    const { result } = renderHook(() => usePageCandidates())

    await waitFor(() => {
      expect(result.current.usingFallback).toBe(true)
    })
    expect(result.current.candidates).toEqual(STATIC_CANDIDATES)
  })
})
```

- [ ] **Step 10: Run the test to verify it fails**

Run: `cd frontend && npm test`
Expected: FAIL — `Cannot find module './usePageCandidates'`.

- [ ] **Step 11: Implement the hook**

Create `frontend/src/hooks/usePageCandidates.ts`:

```ts
import { useEffect, useState } from 'react'
import { STATIC_CANDIDATES, type PageCandidate } from '../lib/navCandidates'

const API_BASE = 'http://127.0.0.1:8123'

export interface UsePageCandidatesResult {
  candidates: PageCandidate[]
  usingFallback: boolean
}

export function usePageCandidates(): UsePageCandidatesResult {
  const [candidates, setCandidates] = useState<PageCandidate[]>(STATIC_CANDIDATES)
  const [usingFallback, setUsingFallback] = useState(false)

  useEffect(() => {
    let cancelled = false

    fetch(`${API_BASE}/api/nav/pages`)
      .then((r) => {
        if (!r.ok) throw new Error(`status ${r.status}`)
        return r.json() as Promise<PageCandidate[]>
      })
      .then((data) => {
        if (!cancelled) {
          setCandidates(data)
          setUsingFallback(false)
        }
      })
      .catch(() => {
        if (!cancelled) {
          console.warn(
            'Chesswright: /api/nav/pages unreachable, using the bundled static nav list.',
          )
          setCandidates(STATIC_CANDIDATES)
          setUsingFallback(true)
        }
      })

    return () => {
      cancelled = true
    }
  }, [])

  return { candidates, usingFallback }
}
```

- [ ] **Step 12: Run the test to verify it passes**

Run: `cd frontend && npm test`
Expected: PASS (all `navCandidates`, `navConfig`, `usePageCandidates` tests green)

- [ ] **Step 13: Commit**

```bash
git add frontend/
git commit -m "$(cat <<'EOF'
Add nav config, static candidate fallback, and usePageCandidates hook

STATIC_CANDIDATES is a hand-transcribed copy of PAGE_CANDIDATES +
SETTINGS_CANDIDATES from dashboard/data/search.py, used both as the
route table's source (routes must exist before any fetch resolves)
and as usePageCandidates' fallback when /api/nav/pages is unreachable.
navConfig.ts's Career/Explore/App grouping is the one piece with no
data-layer source at all -- hand-maintained, flagged in comments.
EOF
)"
```

---

## Task 5: Frontend — routed shell (PageStub, Shell, Sidebar, App routes)

**Files:**
- Create: `frontend/src/pages/PageStub.tsx`, `frontend/src/pages/PageStub.test.tsx`,
  `frontend/src/components/Sidebar.tsx`, `frontend/src/components/Sidebar.test.tsx`,
  `frontend/src/components/Shell.tsx`
- Modify: `frontend/src/App.tsx`, `frontend/src/App.test.tsx`, `frontend/src/main.tsx`

**Interfaces:**
- Consumes: `usePageCandidates` (Task 4, `frontend/src/hooks/usePageCandidates.ts`),
  `groupPages`/`NAV_GROUPS` (Task 4, `frontend/src/navConfig.ts`), `PageCandidate`/
  `STATIC_CANDIDATES` (Task 4, `frontend/src/lib/navCandidates.ts`).
- Produces: `<Shell />` (`frontend/src/components/Shell.tsx`) — the routed layout with
  `<Outlet />`, rendered once at the top of the route tree by `App.tsx`. `<PageStub
  title={string} />` (`frontend/src/pages/PageStub.tsx`) — the placeholder every route
  renders. Real routes exist at `/`, `/overview`, `/patterns`, ... (all 19 static
  `url_path`s), `/` redirects to `/overview`.

- [ ] **Step 1: Install React Router**

```bash
cd frontend
npm install react-router-dom@^6.28.0
cd ..
```

- [ ] **Step 2: Write the failing PageStub test**

Create `frontend/src/pages/PageStub.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import PageStub from './PageStub'

describe('PageStub', () => {
  it('renders the given title and a not-yet-migrated notice', () => {
    render(<PageStub title="Patterns & Tendencies" />)
    expect(screen.getByText('Patterns & Tendencies')).toBeInTheDocument()
    expect(screen.getByText(/not yet migrated/i)).toBeInTheDocument()
  })
})
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd frontend && npm test`
Expected: FAIL — `Cannot find module './PageStub'`.

- [ ] **Step 4: Implement PageStub**

Create `frontend/src/pages/PageStub.tsx`:

```tsx
export default function PageStub({ title }: { title: string }) {
  return (
    <div className="p-8">
      <h1 className="text-2xl font-semibold text-text">{title}</h1>
      <p className="mt-2 text-text-muted">Not yet migrated to the new interface.</p>
    </div>
  )
}
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd frontend && npm test`
Expected: PASS

- [ ] **Step 6: Write the failing Sidebar test**

Create `frontend/src/components/Sidebar.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import Sidebar from './Sidebar'
import { STATIC_CANDIDATES } from '../lib/navCandidates'

vi.mock('../hooks/usePageCandidates', () => ({
  usePageCandidates: () => ({ candidates: STATIC_CANDIDATES, usingFallback: false }),
}))

describe('Sidebar', () => {
  it('renders all 3 groups with the correct page counts', () => {
    render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>,
    )

    expect(screen.getByText('Career')).toBeInTheDocument()
    expect(screen.getByText('Explore')).toBeInTheDocument()
    expect(screen.getByText('App')).toBeInTheDocument()

    expect(screen.getByText('Overview')).toBeInTheDocument()
    expect(screen.getByText('Game Explorer')).toBeInTheDocument()
    expect(screen.getByText('Batch Impact')).toBeInTheDocument()

    // Settings-category candidates must never appear in the sidebar --
    // only the "Settings" page itself, not its 6 sub-sections.
    expect(screen.queryByText('Anthropic API key')).not.toBeInTheDocument()
  })
})
```

- [ ] **Step 7: Run the test to verify it fails**

Run: `cd frontend && npm test`
Expected: FAIL — `Cannot find module './Sidebar'`.

- [ ] **Step 8: Implement Sidebar**

Create `frontend/src/components/Sidebar.tsx`:

```tsx
import { NavLink } from 'react-router-dom'
import { usePageCandidates } from '../hooks/usePageCandidates'
import { NAV_GROUPS, groupPages } from '../navConfig'

export default function Sidebar() {
  const { candidates } = usePageCandidates()
  const pages = candidates.filter((c) => c.category === 'page')
  const grouped = groupPages(pages)

  return (
    <nav className="w-56 shrink-0 overflow-y-auto border-r border-bg-secondary bg-bg-secondary/40 p-4">
      {NAV_GROUPS.map((group) => (
        <div key={group} className="mb-6">
          <div className="mb-2 text-xs uppercase tracking-wide text-text-muted">
            {group}
          </div>
          {grouped[group].map((page) => (
            <NavLink
              key={page.url_path}
              to={`/${page.url_path}`}
              className={({ isActive }) =>
                `block rounded px-3 py-1.5 text-sm ${
                  isActive
                    ? 'bg-accent-gold/20 text-accent-gold'
                    : 'text-text hover:bg-bg-secondary'
                }`
              }
            >
              {page.title}
            </NavLink>
          ))}
        </div>
      ))}
    </nav>
  )
}
```

- [ ] **Step 9: Run the test to verify it passes**

Run: `cd frontend && npm test`
Expected: PASS

- [ ] **Step 10: Implement Shell (no separate test — covered by Step 12's routing test)**

Create `frontend/src/components/Shell.tsx`:

```tsx
import { Outlet } from 'react-router-dom'
import Sidebar from './Sidebar'

export default function Shell() {
  return (
    <div className="flex h-screen bg-bg text-text">
      <Sidebar />
      <div className="flex flex-1 flex-col">
        <header className="flex h-14 items-center justify-between border-b border-bg-secondary px-6">
          <span className="font-semibold text-accent-gold">Chesswright</span>
        </header>
        <main className="flex-1 overflow-auto">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
```

(The topbar's ⌘K trigger is added in Task 6, which also adds `<CommandPalette />` here.)

- [ ] **Step 11: Write the failing routing test**

Replace `frontend/src/App.test.tsx` entirely with:

```tsx
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import App from './App'
import { STATIC_CANDIDATES } from './lib/navCandidates'

vi.mock('./hooks/usePageCandidates', () => ({
  usePageCandidates: () => ({ candidates: STATIC_CANDIDATES, usingFallback: false }),
}))

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  )
}

describe('App routing', () => {
  it('redirects / to /overview', () => {
    renderAt('/')
    expect(screen.getByRole('heading', { name: 'Overview' })).toBeInTheDocument()
  })

  it('renders the correct stub for a direct URL navigation', () => {
    renderAt('/patterns')
    expect(screen.getByRole('heading', { name: 'Patterns & Tendencies' })).toBeInTheDocument()
  })
})
```

- [ ] **Step 12: Run the test to verify it fails**

Run: `cd frontend && npm test`
Expected: FAIL — `App.tsx` still renders the Task-2 placeholder (`<div>Chesswright</div>`),
no `heading` role exists.

- [ ] **Step 13: Implement the route table**

Replace `frontend/src/App.tsx` entirely with:

```tsx
import { Navigate, Route, Routes } from 'react-router-dom'
import Shell from './components/Shell'
import PageStub from './pages/PageStub'
import { STATIC_CANDIDATES } from './lib/navCandidates'

// Routes are generated from the static candidate list, not a live API
// fetch: React Router needs every valid path to exist synchronously at
// app start, before any fetch could resolve. usePageCandidates' live
// result only affects what the Sidebar/CommandPalette *display* -- if
// dashboard/app.py adds a page the live API would report but this
// static list hasn't been updated for, that page's route won't exist
// here until the next frontend build. Same accepted drift risk as
// navConfig.ts's group bucketing.
const pages = STATIC_CANDIDATES.filter((c) => c.category === 'page')

export default function App() {
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route path="/" element={<Navigate to="/overview" replace />} />
        {pages.map((page) => (
          <Route
            key={page.url_path}
            path={page.url_path}
            element={<PageStub title={page.title} />}
          />
        ))}
      </Route>
    </Routes>
  )
}
```

- [ ] **Step 14: Wrap the app in a router**

Modify `frontend/src/main.tsx` — add `BrowserRouter`:

```tsx
import './index.css'
import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'

const rootElement = document.getElementById('root')
if (!rootElement) throw new Error('#root element not found')

ReactDOM.createRoot(rootElement).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>,
)
```

- [ ] **Step 15: Run the test to verify it passes**

Run: `cd frontend && npm test`
Expected: PASS (all tests, including Sidebar and App routing)

Run: `cd frontend && npm run typecheck && npm run build`
Expected: both succeed

- [ ] **Step 16: Commit**

```bash
git add frontend/
git commit -m "$(cat <<'EOF'
Add routed app shell: PageStub, Sidebar, Shell, App route table

Reproduces dashboard/app.py's exact Career/Explore/App grouping and
19-page list. Every route renders PageStub for now -- real page
content (Overview first) is the next Phase 3 slice, deliberately not
pulled into this one.
EOF
)"
```

---

## Task 6: Frontend — shadcn/ui + global command palette

**Files:**
- Create (via `npx shadcn@latest`): `frontend/components.json`,
  `frontend/src/lib/utils.ts`, `frontend/src/components/ui/command.tsx`,
  `frontend/src/components/ui/dialog.tsx` (and any other files the CLI generates as
  dependencies of the `command` component)
- Create: `frontend/src/components/CommandPalette.tsx`,
  `frontend/src/components/CommandPalette.test.tsx`
- Modify: `frontend/src/components/Shell.tsx`

**Interfaces:**
- Consumes: `PageCandidate` (Task 4, `frontend/src/lib/navCandidates.ts`),
  `usePageCandidates` (Task 4, `frontend/src/hooks/usePageCandidates.ts`).
- Produces: `<CommandPalette open={boolean} onOpenChange={(open: boolean) => void}
  candidates={PageCandidate[]} />` (`frontend/src/components/CommandPalette.tsx`) —
  registers a `document`-level `keydown` listener for `Cmd/Ctrl+K` regardless of
  current focus, renders a searchable list of `candidates`, calls `useNavigate()` and
  `onOpenChange(false)` on selection.

- [ ] **Step 1: Initialize shadcn/ui**

```bash
cd frontend
npx shadcn@latest init
```

When prompted, answer: TypeScript — yes (already configured); style — "New York" (or
the CLI's current default, either is fine, this slice doesn't depend on the visual
default); base color — Neutral; CSS variables — yes; the `@` import alias should be
auto-detected from `tsconfig.json`'s `paths` (added in Task 2) — confirm rather than
overwrite it if asked. This generates `frontend/components.json` and
`frontend/src/lib/utils.ts` (a `cn()` class-merging helper).

- [ ] **Step 2: Add the Command component**

```bash
npx shadcn@latest add command
cd ..
```

This generates `frontend/src/components/ui/command.tsx` (wrapping the `cmdk`
package, which the CLI installs as a dependency) and pulls in `dialog` as a
transitive dependency if not already present.

- [ ] **Step 3: Run the existing suite to verify the CLI didn't break anything**

Run: `cd frontend && npm test && npm run typecheck && npm run build`
Expected: all pass (this step only adds new files; nothing existing should regress)

- [ ] **Step 4: Write the failing CommandPalette tests**

Create `frontend/src/components/CommandPalette.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, useNavigate } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import CommandPalette from './CommandPalette'
import type { PageCandidate } from '../lib/navCandidates'

const candidates: PageCandidate[] = [
  { category: 'page', title: 'Overview', url_path: 'overview' },
  { category: 'page', title: 'Patterns & Tendencies', url_path: 'patterns' },
  { category: 'setting', title: 'Anthropic API key', url_path: 'settings' },
]

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return { ...actual, useNavigate: vi.fn() }
})

function renderPalette(open: boolean, onOpenChange: (open: boolean) => void) {
  return render(
    <MemoryRouter>
      <input aria-label="distractor" />
      <CommandPalette open={open} onOpenChange={onOpenChange} candidates={candidates} />
    </MemoryRouter>,
  )
}

describe('CommandPalette', () => {
  it('opens on Cmd/Ctrl+K even while focus is inside an unrelated input', async () => {
    const onOpenChange = vi.fn()
    renderPalette(false, onOpenChange)

    const distractor = screen.getByLabelText('distractor')
    distractor.focus()
    expect(distractor).toHaveFocus()

    await userEvent.keyboard('{Meta>}k{/Meta}')

    expect(onOpenChange).toHaveBeenCalledWith(true)
  })

  it('filters candidates as the user types and navigates on selection', async () => {
    const navigate = vi.fn()
    vi.mocked(useNavigate).mockReturnValue(navigate)
    const onOpenChange = vi.fn()
    renderPalette(true, onOpenChange)

    await userEvent.type(screen.getByPlaceholderText(/search/i), 'Patterns')
    expect(screen.getByText('Patterns & Tendencies')).toBeInTheDocument()
    expect(screen.queryByText('Overview')).not.toBeInTheDocument()

    await userEvent.click(screen.getByText('Patterns & Tendencies'))

    expect(navigate).toHaveBeenCalledWith('/patterns')
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })
})
```

- [ ] **Step 5: Run the test to verify it fails**

Run: `cd frontend && npm test`
Expected: FAIL — `Cannot find module './CommandPalette'`.

- [ ] **Step 6: Implement CommandPalette**

Create `frontend/src/components/CommandPalette.tsx`:

```tsx
import { useEffect, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from './ui/command'
import type { PageCandidate } from '../lib/navCandidates'

export interface CommandPaletteProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  candidates: PageCandidate[]
}

export default function CommandPalette({ open, onOpenChange, candidates }: CommandPaletteProps) {
  const navigate = useNavigate()

  useEffect(() => {
    // Registered on `document`, not scoped to any component inside the
    // palette itself -- this is the specific thing that must work
    // regardless of where focus currently is, the exact case Streamlit's
    // iframe-sandboxed custom components can't do (BRIEF §25).
    function handleKeyDown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        onOpenChange(!open)
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [open, onOpenChange])

  function handleSelect(urlPath: string) {
    navigate(`/${urlPath}`)
    onOpenChange(false)
  }

  const pages = useMemo(() => candidates.filter((c) => c.category === 'page'), [candidates])
  const settings = useMemo(() => candidates.filter((c) => c.category === 'setting'), [candidates])

  return (
    <CommandDialog open={open} onOpenChange={onOpenChange}>
      <CommandInput placeholder="Search pages, settings…" />
      <CommandList>
        <CommandEmpty>No results found.</CommandEmpty>
        <CommandGroup heading="Pages">
          {pages.map((page) => (
            <CommandItem
              key={page.url_path}
              value={page.title}
              onSelect={() => handleSelect(page.url_path)}
            >
              {page.title}
            </CommandItem>
          ))}
        </CommandGroup>
        <CommandGroup heading="Settings">
          {settings.map((setting) => (
            <CommandItem
              key={setting.title}
              value={setting.title}
              onSelect={() => handleSelect(setting.url_path)}
            >
              {setting.title}
            </CommandItem>
          ))}
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  )
}
```

- [ ] **Step 7: Run the test to verify it passes**

Run: `cd frontend && npm test`
Expected: PASS

- [ ] **Step 8: Wire the palette (and its trigger) into Shell**

Replace `frontend/src/components/Shell.tsx` entirely with:

```tsx
import { useState } from 'react'
import { Outlet } from 'react-router-dom'
import Sidebar from './Sidebar'
import CommandPalette from './CommandPalette'
import { usePageCandidates } from '../hooks/usePageCandidates'

export default function Shell() {
  const [paletteOpen, setPaletteOpen] = useState(false)
  const { candidates } = usePageCandidates()

  return (
    <div className="flex h-screen bg-bg text-text">
      <Sidebar />
      <div className="flex flex-1 flex-col">
        <header className="flex h-14 items-center justify-between border-b border-bg-secondary px-6">
          <span className="font-semibold text-accent-gold">Chesswright</span>
          <button
            type="button"
            onClick={() => setPaletteOpen(true)}
            className="rounded border border-bg-secondary px-3 py-1 text-sm text-text-muted hover:text-text"
          >
            Search… <kbd className="ml-2 text-xs">⌘K</kbd>
          </button>
        </header>
        <main className="flex-1 overflow-auto">
          <Outlet />
        </main>
      </div>
      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} candidates={candidates} />
    </div>
  )
}
```

- [ ] **Step 9: Run the full check to verify nothing broke**

Run: `cd frontend && npm test && npm run typecheck && npm run build`
Expected: all pass (Shell has no dedicated test file — it's covered end-to-end by
Task 5's `App.test.tsx` routing tests, which still render through `Shell`)

- [ ] **Step 10: Commit**

```bash
git add frontend/
git commit -m "$(cat <<'EOF'
Add global ⌘K command palette via shadcn/ui + cmdk

CommandPalette registers its keydown listener on document (not scoped
to any component), which is the specific thing that must work
regardless of current focus -- the exact case Streamlit's
iframe-sandboxed custom components can't do (BRIEF §25). Wired into
Shell's topbar with a visible trigger button alongside the ⌘K
shortcut.
EOF
)"
```

---

## Task 7: Live verification and roadmap update

**⚠️ This task must be run by the orchestrating session directly — do not dispatch it
to a subagent.** Per this project's standing directive
(`orchestrator_runs_tests_not_subagents` memory), a subagent launching its own dev
servers can hang waiting on a notification channel that isn't its own. This task also
requires the Playwright MCP browser tools, which are available in the orchestrating
session.

**Files:**
- Modify: `docs/scoping/frontend-rewrite-development-path-2026-07-12.md`

- [ ] **Step 1: Start the backend dev server**

```bash
python3 api/spike_launcher.py &
```

Wait for it to print `Fetched real data through the subprocess API: ...` and
`Clean shutdown confirmed` — no, actually **do not** let `spike_launcher.py`'s
`main()` run its own smoke-test-and-shutdown cycle for this step. Instead, run the API
directly in server mode, matching how the frontend expects a long-lived server on a
fixed port:

```bash
python3 -m uvicorn api.main:app --host 127.0.0.1 --port 8123 &
```

Confirm it's serving: `curl -s http://127.0.0.1:8123/api/nav/pages | head -c 200`
Expected: a JSON array starting with `[{"category":"page","title":"Overview",...`

- [ ] **Step 2: Start the frontend dev server**

```bash
cd frontend && npm run dev &
cd ..
```

Confirm it's serving: `curl -s http://127.0.0.1:5173 | head -c 200`
Expected: the Vite dev HTML shell (200 response).

- [ ] **Step 3: Live-verify with the Playwright MCP tools**

Using `mcp__plugin_playwright_playwright__browser_navigate` and the other Playwright
MCP tools available in this session, against `http://127.0.0.1:5173`:

1. Navigate to `/`. Confirm it redirects to `/overview` and the Overview stub renders.
2. Take a snapshot/screenshot. Confirm all 3 groups (Career, Explore, App) are visible
   in the sidebar with the correct pages under each, matching Task 5's grouping test.
3. Click a non-Overview sidebar link (e.g. "Game Endings"). Confirm the URL changes to
   `/game-endings` and the stub's heading updates to "Game Endings".
4. Use browser back navigation. Confirm it returns to `/overview`.
5. Navigate directly to `http://127.0.0.1:5173/tactical-highlights` (a fresh
   navigation, not a click). Confirm the correct stub renders — proves real routing,
   not client-side-only state.
6. Click into some non-palette text input if one exists on the page, or otherwise
   confirm focus is not on the palette trigger button. Dispatch `Cmd+K` (or `Ctrl+K`
   on non-Mac) via the Playwright keyboard tool. Confirm the command palette opens —
   this is the literal litmus test this whole slice exists to prove.
7. Type "Settings" into the palette. Confirm both the "Settings" page and all 6
   Settings-category entries (Anthropic API key, Live engine settings, etc.) appear,
   filtered correctly.
8. Click "Anthropic API key". Confirm it navigates to `/settings` and the palette
   closes.
9. Check console messages (`mcp__plugin_playwright_playwright__browser_console_messages`)
   across all of the above. Confirm zero errors.
10. Stop the frontend dev server, kill the `uvicorn` process, confirm no orphaned
    processes remain (`ps aux | grep -E "vite|uvicorn"`).

If any check fails, fix the relevant frontend/backend code from the task that owns
it, re-run the affected task's automated tests, then repeat this Step 3 from the top.

- [ ] **Step 4: Update the roadmap doc**

In `docs/scoping/frontend-rewrite-development-path-2026-07-12.md`, after the existing
"Phase 2 update" paragraph at the end of the file, add:

```markdown
**Phase 3 update (2026-07-12): app-shell slice done.** React app shell (topbar,
3-group/19-page sidebar nav reproducing `dashboard/app.py`'s grouping exactly, global
⌘K command palette via shadcn/ui + `cmdk`) built and live-verified against the real
dev API — confirmed the palette opens via `Cmd/Ctrl+K` regardless of current focus
(the specific case Streamlit's iframe-sandboxed custom components can't do, BRIEF
§25), fuzzy-filters and navigates correctly, and direct URL navigation to any of the
19 routes renders the correct page. Coexistence decision made as part of this slice
(see `docs/superpowers/specs/2026-07-12-app-shell-slice-design.md`): dev-parallel,
milestone cutover — every further Phase 3 slice builds against the standalone dev
workflow with zero `desktop_app.py` changes, deferring the one real
packaging-integration decision to a later judged milestone rather than smearing it
across every slice. Next: Overview (already spiked, cheap to port, re-validates the
existing `tests/integration/test_api_overview.py` slice against the real chosen
stack), per the roadmap's own risk-ordering.
```

- [ ] **Step 5: Commit**

```bash
git add docs/scoping/frontend-rewrite-development-path-2026-07-12.md
git commit -m "$(cat <<'EOF'
Record app-shell slice completion in the frontend rewrite roadmap

Live-verified via Playwright against the real dev API: global ⌘K
works regardless of focus location, sidebar grouping matches
dashboard/app.py exactly, direct URL navigation renders the correct
page for all 19 routes, zero console errors.
EOF
)"
```

---

## Self-Review Notes

- **Spec coverage**: every spec section has a task — backend endpoint (Task 1), TS/
  Tailwind toolchain (Tasks 2-3), nav data + fallback (Task 4), routed shell (Task 5),
  command palette (Task 6), live verification + roadmap update (Task 7). The
  coexistence decision (dev-parallel, no `desktop_app.py` changes) is enforced by
  omission — no task touches `desktop_app.py` — and recorded explicitly in Task 7's
  roadmap update.
- **Placeholder scan**: no TBD/TODO markers; every step has literal runnable
  commands or complete file contents, not descriptions of what to write.
- **Type consistency**: `PageCandidate` is defined once (Task 4,
  `lib/navCandidates.ts`) and imported by name everywhere else it's used (navConfig,
  usePageCandidates, Sidebar, App, CommandPalette) — no redefinition drift.
  `usePageCandidates()`'s return shape (`{ candidates, usingFallback }`) matches its
  Task 4 test and its Task 5/6 consumers exactly.
