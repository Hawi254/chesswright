# Overview Identity Zone Port — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port only the Overview page's identity zone (headline stats, rating
snapshot, current streak, career narrative, top-3 trait tags) from the Streamlit
dashboard to the new React/Vite + FastAPI stack, replacing the `PageStub` currently
rendered at `/overview`.

**Architecture:** Three new thin FastAPI wrapper endpoints (`current-streak`,
`career-findings`, `narrative`) alongside the 3 existing Overview endpoints, with a
small hand-written 60s TTL cache on the two expensive ones. One new frontend hook
(`useOverviewData`) fires all 5 Overview fetches in parallel; one new page component
(`OverviewPage`) renders loading/error/content from that hook's result and replaces
the stub at the `/overview` route.

**Tech Stack:** FastAPI (Python), pytest, React 18 + TypeScript, Vitest +
Testing Library, Tailwind CSS v4 (`@theme` tokens already in `frontend/src/index.css`).

## Global Constraints

- No changes to `dashboard/data/*.py` or `dashboard/narrative.py` business logic —
  every new endpoint is a thin wrapper, same style as the 3 existing Overview
  endpoints and `/api/nav/pages` in `api/main.py`.
- The `career-findings` endpoint must gate on `analyzed_games > 0` exactly like
  `dashboard/overview_view.py`'s `render()` does (line ~418: `if
  stats.get("analyzed_games", 0) > 0: findings = cached_career_findings(...)`) —
  this is the actual, already-proven-safe production behavior for
  `get_career_findings`, not an optimization to second-guess.
- TTL cache: 60 seconds, applied only to `career-findings` and `narrative` (not
  `current-streak`, which is a single flat, cheap query per the design spec). Hand
  written, not `functools.lru_cache` (no TTL) and not a general framework.
- Every new endpoint must degrade to a well-formed empty-ish response on a fresh,
  empty migrated DB (no games at all) — this is a real, designed-for onboarding
  state per `dashboard/narrative.py`'s own docstring, not a rare edge case.
- Frontend: no pixel parity with the current Streamlit page's custom CSS
  (`.cw-ov-rail` etc.) — style with Tailwind utility classes against the existing
  `@theme` tokens (`bg`, `bg-secondary`, `accent-gold`, `positive`, `negative`,
  `text`, `text-muted`), matching `PageStub.tsx`'s existing convention.
- `useOverviewData` reports one page-level `error: boolean`, not per-field errors —
  no partial-content rendering (see design spec's reasoning: the zone's pieces are
  too interdependent for graceful partial degradation to make sense).
- Run all test commands (`pytest`, `npm test`, `npm run typecheck`) yourself,
  synchronously in the foreground. Never background a test/dev-server command and
  wait for a notification about it — that channel does not exist for shell commands
  you run directly (`orchestrator_runs_tests_not_subagents` project memory).

---

## Task 1: Backend — 3 new endpoints + TTL cache

**Files:**
- Modify: `api/main.py`
- Modify: `tests/integration/test_api_overview.py`

**Interfaces:**
- Produces: `GET /api/overview/current-streak` → `{"outcome": str | null, "length": int}`
- Produces: `GET /api/overview/career-findings` → `list[dict]` (full finding dicts:
  `title`, `headline`, `detail`, `polarity`, `severity`, `category`, optional
  `confidence`)
- Produces: `GET /api/overview/narrative` → `{"narrative": str}`
- Produces: `api.main.reset_caches()` — test-only helper that clears both TTL
  caches; must be called by the `api_client` fixture before each test, since
  `api.main` is a singleton module shared across the whole pytest process (matches
  the existing `_common.get_connections.clear()` line already in that fixture).

- [ ] **Step 1: Write the failing tests**

Add to `tests/integration/test_api_overview.py`, after the existing
`test_rating_snapshot_endpoint` test:

```python
@pytest.mark.integration
def test_current_streak_endpoint(api_client):
    resp = api_client.get("/api/overview/current-streak")
    assert resp.status_code == 200
    assert resp.json() == {"outcome": None, "length": 0}


@pytest.mark.integration
def test_career_findings_endpoint_empty_db(api_client):
    resp = api_client.get("/api/overview/career-findings")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.integration
def test_career_findings_endpoint_ttl_cache(api_client, monkeypatch):
    import data

    call_count = {"n": 0}

    def fake_get_headline_stats(*args, **kwargs):
        return {"total_games": 10, "analyzed_games": 10, "acpl": 45.0,
                 "blunder_rate": 5.0, "win_pct": 55.0, "n_analyzed_moves": 200}

    def fake_get_career_findings(*args, **kwargs):
        call_count["n"] += 1
        return [{"title": "Test finding", "headline": "h", "detail": "d",
                  "polarity": "strength", "severity": "low", "category": "general"}]

    monkeypatch.setattr(data, "get_headline_stats", fake_get_headline_stats)
    monkeypatch.setattr(data, "get_career_findings", fake_get_career_findings)

    resp1 = api_client.get("/api/overview/career-findings")
    resp2 = api_client.get("/api/overview/career-findings")

    assert resp1.status_code == 200
    assert resp2.status_code == 200
    assert resp1.json() == resp2.json()
    assert call_count["n"] == 1


@pytest.mark.integration
def test_narrative_endpoint_empty_db(api_client):
    resp = api_client.get("/api/overview/narrative")
    assert resp.status_code == 200
    assert resp.json() == {"narrative": "No games yet -- fetch some games to get started."}


@pytest.mark.integration
def test_narrative_endpoint_ttl_cache(api_client, monkeypatch):
    import narrative

    call_count = {"n": 0}

    def fake_generate_career_narrative(*args, **kwargs):
        call_count["n"] += 1
        return "Test narrative text."

    monkeypatch.setattr(narrative, "generate_career_narrative", fake_generate_career_narrative)

    resp1 = api_client.get("/api/overview/narrative")
    resp2 = api_client.get("/api/overview/narrative")

    assert resp1.status_code == 200
    assert resp2.status_code == 200
    assert resp1.json() == resp2.json() == {"narrative": "Test narrative text."}
    assert call_count["n"] == 1
```

Also modify the existing `api_client` fixture in the same file to reset the new
module-level caches (add the line marked below, right after
`_common.get_connections.clear()`):

```python
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
    api_main.reset_caches()  # NEW -- module-level TTL caches persist across tests
                              # in this process otherwise, since api.main is only
                              # ever imported once.
    return TestClient(api_main.app)
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `python3 -m pytest tests/integration/test_api_overview.py -v`
Expected: the 5 new tests FAIL with `404 Not Found` (routes don't exist yet) or
`AttributeError: module 'api.main' has no attribute 'reset_caches'`.

- [ ] **Step 3: Implement the endpoints and TTL cache**

Replace the full contents of `api/main.py` with:

```python
"""FastAPI service wrapping existing, Streamlit-free dashboard/data/*.py
and dashboard/narrative.py functions. No new business logic; no auth; no
write paths. See
docs/superpowers/specs/2026-07-12-frontend-rewrite-spike-design.md and
docs/superpowers/specs/2026-07-12-overview-identity-zone-port-design.md.
"""
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.db import get_db_connections

import data
import narrative

app = FastAPI(title="Chesswright API")

# The Vite dev server (5173) and this API (8123) are different origins,
# so the browser blocks the frontend's fetch() calls without this --
# found live while verifying Task 7 (requests failed with a CORS error,
# page stuck on "Loading..." forever). Wide open on purpose: spike-only,
# localhost-bound, no auth, read-only endpoints (see module docstring).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
)


class _TTLCache:
    """Small hand-written cache for one expensive, argument-less
    computation -- not a general caching framework. 60s bounds staleness
    to roughly one minute after a mid-session sync/analysis batch changes
    the underlying data, rather than caching until process restart
    (functools.lru_cache with no TTL was considered and rejected for this
    reason -- see the Overview identity-zone port design spec)."""

    def __init__(self, ttl_seconds):
        self._ttl_seconds = ttl_seconds
        self._value = None
        self._computed_at = None

    def get(self, compute):
        now = time.monotonic()
        if self._computed_at is None or (now - self._computed_at) > self._ttl_seconds:
            self._value = compute()
            self._computed_at = now
        return self._value

    def clear(self):
        self._value = None
        self._computed_at = None


_narrative_cache = _TTLCache(60)
_career_findings_cache = _TTLCache(60)


def reset_caches():
    """Test-only hook: api.main is a singleton module shared across every
    test in a pytest process, so a cache populated by one test would
    otherwise leak into the next one."""
    _narrative_cache.clear()
    _career_findings_cache.clear()


@app.get("/api/overview/headline-stats")
def headline_stats():
    sqlite_conn, duck_conn = get_db_connections()
    return data.get_headline_stats(duck_conn, sqlite_conn)


@app.get("/api/overview/rating-trajectory")
def rating_trajectory():
    _, duck_conn = get_db_connections()
    df = data.get_rating_trajectory(duck_conn)
    return df.to_dict(orient="records")


@app.get("/api/overview/rating-snapshot")
def rating_snapshot():
    _, duck_conn = get_db_connections()
    return data.get_rating_snapshot(duck_conn)


@app.get("/api/overview/current-streak")
def current_streak():
    _, duck_conn = get_db_connections()
    return data.get_current_streak(duck_conn)


@app.get("/api/overview/career-findings")
def career_findings():
    def compute():
        sqlite_conn, duck_conn = get_db_connections()
        stats = data.get_headline_stats(duck_conn, sqlite_conn)
        if stats.get("analyzed_games", 0) == 0:
            return []
        return data.get_career_findings(duck_conn, sqlite_conn, stats.get("blunder_rate"))
    return _career_findings_cache.get(compute)


@app.get("/api/overview/narrative")
def narrative_endpoint():
    def compute():
        sqlite_conn, duck_conn = get_db_connections()
        stats = data.get_headline_stats(duck_conn, sqlite_conn)
        rating_df = data.get_rating_trajectory(duck_conn)
        explorer_df = data.get_game_explorer_table(duck_conn)
        top_game = explorer_df.iloc[0] if len(explorer_df) else None
        return {"narrative": narrative.generate_career_narrative(stats, rating_df, top_game)}
    return _narrative_cache.get(compute)


@app.get("/api/nav/pages")
def nav_pages():
    return data.PAGE_CANDIDATES + data.SETTINGS_CANDIDATES
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest tests/integration/test_api_overview.py -v`
Expected: all tests PASS (existing 4 + new 5 = 9 tests).

- [ ] **Step 5: Commit**

```bash
git add api/main.py tests/integration/test_api_overview.py
git commit -m "Add current-streak, career-findings, and narrative endpoints with TTL cache"
```

---

## Task 2: Frontend — `useOverviewData` hook

**Files:**
- Create: `frontend/src/hooks/useOverviewData.ts`
- Test: `frontend/src/hooks/useOverviewData.test.ts`

**Interfaces:**
- Consumes: the 5 endpoints from Task 1 plus the 2 pre-existing ones
  (`GET /api/overview/headline-stats`, `GET /api/overview/rating-snapshot`,
  `GET /api/overview/current-streak`, `GET /api/overview/career-findings`,
  `GET /api/overview/narrative`), same `API_BASE = 'http://127.0.0.1:8123'`
  convention as `frontend/src/hooks/usePageCandidates.ts`.
- Produces: `useOverviewData(): OverviewData` and the exported types
  `HeadlineStats`, `RatingSnapshot`, `Streak`, `Finding`, `OverviewData` — Task 3's
  `OverviewPage` and its test import these directly from this file.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/hooks/useOverviewData.test.ts`:

```ts
import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useOverviewData } from './useOverviewData'

const SAMPLE_STATS = {
  total_games: 100, analyzed_games: 40, acpl: 45.2, blunder_rate: 5.1,
  win_pct: 52.3, n_analyzed_moves: 4000,
}
const SAMPLE_RATING_SNAPSHOT = { current_rating: 1500, peak_rating: 1550 }
const SAMPLE_STREAK = { outcome: 'win', length: 3 }
const SAMPLE_FINDINGS = [
  { title: 'Sharp attacker', headline: 'h', detail: 'd', polarity: 'strength',
    severity: 'medium', category: 'tactical' },
]
const SAMPLE_NARRATIVE_RESPONSE = { narrative: 'Test narrative text.' }

const RESPONSES: Record<string, unknown> = {
  '/api/overview/headline-stats': SAMPLE_STATS,
  '/api/overview/rating-snapshot': SAMPLE_RATING_SNAPSHOT,
  '/api/overview/current-streak': SAMPLE_STREAK,
  '/api/overview/career-findings': SAMPLE_FINDINGS,
  '/api/overview/narrative': SAMPLE_NARRATIVE_RESPONSE,
}

function mockFetchSuccess() {
  return vi.fn((url: string) => {
    const path = new URL(url).pathname
    return Promise.resolve({ ok: true, json: async () => RESPONSES[path] })
  })
}

describe('useOverviewData', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('starts in a loading state with no error', () => {
    vi.stubGlobal('fetch', mockFetchSuccess())
    const { result } = renderHook(() => useOverviewData())
    expect(result.current.loading).toBe(true)
    expect(result.current.error).toBe(false)
  })

  it('populates all fields when every request succeeds', async () => {
    vi.stubGlobal('fetch', mockFetchSuccess())
    const { result } = renderHook(() => useOverviewData())

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })
    expect(result.current.error).toBe(false)
    expect(result.current.stats).toEqual(SAMPLE_STATS)
    expect(result.current.ratingSnapshot).toEqual(SAMPLE_RATING_SNAPSHOT)
    expect(result.current.streak).toEqual(SAMPLE_STREAK)
    expect(result.current.findings).toEqual(SAMPLE_FINDINGS)
    expect(result.current.narrative).toBe('Test narrative text.')
  })

  it('reports a page-level error if every request fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network error')))
    const { result } = renderHook(() => useOverviewData())

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })
    expect(result.current.error).toBe(true)
    expect(result.current.stats).toBeNull()
    expect(result.current.narrative).toBeNull()
  })

  it('reports a page-level error if a single request returns not-ok', async () => {
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      const path = new URL(url).pathname
      if (path === '/api/overview/narrative') {
        return Promise.resolve({ ok: false, status: 500 })
      }
      return Promise.resolve({ ok: true, json: async () => RESPONSES[path] })
    }))
    const { result } = renderHook(() => useOverviewData())

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })
    expect(result.current.error).toBe(true)
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- useOverviewData`
Expected: FAIL — `Cannot find module './useOverviewData'`.

- [ ] **Step 3: Implement the hook**

Create `frontend/src/hooks/useOverviewData.ts`:

```ts
import { useEffect, useState } from 'react'

const API_BASE = 'http://127.0.0.1:8123'

export interface HeadlineStats {
  total_games: number
  analyzed_games: number
  acpl: number | null
  blunder_rate: number | null
  win_pct: number | null
  n_analyzed_moves: number
}

export interface RatingSnapshot {
  current_rating: number | null
  peak_rating: number | null
}

export interface Streak {
  outcome: string | null
  length: number
}

export interface Finding {
  title: string
  headline: string
  detail: string
  polarity: 'strength' | 'weakness' | 'mixed' | 'neutral'
  severity: 'low' | 'medium' | 'high'
  category: 'tactical' | 'time' | 'defense' | 'matchup' | 'giant_killer' | 'general'
  confidence?: 'insufficient' | 'low' | 'medium' | 'high'
}

export interface OverviewData {
  stats: HeadlineStats | null
  ratingSnapshot: RatingSnapshot | null
  streak: Streak | null
  findings: Finding[] | null
  narrative: string | null
  loading: boolean
  error: boolean
}

async function fetchJson<T>(path: string): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`)
  if (!r.ok) throw new Error(`status ${r.status}`)
  return r.json() as Promise<T>
}

const EMPTY_STATE: OverviewData = {
  stats: null,
  ratingSnapshot: null,
  streak: null,
  findings: null,
  narrative: null,
  loading: true,
  error: false,
}

export function useOverviewData(): OverviewData {
  const [state, setState] = useState<OverviewData>(EMPTY_STATE)

  useEffect(() => {
    let cancelled = false

    Promise.all([
      fetchJson<HeadlineStats>('/api/overview/headline-stats'),
      fetchJson<RatingSnapshot>('/api/overview/rating-snapshot'),
      fetchJson<Streak>('/api/overview/current-streak'),
      fetchJson<Finding[]>('/api/overview/career-findings'),
      fetchJson<{ narrative: string }>('/api/overview/narrative'),
    ])
      .then(([stats, ratingSnapshot, streak, findings, narrativeResp]) => {
        if (!cancelled) {
          setState({
            stats,
            ratingSnapshot,
            streak,
            findings,
            narrative: narrativeResp.narrative,
            loading: false,
            error: false,
          })
        }
      })
      .catch(() => {
        if (!cancelled) {
          setState({ ...EMPTY_STATE, loading: false, error: true })
        }
      })

    return () => {
      cancelled = true
    }
  }, [])

  return state
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm test -- useOverviewData`
Expected: PASS (4/4 tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/hooks/useOverviewData.ts frontend/src/hooks/useOverviewData.test.ts
git commit -m "Add useOverviewData hook for the Overview identity zone"
```

---

## Task 3: Frontend — `OverviewPage` component

**Files:**
- Create: `frontend/src/pages/OverviewPage.tsx`
- Test: `frontend/src/pages/OverviewPage.test.tsx`

**Interfaces:**
- Consumes: `useOverviewData()` and the `Finding` type from
  `frontend/src/hooks/useOverviewData.ts` (Task 2).
- Produces: `export default function OverviewPage(): JSX.Element` — Task 4 wires
  this into `App.tsx` at the `/overview` route. Always renders an `<h1>Overview</h1>`
  heading (matches `PageStub`'s existing page-title convention and keeps
  `App.test.tsx`'s `/` redirect assertion meaningful regardless of loading/error
  state), then one of: a loading paragraph, an error paragraph, or the full
  identity zone content.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/pages/OverviewPage.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import OverviewPage from './OverviewPage'
import type { OverviewData } from '../hooks/useOverviewData'

const mockUseOverviewData = vi.fn()
vi.mock('../hooks/useOverviewData', () => ({
  useOverviewData: () => mockUseOverviewData(),
}))

const EMPTY: OverviewData = {
  stats: null, ratingSnapshot: null, streak: null, findings: null, narrative: null,
  loading: false, error: false,
}

describe('OverviewPage', () => {
  it('always renders the Overview heading', () => {
    mockUseOverviewData.mockReturnValue({ ...EMPTY, loading: true })
    render(<OverviewPage />)
    expect(screen.getByRole('heading', { name: 'Overview' })).toBeInTheDocument()
  })

  it('shows a loading indicator while loading', () => {
    mockUseOverviewData.mockReturnValue({ ...EMPTY, loading: true })
    render(<OverviewPage />)
    expect(screen.getByText(/loading/i)).toBeInTheDocument()
  })

  it('shows an error message when loading fails', () => {
    mockUseOverviewData.mockReturnValue({ ...EMPTY, loading: false, error: true })
    render(<OverviewPage />)
    expect(screen.getByText(/couldn.t load/i)).toBeInTheDocument()
  })

  it('renders the identity zone from sample data', () => {
    mockUseOverviewData.mockReturnValue({
      stats: { total_games: 100, analyzed_games: 40, acpl: 45.2, blunder_rate: 5.1,
               win_pct: 52.3, n_analyzed_moves: 4000 },
      ratingSnapshot: { current_rating: 1500, peak_rating: 1550 },
      streak: { outcome: 'win', length: 3 },
      findings: [
        { title: 'Sharp attacker', headline: 'h', detail: 'd', polarity: 'strength',
          severity: 'medium', category: 'tactical' },
        { title: 'Time trouble', headline: 'h', detail: 'd', polarity: 'weakness',
          severity: 'high', category: 'time' },
      ],
      narrative: 'You have played 100 games.',
      loading: false,
      error: false,
    })
    render(<OverviewPage />)

    expect(screen.getByText('Sharp attacker')).toBeInTheDocument()
    expect(screen.getByText('Time trouble')).toBeInTheDocument()
    expect(screen.getByText('1500')).toBeInTheDocument()
    expect(screen.getByText('peak 1550')).toBeInTheDocument()
    expect(screen.getByText(/3-game win streak/)).toBeInTheDocument()
    expect(screen.getByText('You have played 100 games.')).toBeInTheDocument()
    expect(screen.getByText('100')).toBeInTheDocument()
    expect(screen.getByText('40')).toBeInTheDocument()
    expect(screen.getByText('52.3%')).toBeInTheDocument()
    expect(screen.getByText('45.2')).toBeInTheDocument()
  })

  it('caps trait tags at 3 and prioritizes strengths', () => {
    mockUseOverviewData.mockReturnValue({
      stats: { total_games: 10, analyzed_games: 10, acpl: 40, blunder_rate: 4,
               win_pct: 50, n_analyzed_moves: 100 },
      ratingSnapshot: { current_rating: 1400, peak_rating: 1400 },
      streak: { outcome: null, length: 0 },
      findings: [
        { title: 'Strength A', headline: 'h', detail: 'd', polarity: 'strength', severity: 'low', category: 'general' },
        { title: 'Strength B', headline: 'h', detail: 'd', polarity: 'strength', severity: 'low', category: 'general' },
        { title: 'Weakness A', headline: 'h', detail: 'd', polarity: 'weakness', severity: 'low', category: 'general' },
        { title: 'Weakness B', headline: 'h', detail: 'd', polarity: 'weakness', severity: 'low', category: 'general' },
      ],
      narrative: 'Narrative.',
      loading: false,
      error: false,
    })
    render(<OverviewPage />)

    expect(screen.getByText('Strength A')).toBeInTheDocument()
    expect(screen.getByText('Strength B')).toBeInTheDocument()
    expect(screen.getByText('Weakness A')).toBeInTheDocument()
    expect(screen.queryByText('Weakness B')).not.toBeInTheDocument()
    expect(screen.getByText('at peak')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- OverviewPage`
Expected: FAIL — `Cannot find module './OverviewPage'`.

- [ ] **Step 3: Implement the component**

Create `frontend/src/pages/OverviewPage.tsx`:

```tsx
import { useOverviewData, type Finding } from '../hooks/useOverviewData'

// Same logic as dashboard/overview_view.py's _split_by_polarity + the
// tags = [...][:3] line in _render_identity_zone: top 2 strengths, top 2
// weakness-or-mixed findings, concatenated and capped at 3.
function topTraitTags(findings: Finding[]): Finding[] {
  const strengths = findings.filter((f) => f.polarity === 'strength').slice(0, 2)
  const weaknesses = findings
    .filter((f) => f.polarity === 'weakness' || f.polarity === 'mixed')
    .slice(0, 2)
  return [...strengths, ...weaknesses].slice(0, 3)
}

export default function OverviewPage() {
  const { stats, ratingSnapshot, streak, findings, narrative, loading, error } =
    useOverviewData()

  return (
    <div className="p-8">
      <h1 className="text-2xl font-semibold text-text">Overview</h1>

      {loading && <p className="mt-4 text-text-muted">Loading…</p>}

      {!loading && error && (
        <p className="mt-4 text-negative">
          Couldn&apos;t load your Overview data. Confirm the Chesswright API server
          is running.
        </p>
      )}

      {!loading && !error && stats && ratingSnapshot && streak && findings && narrative !== null && (
        <div className="mt-4">
          <div className="flex gap-2">
            {topTraitTags(findings).map((f) => (
              <span
                key={f.title}
                className="rounded-full bg-bg-secondary px-3 py-1 text-sm text-accent-gold"
              >
                {f.title}
              </span>
            ))}
          </div>

          {ratingSnapshot.current_rating !== null && (
            <div className="mt-4">
              <span className="text-3xl font-semibold text-text">
                {ratingSnapshot.current_rating}
              </span>
              {ratingSnapshot.peak_rating !== null && (
                <span className="ml-2 text-sm text-text-muted">
                  {ratingSnapshot.current_rating < ratingSnapshot.peak_rating
                    ? `peak ${ratingSnapshot.peak_rating}`
                    : 'at peak'}
                </span>
              )}
              <div className="text-xs text-text-muted">
                Current rating
                {streak.length >= 2 ? ` · ${streak.length}-game ${streak.outcome} streak` : ''}
              </div>
            </div>
          )}

          <p className="mt-4 max-w-2xl text-text">{narrative}</p>

          <div className="mt-6 grid grid-cols-4 gap-4">
            <div>
              <div className="text-xs text-text-muted">Total games</div>
              <div className="text-xl text-text">{stats.total_games.toLocaleString()}</div>
            </div>
            <div>
              <div className="text-xs text-text-muted">Analyzed games</div>
              <div className="text-xl text-text">{stats.analyzed_games.toLocaleString()}</div>
            </div>
            <div>
              <div className="text-xs text-text-muted">Win rate</div>
              <div className="text-xl text-text">
                {stats.win_pct !== null ? `${stats.win_pct.toFixed(1)}%` : '--'}
              </div>
            </div>
            <div>
              <div className="text-xs text-text-muted">ACPL</div>
              <div className="text-xl text-text">
                {stats.acpl !== null ? stats.acpl.toFixed(1) : '--'}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm test -- OverviewPage`
Expected: PASS (5/5 tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/OverviewPage.tsx frontend/src/pages/OverviewPage.test.tsx
git commit -m "Add OverviewPage identity zone component"
```

---

## Task 4: Wire `OverviewPage` into the route table

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/App.test.tsx`

**Interfaces:**
- Consumes: `OverviewPage` (Task 3, default export), `useOverviewData` (Task 2, for
  the test mock).

- [ ] **Step 1: Update the failing/changed test first**

Modify `frontend/src/App.test.tsx` to mock `useOverviewData` (the real hook would
otherwise attempt a real `fetch` during the test) and add a case proving the wiring:

```tsx
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import App from './App'
import { STATIC_CANDIDATES } from './lib/navCandidates'
import type { OverviewData } from './hooks/useOverviewData'

vi.mock('./hooks/usePageCandidates', () => ({
  usePageCandidates: () => ({ candidates: STATIC_CANDIDATES, usingFallback: false }),
}))

const OVERVIEW_LOADING: OverviewData = {
  stats: null, ratingSnapshot: null, streak: null, findings: null, narrative: null,
  loading: true, error: false,
}
vi.mock('./hooks/useOverviewData', () => ({
  useOverviewData: () => OVERVIEW_LOADING,
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

  it('renders OverviewPage (not PageStub) at /overview', () => {
    renderAt('/overview')
    expect(screen.getByText(/loading/i)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run the test to verify the new case fails**

Run: `cd frontend && npm test -- App.test`
Expected: the new third test FAILS (no "Loading…" text — `/overview` still renders
`PageStub`, which has no such text). The first two tests should still PASS
unaffected.

- [ ] **Step 3: Wire `OverviewPage` into `App.tsx`**

Replace the full contents of `frontend/src/App.tsx` with:

```tsx
import { Navigate, Route, Routes } from 'react-router-dom'
import Shell from './components/Shell'
import PageStub from './pages/PageStub'
import OverviewPage from './pages/OverviewPage'
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
            element={
              page.url_path === 'overview' ? <OverviewPage /> : <PageStub title={page.title} />
            }
          />
        ))}
      </Route>
    </Routes>
  )
}
```

- [ ] **Step 4: Run the tests and typecheck to verify they pass**

Run: `cd frontend && npm test -- App.test && npm run typecheck`
Expected: all 3 `App.test.tsx` cases PASS; `tsc --noEmit` reports no errors.

- [ ] **Step 5: Run the full frontend test suite**

Run: `cd frontend && npm test`
Expected: all tests across the whole suite PASS (no regressions in `Sidebar`,
`CommandPalette`, `usePageCandidates`, etc.).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/App.tsx frontend/src/App.test.tsx
git commit -m "Route /overview to OverviewPage instead of PageStub"
```

---

## Task 5: Live verification and roadmap update

**⚠️ Run this task directly yourself — do not dispatch it to a subagent.** Per this
project's standing directive (`orchestrator_runs_tests_not_subagents` memory), a
subagent launching its own dev servers can hang waiting on a notification channel
that isn't its own. This task also requires the Playwright MCP browser tools.

**Files:**
- Modify: `docs/scoping/frontend-rewrite-development-path-2026-07-12.md`

- [ ] **Step 1: Run the full backend test suite once more**

Run: `python3 -m pytest tests/integration/test_api_overview.py -v`
Expected: 9/9 PASS.

- [ ] **Step 2: Start the backend dev server**

```bash
python3 -m uvicorn api.main:app --host 127.0.0.1 --port 8123 &
```

Confirm it's serving: `curl -s http://127.0.0.1:8123/api/overview/narrative`
Expected: `{"narrative":"No games yet -- fetch some games to get started."}` if the
real dev DB has no games yet, or a real narrative string if it has data — either
way, a 200 response, not an error.

Also fetch and note down the current real values for comparison in Step 4:

```bash
curl -s http://127.0.0.1:8123/api/overview/headline-stats
curl -s http://127.0.0.1:8123/api/overview/rating-snapshot
curl -s http://127.0.0.1:8123/api/overview/current-streak
curl -s http://127.0.0.1:8123/api/overview/career-findings
curl -s http://127.0.0.1:8123/api/overview/narrative
```

- [ ] **Step 3: Start the frontend dev server**

```bash
cd frontend && npm run dev &
cd ..
```

Confirm it's serving: `curl -s http://127.0.0.1:5173 | head -c 200`
Expected: the Vite dev HTML shell (200 response).

- [ ] **Step 4: Live-verify with the Playwright MCP tools**

Using `mcp__plugin_playwright_playwright__browser_navigate` and the other Playwright
MCP tools available in this session, against `http://127.0.0.1:5173`:

1. Navigate to `/overview`. Confirm the page renders (not stuck on "Loading…" —
   wait for it to settle) and shows: the "Overview" heading, up to 3 trait tags, a
   current-rating number, the narrative paragraph, and the 4 metric cards (Total
   games, Analyzed games, Win rate, ACPL).
2. Cross-check every number and the narrative text shown against the `curl`
   responses captured in Step 2 — they must match exactly (this is the
   spec's "correctness sanity check, not a pixel-diff").
3. Take a screenshot for a visual sanity check (readable, not broken layout —
   pixel parity with the old Streamlit page is explicitly out of scope).
4. Check console messages
   (`mcp__plugin_playwright_playwright__browser_console_messages`). Confirm zero
   errors.
5. Navigate to `/` directly (fresh navigation). Confirm it redirects to `/overview`
   and renders the same content as step 1 — proves the route wiring from Task 4,
   not just client-side state.
6. Confirm the TTL cache is actually effective: time a cold request against a warm
   one for each cached endpoint —
   `time curl -s http://127.0.0.1:8123/api/overview/narrative > /dev/null` followed
   immediately by a second identical `time curl` call, then the same pair for
   `/api/overview/career-findings`. Expect the second call in each pair to be
   noticeably faster (served from the 60s in-process cache, no recomputation).
7. Stop the frontend dev server, kill the `uvicorn` process, confirm no orphaned
   processes remain (`ps aux | grep -E "vite|uvicorn"`).

If any check fails, fix the relevant frontend/backend code from the task that owns
it, re-run that task's automated tests, then repeat this Step 4 from the top.

- [ ] **Step 5: Update the roadmap doc**

In `docs/scoping/frontend-rewrite-development-path-2026-07-12.md`, after the
existing "Phase 3 update (2026-07-12): app-shell slice done." paragraph at the end
of the file, add a new dated paragraph in the same style, summarizing: the 3 new
endpoints and the 60s TTL cache mechanism, the `useOverviewData` +
`OverviewPage` frontend pieces, and the concrete live-verified numbers/narrative
observed in Step 4 (current rating, streak, the 4 metric card values). Note
explicitly that Evolution and Coaching zones, achievements, the engine-status
strip, and the career-highlight teaser remain deferred to follow-on slices, per the
design spec's "Out of scope" section.

- [ ] **Step 6: Commit the roadmap update**

```bash
git add docs/scoping/frontend-rewrite-development-path-2026-07-12.md
git commit -m "Record Overview identity-zone slice as live-verified in the roadmap"
```

---

After all 5 tasks are complete and verified, use
**superpowers:finishing-a-development-branch** to decide how to integrate this work
(this branch already tracks `origin/worktree-frontend-spike` with no PR yet, per
project memory — follow that skill's prompts rather than assuming a default here).
