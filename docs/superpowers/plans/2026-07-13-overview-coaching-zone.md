# Overview Coaching Zone Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port `dashboard/overview_view.py`'s `_render_coaching_zone` (strengths/weaknesses balance, ranked focus-areas list, coaching-plan CTA, quick-links row) into the React rewrite's Overview page.

**Architecture:** One new thin-wrapper FastAPI endpoint for the one piece of new data this zone needs (whether an AI coaching-plan narrative is already cached); everything else reuses `findings`, which `useOverviewData()` already fetches. A new `useCoachingPlanStatus` hook (independent, same shape as `useMilestones`/`useCareerHighlight`) and a new `CoachingZone` component, wired into `OverviewPage.tsx` after `CareerHighlight`.

**Tech Stack:** FastAPI (Python), React + TypeScript, Vitest + Testing Library, react-router-dom `Link`, Tailwind (existing `@theme` tokens only, no new CSS).

## Global Constraints

- Working directory for all steps: `/home/jasper/Desktop/wider_release/chess_app/.claude/worktrees/frontend-spike` (the `worktree-frontend-spike` branch — not the main checkout).
- No pixel parity with `OVERVIEW_CSS`'s bespoke Streamlit styling — use existing Tailwind `@theme` tokens (`bg`, `bg-secondary`, `accent-gold`, `positive`, `negative`, `text`, `text-muted`) only.
- No new backend caching beyond the one endpoint specified — it's a single indexed SQLite lookup, same bar as `current-streak`/`achievements`.
- Ranked focus-list behavior must match the Streamlit original exactly, including its apparent off-by-one (weaknesses are capped at 2 by `_split_by_polarity` before the ranked list's own `[:3]` ever applies) — this plan ports that behavior, it does not fix it.
- Links to `/patterns`, `/matchups`, `/game-endings`, `/tactical-highlights`, `/insights`, `/openings` must be real `<Link>` navigation (these routes exist and render `PageStub`), not inert like `CareerHighlight`'s Game Detail link.
- Python code style: no comments except where a hidden constraint/reason needs explaining (matches every file read during scoping). TypeScript/React code style: no semicolons, single quotes, matches every existing file in `frontend/src`.

---

### Task 1: Backend — `/api/overview/coaching-plan-status` endpoint

**Files:**
- Modify: `api/main.py` (add one new endpoint, after `career_highlight` at line 151, before `nav_pages`)
- Test: `tests/integration/test_api_overview.py` (add two new tests, after `test_achievements_endpoint_returns_unlocked_achievements`, before `test_config_default_path_restored_after_api_client_tests`)

**Interfaces:**
- Consumes: `data.get_cached_narrative(sqlite_conn, subject_type, subject_key)` (`dashboard/data/_shared.py:143`, already imported as `data` in `api/main.py`) — returns `(response_text, generated_at)` tuple or `None`.
- Produces: `GET /api/overview/coaching-plan-status` → `{"cached": bool}`, consumed by Task 2's hook.

- [ ] **Step 1: Write the failing tests**

Add to `tests/integration/test_api_overview.py`, directly after `test_achievements_endpoint_returns_unlocked_achievements` (before `test_config_default_path_restored_after_api_client_tests`):

```python
@pytest.mark.integration
def test_coaching_plan_status_endpoint_no_cached_narrative(api_client):
    resp = api_client.get("/api/overview/coaching-plan-status")
    assert resp.status_code == 200
    assert resp.json() == {"cached": False}


@pytest.mark.integration
def test_coaching_plan_status_endpoint_with_cached_narrative(api_client, monkeypatch):
    import data

    def fake_get_cached_narrative(conn, subject_type, subject_key):
        assert subject_type == "coaching"
        assert subject_key == "recommendations"
        return ("Some cached coaching text.", "2026-01-01T00:00:00")

    monkeypatch.setattr(data, "get_cached_narrative", fake_get_cached_narrative)

    resp = api_client.get("/api/overview/coaching-plan-status")
    assert resp.status_code == 200
    assert resp.json() == {"cached": True}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/integration/test_api_overview.py -k coaching_plan_status -v`
Expected: FAIL — `404 Not Found` (route doesn't exist yet) on both tests.

- [ ] **Step 3: Implement the endpoint**

In `api/main.py`, insert directly after the `career_highlight` function (after line 151, before the `@app.get("/api/nav/pages")` block):

```python
@app.get("/api/overview/coaching-plan-status")
def coaching_plan_status():
    sqlite_conn, _ = get_db_connections()
    return {"cached": bool(data.get_cached_narrative(sqlite_conn, "coaching", "recommendations"))}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/integration/test_api_overview.py -k coaching_plan_status -v`
Expected: PASS (2 passed)

Also run the full file to confirm no regressions:
Run: `python3 -m pytest tests/integration/test_api_overview.py -v`
Expected: all tests pass (17 passed, up from 15)

- [ ] **Step 5: Commit**

```bash
git add api/main.py tests/integration/test_api_overview.py
git commit -m "Add /api/overview/coaching-plan-status endpoint"
```

---

### Task 2: Frontend — `useCoachingPlanStatus` hook

**Files:**
- Create: `frontend/src/hooks/useCoachingPlanStatus.ts`
- Test: `frontend/src/hooks/useCoachingPlanStatus.test.ts`

**Interfaces:**
- Consumes: `GET /api/overview/coaching-plan-status` → `{"cached": bool}` (Task 1).
- Produces: `useCoachingPlanStatus(): { cached: boolean | null; loading: boolean; error: boolean }`, consumed by Task 4's `OverviewPage.tsx` wiring.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/hooks/useCoachingPlanStatus.test.ts`:

```typescript
import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useCoachingPlanStatus } from './useCoachingPlanStatus'

function mockFetchSuccess(body: unknown) {
  return vi.fn(() => Promise.resolve({ ok: true, json: async () => body }))
}

describe('useCoachingPlanStatus', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('starts in a loading state with no error', async () => {
    vi.stubGlobal('fetch', mockFetchSuccess({ cached: false }))
    const { result } = renderHook(() => useCoachingPlanStatus())
    expect(result.current.loading).toBe(true)
    expect(result.current.error).toBe(false)

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })
  })

  it('reports cached: true when the API says a plan is already cached', async () => {
    vi.stubGlobal('fetch', mockFetchSuccess({ cached: true }))
    const { result } = renderHook(() => useCoachingPlanStatus())

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })
    expect(result.current.error).toBe(false)
    expect(result.current.cached).toBe(true)
  })

  it('reports cached: false when no plan has been generated yet', async () => {
    vi.stubGlobal('fetch', mockFetchSuccess({ cached: false }))
    const { result } = renderHook(() => useCoachingPlanStatus())

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })
    expect(result.current.error).toBe(false)
    expect(result.current.cached).toBe(false)
  })

  it('reports an error state if the request fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network error')))
    const { result } = renderHook(() => useCoachingPlanStatus())

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })
    expect(result.current.error).toBe(true)
    expect(result.current.cached).toBeNull()
  })

  it('reports an error state on a non-ok response', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: false, status: 500 })))
    const { result } = renderHook(() => useCoachingPlanStatus())

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })
    expect(result.current.error).toBe(true)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/hooks/useCoachingPlanStatus.test.ts`
Expected: FAIL — cannot find module `./useCoachingPlanStatus`

- [ ] **Step 3: Implement the hook**

Create `frontend/src/hooks/useCoachingPlanStatus.ts`:

```typescript
import { useEffect, useState } from 'react'

const API_BASE = 'http://127.0.0.1:8123'

export interface CoachingPlanStatusData {
  cached: boolean | null
  loading: boolean
  error: boolean
}

const EMPTY_STATE: CoachingPlanStatusData = {
  cached: null,
  loading: true,
  error: false,
}

export function useCoachingPlanStatus(): CoachingPlanStatusData {
  const [state, setState] = useState<CoachingPlanStatusData>(EMPTY_STATE)

  useEffect(() => {
    let cancelled = false

    fetch(`${API_BASE}/api/overview/coaching-plan-status`)
      .then((r) => {
        if (!r.ok) throw new Error(`status ${r.status}`)
        return r.json() as Promise<{ cached: boolean }>
      })
      .then((body) => {
        if (!cancelled) {
          setState({ cached: body.cached, loading: false, error: false })
        }
      })
      .catch(() => {
        if (!cancelled) {
          setState({ cached: null, loading: false, error: true })
        }
      })

    return () => {
      cancelled = true
    }
  }, [])

  return state
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/hooks/useCoachingPlanStatus.test.ts`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/hooks/useCoachingPlanStatus.ts frontend/src/hooks/useCoachingPlanStatus.test.ts
git commit -m "Add useCoachingPlanStatus hook for the Overview Coaching zone"
```

---

### Task 3: Frontend — `CoachingZone` component

**Files:**
- Create: `frontend/src/components/CoachingZone.tsx`
- Test: `frontend/src/components/CoachingZone.test.tsx`

**Interfaces:**
- Consumes: `Finding` type (`frontend/src/hooks/useOverviewData.ts:26-33` — `{ title: string; headline: string; detail: string; polarity: 'strength'|'weakness'|'mixed'|'neutral'; severity: 'low'|'medium'|'high'; category: string; confidence?: string }`); `CoachingPlanStatusData['cached']` (Task 2).
- Produces: `export default function CoachingZone({ findings, cached }: { findings: Finding[]; cached: boolean | null })`, consumed by Task 4's `OverviewPage.tsx`.

Needs `react-router-dom` for navigation — already a project dependency (used in `App.tsx`, `Sidebar.tsx`, `CommandPalette.tsx`). `MemoryRouter` is needed to render `<Link>` in isolation in tests (same reason `App.tsx`'s own tests wrap in a router — check `frontend/src/App.test.tsx` if the pattern needs confirming, but `MemoryRouter` from `react-router-dom` is the standard RTL approach for components using `Link`/`NavLink` outside a full app render).

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/CoachingZone.test.tsx`:

```typescript
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import CoachingZone from './CoachingZone'
import type { Finding } from '../hooks/useOverviewData'

function renderZone(findings: Finding[], cached: boolean | null) {
  return render(
    <MemoryRouter>
      <CoachingZone findings={findings} cached={cached} />
    </MemoryRouter>,
  )
}

describe('CoachingZone', () => {
  it('renders the heading, CTA, and quick links but no balance/ranked sections when findings is empty', () => {
    renderZone([], null)

    expect(screen.getByText('Your coaching plan')).toBeInTheDocument()
    expect(screen.getByText('Get your coaching plan →')).toBeInTheDocument()
    expect(screen.getByText('Insights')).toBeInTheDocument()
    expect(screen.getByText('Patterns & Tendencies')).toBeInTheDocument()
    expect(screen.getByText('Openings & Repertoire')).toBeInTheDocument()
    expect(screen.queryByText('Strengths')).not.toBeInTheDocument()
    expect(screen.queryByText('Focus areas')).not.toBeInTheDocument()
    expect(screen.queryByText(/is your top focus area/)).not.toBeInTheDocument()
  })

  it('shows "Get your coaching plan" when cached is false', () => {
    renderZone([], false)
    expect(screen.getByText('Get your coaching plan →')).toBeInTheDocument()
  })

  it('shows "View your coaching plan" when cached is true', () => {
    renderZone([], true)
    expect(screen.getByText('View your coaching plan →')).toBeInTheDocument()
  })

  it('splits findings into strengths/weaknesses columns, caps the ranked list at the top 2 weaknesses in list order, and links mapped findings to their origin page', () => {
    const findings: Finding[] = [
      { title: 'Sharp attacker', headline: 'h', detail: 'Finds tactics often',
        polarity: 'strength', severity: 'medium', category: 'tactical' },
      { title: 'Solid defense', headline: 'h', detail: 'Rarely blunders material',
        polarity: 'strength', severity: 'low', category: 'defense' },
      { title: 'Piece blunder hot-spot', headline: 'h', detail: 'Loses pieces under pressure',
        polarity: 'weakness', severity: 'high', category: 'tactical' },
      { title: 'Unmapped finding', headline: 'h', detail: 'No destination page for this one',
        polarity: 'weakness', severity: 'medium', category: 'general' },
      { title: 'Toughest opponent', headline: 'h', detail: 'Struggles against this player',
        polarity: 'mixed', severity: 'low', category: 'matchup' },
    ]
    renderZone(findings, null)

    expect(screen.getByText('Sharp attacker')).toBeInTheDocument()
    expect(screen.getByText('Solid defense')).toBeInTheDocument()
    expect(screen.getByText('Piece blunder hot-spot')).toBeInTheDocument()
    expect(screen.getByText('Unmapped finding')).toBeInTheDocument()
    // Only the first 2 weakness/mixed findings in list order make it past
    // splitByPolarity -- 'Toughest opponent' is 3rd and is dropped, even
    // though it's a lower severity than one of the two kept.
    expect(screen.queryByText('Toughest opponent')).not.toBeInTheDocument()

    expect(screen.getByText(/Piece blunder hot-spot is your top focus area/)).toBeInTheDocument()

    const patternsLink = screen.getByRole('link', { name: 'Patterns & Tendencies' })
    expect(patternsLink).toHaveAttribute('href', '/patterns')

    expect(screen.queryByRole('link', { name: /Unmapped/ })).not.toBeInTheDocument()
  })

  it('renders no ranked focus-area link for findings with no _FINDING_DEST mapping', () => {
    const findings: Finding[] = [
      { title: 'Some novel finding', headline: 'h', detail: 'd',
        polarity: 'weakness', severity: 'high', category: 'general' },
    ]
    renderZone(findings, null)

    expect(screen.getByText('Some novel finding')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Some novel finding' })).not.toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/CoachingZone.test.tsx`
Expected: FAIL — cannot find module `./CoachingZone`

- [ ] **Step 3: Implement the component**

Create `frontend/src/components/CoachingZone.tsx`:

```tsx
import { Link } from 'react-router-dom'
import type { Finding } from '../hooks/useOverviewData'

const SEVERITY_DOTS: Record<Finding['severity'], number> = { high: 3, medium: 2, low: 1 }

const FINDING_DEST: Record<string, { path: string; label: string }> = {
  'Piece blunder hot-spot': { path: '/patterns', label: 'Patterns & Tendencies' },
  'Sharp positions and blunder rate': { path: '/patterns', label: 'Patterns & Tendencies' },
  'Thinking time vs. blunder rate': { path: '/patterns', label: 'Patterns & Tendencies' },
  'Clock pressure and blunder rate': { path: '/patterns', label: 'Patterns & Tendencies' },
  'Castling and win rate': { path: '/patterns', label: 'Patterns & Tendencies' },
  'King moves off the back rank': { path: '/patterns', label: 'Patterns & Tendencies' },
  'Toughest opponent': { path: '/matchups', label: 'Matchups & Opponents' },
  'Giant-killing and collapses': { path: '/matchups', label: 'Matchups & Opponents' },
  'Tactical highlights so far': { path: '/tactical-highlights', label: 'Tactical Highlights' },
  'How your games end': { path: '/game-endings', label: 'Game Endings' },
}

const QUICK_LINKS = [
  { path: '/insights', label: 'Insights' },
  { path: '/patterns', label: 'Patterns & Tendencies' },
  { path: '/openings', label: 'Openings & Repertoire' },
]

function splitByPolarity(findings: Finding[]): { strengths: Finding[]; weaknesses: Finding[] } {
  return {
    strengths: findings.filter((f) => f.polarity === 'strength').slice(0, 2),
    weaknesses: findings
      .filter((f) => f.polarity === 'weakness' || f.polarity === 'mixed')
      .slice(0, 2),
  }
}

export default function CoachingZone({
  findings,
  cached,
}: {
  findings: Finding[]
  cached: boolean | null
}) {
  const { strengths, weaknesses } = splitByPolarity(findings)
  const ranked = [...weaknesses]
    .sort((a, b) => SEVERITY_DOTS[b.severity] - SEVERITY_DOTS[a.severity])
    .slice(0, 3)
  const topWeakness = ranked.length > 0 ? ranked[0].title : null
  const ctaLabel = cached ? 'View your coaching plan →' : 'Get your coaching plan →'

  return (
    <div className="mt-6">
      <h2 className="text-xs uppercase tracking-wide text-text-muted">Your coaching plan</h2>

      {(strengths.length > 0 || weaknesses.length > 0) && (
        <div className="mt-2 grid grid-cols-2 gap-4">
          <div>
            <div className="text-xs uppercase tracking-wide text-positive">Strengths</div>
            {strengths.length === 0 && (
              <p className="mt-1 text-xs text-text-muted">
                Nothing surfaced yet — check back after more games are analyzed.
              </p>
            )}
            {strengths.map((f) => (
              <div key={f.title} className="mt-2">
                <div className="text-sm font-medium text-text">{f.title}</div>
                <div className="text-xs text-text-muted">{f.detail}</div>
              </div>
            ))}
          </div>
          <div>
            <div className="text-xs uppercase tracking-wide text-accent-gold">Focus areas</div>
            {weaknesses.length === 0 && (
              <p className="mt-1 text-xs text-text-muted">
                Nothing surfaced yet — check back after more games are analyzed.
              </p>
            )}
            {weaknesses.map((f) => (
              <div key={f.title} className="mt-2">
                <div className="text-sm font-medium text-text">{f.title}</div>
                <div className="text-xs text-text-muted">{f.detail}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {ranked.length > 0 && (
        <div className="mt-4 rounded border border-bg-secondary p-3">
          {ranked.map((f) => {
            const dots = SEVERITY_DOTS[f.severity]
            const dest = FINDING_DEST[f.title]
            return (
              <div key={f.title} className="flex items-center justify-between gap-4 py-1">
                <div>
                  <span className="mr-2 text-xs text-negative">
                    {'●'.repeat(dots)}
                    {'○'.repeat(3 - dots)}
                  </span>
                  <span className="text-sm font-medium text-text">{f.title}</span>
                  <div className="text-xs text-text-muted">{f.detail}</div>
                </div>
                {dest && (
                  <Link
                    to={dest.path}
                    className="shrink-0 rounded border border-bg-secondary px-2 py-1 text-xs text-text hover:bg-bg-secondary/40"
                  >
                    {dest.label}
                  </Link>
                )}
              </div>
            )
          })}
        </div>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-3">
        {topWeakness && (
          <span className="text-xs text-text-muted">
            Because <strong className="text-text">{topWeakness}</strong> is your top focus area —
          </span>
        )}
        <Link
          to="/insights"
          className="rounded border border-accent-gold px-3 py-1.5 text-sm text-accent-gold hover:bg-accent-gold/10"
        >
          {ctaLabel}
        </Link>
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        {QUICK_LINKS.map((link) => (
          <Link
            key={link.path}
            to={link.path}
            className="rounded border border-bg-secondary bg-bg-secondary/40 px-3 py-1.5 text-sm text-text hover:bg-bg-secondary/70"
          >
            {link.label}
          </Link>
        ))}
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/components/CoachingZone.test.tsx`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/CoachingZone.tsx frontend/src/components/CoachingZone.test.tsx
git commit -m "Add CoachingZone component"
```

---

### Task 4: Wire `CoachingZone` into `OverviewPage.tsx`

**Files:**
- Modify: `frontend/src/pages/OverviewPage.tsx`
- Modify: `frontend/src/pages/OverviewPage.test.tsx`

**Interfaces:**
- Consumes: `useCoachingPlanStatus` (Task 2), `CoachingZone` (Task 3), the existing `findings`/`loading`/`error` from `useOverviewData()` (`frontend/src/hooks/useOverviewData.ts`).
- Produces: nothing further downstream — this is the final integration point for this slice.

`CoachingZone` reuses `findings` from `useOverviewData()`, so it renders as soon as `useOverviewData()` resolves successfully (`!loading && !error && findings`) — independent of the other identity-zone-only fields (`stats`, `ratingSnapshot`, `streak`, `narrative`). Two existing tests in `OverviewPage.test.tsx` currently assert on finding titles (e.g. `getByText('Sharp attacker')`) with plain global queries; once `CoachingZone` renders the same finding titles alongside the identity zone's trait tags, those titles appear more than once in the DOM and `getByText` (which requires exactly one match) will throw. Fix: give the identity-zone wrapper a `data-testid` and scope those specific assertions to it with `within(...)`.

- [ ] **Step 1: Add `data-testid="identity-zone"` to the identity-zone wrapper**

In `frontend/src/pages/OverviewPage.tsx`, change the wrapping div (currently, per the file read during scoping):

```tsx
      {!loading && !error && stats && ratingSnapshot && streak && findings && narrative !== null && (
        <div className="mt-4">
```

to:

```tsx
      {!loading && !error && stats && ratingSnapshot && streak && findings && narrative !== null && (
        <div className="mt-4" data-testid="identity-zone">
```

- [ ] **Step 2: Update the two existing tests whose assertions now collide with `CoachingZone`'s output**

In `frontend/src/pages/OverviewPage.test.tsx`:

1. Add `within` to the import on line 1:

```typescript
import { render, screen, within } from '@testing-library/react'
```

2. In `'renders the identity zone from sample data'`, replace:

```typescript
    expect(screen.getByText('Sharp attacker')).toBeInTheDocument()
    expect(screen.getByText('Time trouble')).toBeInTheDocument()
```

with:

```typescript
    const identityZone = screen.getByTestId('identity-zone')
    expect(within(identityZone).getByText('Sharp attacker')).toBeInTheDocument()
    expect(within(identityZone).getByText('Time trouble')).toBeInTheDocument()
```

3. In `'caps trait tags at 3 and prioritizes strengths'`, replace:

```typescript
    expect(screen.getByText('Strength A')).toBeInTheDocument()
    expect(screen.getByText('Strength B')).toBeInTheDocument()
    expect(screen.getByText('Weakness A')).toBeInTheDocument()
    expect(screen.queryByText('Weakness B')).not.toBeInTheDocument()
    expect(screen.getByText('at peak')).toBeInTheDocument()
```

with:

```typescript
    const identityZone = screen.getByTestId('identity-zone')
    expect(within(identityZone).getByText('Strength A')).toBeInTheDocument()
    expect(within(identityZone).getByText('Strength B')).toBeInTheDocument()
    expect(within(identityZone).getByText('Weakness A')).toBeInTheDocument()
    expect(within(identityZone).queryByText('Weakness B')).not.toBeInTheDocument()
    expect(screen.getByText('at peak')).toBeInTheDocument()
```

(`'Weakness B'` is excluded from the identity zone's own top-3 trait-tag cap, but — once `CoachingZone` is wired in below — it *does* appear in the Coaching zone's own top-2 weaknesses column. Scoping to `identity-zone` keeps this assertion testing what it was always meant to test.)

- [ ] **Step 3: Run the test suite to confirm these two tests still pass on their own merits (component not wired in yet)**

Run: `cd frontend && npx vitest run src/pages/OverviewPage.test.tsx`
Expected: PASS (9 tests, unchanged behavior — `data-testid` and `within` scoping don't change what's asserted, just how precisely)

- [ ] **Step 4: Add two new tests for `CoachingZone`'s wiring**

Add to `frontend/src/pages/OverviewPage.test.tsx`, at the end of the `describe` block (after the last existing `it`):

```typescript
  it('renders the coaching zone once findings resolve, even if other identity-zone fields are still missing', () => {
    mockUseOverviewData.mockReturnValue({
      stats: null,
      ratingSnapshot: null,
      streak: null,
      findings: [
        { title: 'Only weakness', headline: 'h', detail: 'd', polarity: 'weakness',
          severity: 'low', category: 'general' },
      ],
      narrative: null,
      loading: false,
      error: false,
    })
    render(<OverviewPage />)

    expect(screen.getByText('Your coaching plan')).toBeInTheDocument()
    expect(screen.getByText('Get your coaching plan →')).toBeInTheDocument()
  })

  it('renders no coaching zone while the overview fetch has not resolved', () => {
    mockUseOverviewData.mockReturnValue({ ...EMPTY, loading: true })
    render(<OverviewPage />)

    expect(screen.queryByText('Your coaching plan')).not.toBeInTheDocument()
  })
```

- [ ] **Step 5: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/pages/OverviewPage.test.tsx`
Expected: FAIL — the two new tests fail (`'Your coaching plan'` not found / found when it shouldn't be — `CoachingZone` isn't wired in yet)

- [ ] **Step 6: Wrap `OverviewPage.test.tsx`'s renders in `MemoryRouter`**

`CoachingZone` (wired in next step) renders `react-router-dom`'s `Link`, which throws
`useHref() may be used only in the context of a <Router> component` when rendered
without a Router ancestor. `OverviewPage.test.tsx` currently calls
`render(<OverviewPage />)` directly with no Router wrapper (it didn't need one before
— `CareerHighlight` uses a plain disabled `<button>`, not `Link`). Fix by adding a
`renderPage()` helper (same `MemoryRouter`-wrapping pattern `App.test.tsx` already
uses) and replacing every `render(<OverviewPage />)` call site with it.

In `frontend/src/pages/OverviewPage.test.tsx`:

1. Add the import, alongside the existing ones:

```typescript
import { MemoryRouter } from 'react-router-dom'
```

2. Add this helper directly after the `EMPTY` constant (before the `describe` block):

```typescript
function renderPage() {
  return render(
    <MemoryRouter>
      <OverviewPage />
    </MemoryRouter>,
  )
}
```

3. Replace every occurrence of `render(<OverviewPage />)` in the file (10 occurrences,
   one per existing `it(...)`) with `renderPage()`. The two new tests added in Step 4
   above should also use `renderPage()`, not `render(<OverviewPage />)` — go back and
   fix those two now too.

- [ ] **Step 7: Wire `CoachingZone` into `OverviewPage.tsx`**

In `frontend/src/pages/OverviewPage.tsx`:

1. Add imports, alongside the existing ones:

```tsx
import CoachingZone from '../components/CoachingZone'
```

and

```tsx
import { useCoachingPlanStatus } from '../hooks/useCoachingPlanStatus'
```

2. Add the hook call, alongside the existing ones:

```tsx
  const { cached } = useCoachingPlanStatus()
```

3. Render `CoachingZone` after `<CareerHighlight game={game} />`:

```tsx
      <CareerHighlight game={game} />
      {!loading && !error && findings && <CoachingZone findings={findings} cached={cached} />}
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/pages/OverviewPage.test.tsx`
Expected: PASS (11 tests, up from 9)

Then run the full frontend suite and typecheck:
Run: `cd frontend && npm test && npm run typecheck`
Expected: all test files pass, typecheck clean

- [ ] **Step 9: Commit**

```bash
git add frontend/src/pages/OverviewPage.tsx frontend/src/pages/OverviewPage.test.tsx
git commit -m "Render CoachingZone on OverviewPage"
```

---

### Task 5: Live-verify against the real dev DB

**Files:** none (verification only, no code changes expected unless this step surfaces a real bug — if it does, fix it as an additional step here before committing, per this project's standing live-verification discipline)

- [ ] **Step 1: Start the API server**

Run (background): `cd /home/jasper/Desktop/wider_release/chess_app/.claude/worktrees/frontend-spike && python3 -m uvicorn api.main:app --port 8123`

- [ ] **Step 2: Start the Vite dev server**

Run (background): `cd /home/jasper/Desktop/wider_release/chess_app/.claude/worktrees/frontend-spike/frontend && npm run dev`

- [ ] **Step 3: Confirm the raw endpoint output against the real dev DB**

Run: `curl -s http://127.0.0.1:8123/api/overview/coaching-plan-status`
Run: `curl -s http://127.0.0.1:8123/api/overview/career-findings`

Note the `cached` boolean and the full findings list — these are the ground truth the rendered page must match.

- [ ] **Step 4: Playwright-verify the rendered page**

Navigate to `http://localhost:5173/overview` with the Playwright MCP tools, wait for the page to finish loading, and screenshot the Coaching zone. Cross-check:
- The strengths/weaknesses column contents match the top 2 strength / top 2 weakness-or-mixed findings from Step 3's `career-findings` output (by title, in the same order).
- The ranked focus-area list matches those same weaknesses, sorted by severity (high → low), with the correct link label/target per finding title (or no link, for any title not in `FINDING_DEST`).
- The CTA label matches Step 3's `cached` value (`"View your coaching plan →"` if `true`, `"Get your coaching plan →"` if `false`).
- Zero new console errors (only the pre-existing favicon 404 and React Router future-flag warnings every prior slice has noted).

- [ ] **Step 5: Record findings**

If everything matches: no code changes needed, this task is done. If live-verification surfaces a real bug: fix it, re-run the full test suites (`python3 -m pytest tests/integration/test_api_overview.py -v` and `cd frontend && npm test && npm run typecheck`), re-verify, then commit the fix with a message describing the specific bug found (matching this project's established pattern for e.g. the `react-plotly.js` ESM bug found during the Evolution-zone slice).
