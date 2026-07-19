# Overview Evolution Zone Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port the "Rating & accuracy over time" piece of Streamlit's Overview Evolution zone (two line charts: avg rating by year, ACPL by year, plus a coverage-skew caption) to the React/FastAPI stack, using `react-plotly.js`.

**Architecture:** One new thin-wrapper FastAPI endpoint (`GET /api/overview/acpl-trajectory`), reusing the already-built-but-unconsumed `GET /api/overview/rating-trajectory`. A small chart-building library (`frontend/src/lib/charts.ts`) that mirrors `dashboard/charts.py`'s `line_chart` and the coverage-skew threshold logic as pure, independently-testable functions. An independent React hook (`useEvolutionData`), decoupled from `useOverviewData` (same reasoning as the existing `useMilestones`). A presentational `EvolutionZone` component (mirrors `MilestonesRow`'s prop-driven shape) rendering two `react-plotly.js` `<Plot>` charts. Wired into `OverviewPage` below the existing `MilestonesRow`.

**Tech Stack:** FastAPI, pytest + `TestClient` (backend, no new dependencies). React, Vitest + `@testing-library/react`, `react-plotly.js` + `plotly.js` (new frontend dependencies).

## Global Constraints

- Scope is charts only: `avg_rating`-by-year and `acpl`-by-year, plus the coverage-skew caption. Recent form and career highlight are explicitly out of scope (separate future slices) — do not add them in this plan.
- Charting library is `react-plotly.js` — decided directly by the user, no comparison/bake-off to redo.
- No caching on `acpl-trajectory` — a single JOIN/GROUP BY query, not the multi-query fan-out that justified the `narrative`/`career-findings` TTL cache.
- Chart colors come from the existing `frontend/src/lib/theme.ts` `THEME` object (`THEME.accentGold`, `THEME.negative`, `THEME.bg`, `THEME.bgSecondary`, `THEME.text`) — already verified to match `dashboard/theme.py` byte-for-byte (`frontend/src/lib/theme.test.ts`). Do not hardcode new hex values.
- Charts render even when the underlying array is empty (0 rows) — Plotly shows an empty axes frame. This differs deliberately from `MilestonesRow`'s "render nothing when empty" rule.
- The coverage-skew caption's threshold logic must match `dashboard/overview_view.py`'s Python 1:1: only shown when there are ≥2 ACPL-trajectory rows, and only when `max(coverage_pct) >= 2 * max(min(coverage_pct), 0.1)`. Ties break to the first occurrence in array order (matches pandas `idxmin`/`idxmax`).
- Spec: `docs/superpowers/specs/2026-07-12-overview-evolution-zone-design.md`.

---

## Task 1: Backend — `/api/overview/acpl-trajectory` endpoint

**Files:**
- Modify: `api/main.py`
- Modify: `tests/integration/test_api_overview.py`

**Interfaces:**
- Consumes: `data.get_acpl_trajectory(duck_conn) -> pd.DataFrame` (existing, `dashboard/data/overview.py:15`, columns `year, acpl, n_games, n_total_games, coverage_pct`), `get_db_connections() -> (sqlite_conn, duck_conn)` (existing, `api/db.py`).
- Produces: `GET /api/overview/acpl-trajectory` → `200 [{"year": int, "acpl": float, "n_games": int, "n_total_games": int, "coverage_pct": float}, ...]`.

- [ ] **Step 1: Write the failing test**

In `tests/integration/test_api_overview.py`, insert this test immediately after `test_rating_trajectory_endpoint` and before `test_rating_snapshot_endpoint`:

```python
@pytest.mark.integration
def test_acpl_trajectory_endpoint(api_client):
    resp = api_client.get("/api/overview/acpl-trajectory")
    assert resp.status_code == 200
    assert resp.json() == []  # empty migrated DB has no analyzed games
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m pytest tests/integration/test_api_overview.py -k acpl_trajectory -v`
Expected: FAIL with `404` (route does not exist yet).

- [ ] **Step 3: Add the endpoint**

In `api/main.py`, add the endpoint immediately after `rating_trajectory` and before `rating_snapshot` (keeps the two trajectory endpoints adjacent, matching the file's existing top-to-bottom grouping):

```python
@app.get("/api/overview/rating-trajectory")
def rating_trajectory():
    _, duck_conn = get_db_connections()
    df = data.get_rating_trajectory(duck_conn)
    return df.to_dict(orient="records")


@app.get("/api/overview/acpl-trajectory")
def acpl_trajectory():
    _, duck_conn = get_db_connections()
    df = data.get_acpl_trajectory(duck_conn)
    return df.to_dict(orient="records")


@app.get("/api/overview/rating-snapshot")
def rating_snapshot():
    _, duck_conn = get_db_connections()
    return data.get_rating_snapshot(duck_conn)
```

- [ ] **Step 4: Run the full backend test file to verify it passes**

Run: `python3 -m pytest tests/integration/test_api_overview.py -v`
Expected: 13/13 PASS (12 existing + 1 new).

- [ ] **Step 5: Commit**

```bash
git add api/main.py tests/integration/test_api_overview.py
git commit -m "Add GET /api/overview/acpl-trajectory endpoint"
```

---

## Task 2: Frontend — `lib/charts.ts` chart-building helpers

**Files:**
- Create: `frontend/src/lib/charts.ts`
- Test: `frontend/src/lib/charts.test.ts`

**Interfaces:**
- Consumes: `THEME` from `./theme` (existing, `frontend/src/lib/theme.ts`).
- Produces: `lineChart(rows, x, y, color, options?) -> { data: Partial<PlotData>[], layout: Partial<Layout> }`, `LineChartOptions` interface (`height?`, `xTitle?`, `yTitle?`, `hoverExtra?: { column, label }`), `coverageWarning(rows: AcplTrajectoryPoint[]) -> string | null`, `AcplTrajectoryPoint` interface (`year, acpl, n_games, n_total_games, coverage_pct`) — all consumed by Task 4 (`EvolutionZone`).

- [ ] **Step 1: Install `plotly.js` and its types**

```bash
cd frontend && npm install plotly.js && npm install --save-dev @types/plotly.js
```

- [ ] **Step 2: Write the failing tests**

Create `frontend/src/lib/charts.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import { coverageWarning, lineChart } from './charts'

describe('lineChart', () => {
  const rows = [
    { year: 2024, avg_rating: 1400 },
    { year: 2025, avg_rating: 1500 },
  ]

  it('builds one scatter trace from the given x/y columns', () => {
    const { data } = lineChart(rows, 'year', 'avg_rating', '#C19A4B')
    expect(data).toHaveLength(1)
    expect(data[0].x).toEqual([2024, 2025])
    expect(data[0].y).toEqual([1400, 1500])
    expect(data[0].type).toBe('scatter')
    expect(data[0].mode).toBe('lines+markers')
    expect(data[0].line).toEqual({ color: '#C19A4B', width: 2 })
  })

  it('title-cases axis titles by default', () => {
    const { layout } = lineChart(rows, 'year', 'avg_rating', '#C19A4B')
    expect(layout.xaxis?.title).toEqual({ text: 'Year' })
    expect(layout.yaxis?.title).toEqual({ text: 'Avg Rating' })
  })

  it('uses explicit axis titles when given', () => {
    const { layout } = lineChart(rows, 'year', 'avg_rating', '#C19A4B', {
      xTitle: 'Year',
      yTitle: 'Average rating',
    })
    expect(layout.xaxis?.title).toEqual({ text: 'Year' })
    expect(layout.yaxis?.title).toEqual({ text: 'Average rating' })
  })

  it('appends a hoverExtra column to the hovertemplate and customdata', () => {
    const coverageRows = [{ year: 2024, acpl: 40, hover_coverage: '5 of 10 games (50.0%)' }]
    const { data } = lineChart(coverageRows, 'year', 'acpl', '#B0584F', {
      hoverExtra: { column: 'hover_coverage', label: 'Analyzed' },
    })
    expect(data[0].customdata).toEqual(['5 of 10 games (50.0%)'])
    expect(data[0].hovertemplate).toContain('Analyzed: %{customdata}')
  })

  it('applies the dark theme colors to the layout', () => {
    const { layout } = lineChart(rows, 'year', 'avg_rating', '#C19A4B')
    expect(layout.paper_bgcolor).toBe('#14181F')
    expect(layout.plot_bgcolor).toBe('#1E2530')
    expect(layout.font).toEqual({ color: '#E8E6E1', size: 13 })
  })
})

describe('coverageWarning', () => {
  it('returns null with fewer than 2 rows', () => {
    expect(coverageWarning([])).toBeNull()
    expect(
      coverageWarning([{ year: 2024, acpl: 40, n_games: 5, n_total_games: 10, coverage_pct: 50 }]),
    ).toBeNull()
  })

  it('returns null when coverage does not vary sharply', () => {
    const rows = [
      { year: 2024, acpl: 40, n_games: 5, n_total_games: 10, coverage_pct: 50 },
      { year: 2025, acpl: 42, n_games: 6, n_total_games: 10, coverage_pct: 60 },
    ]
    expect(coverageWarning(rows)).toBeNull()
  })

  it('warns when the max coverage is at least double the min (floor 0.1)', () => {
    const rows = [
      { year: 2024, acpl: 40, n_games: 1, n_total_games: 100, coverage_pct: 1 },
      { year: 2025, acpl: 42, n_games: 50, n_total_games: 100, coverage_pct: 50 },
    ]
    expect(coverageWarning(rows)).toBe(
      '⚠️ Analysis coverage varies sharply by year — from 1.0% in 2024 to 50.0% in 2025.',
    )
  })

  it('uses the first occurrence on a coverage_pct tie, matching pandas idxmin/idxmax', () => {
    const rows = [
      { year: 2024, acpl: 40, n_games: 1, n_total_games: 100, coverage_pct: 10 },
      { year: 2025, acpl: 41, n_games: 1, n_total_games: 10, coverage_pct: 10 },
      { year: 2026, acpl: 42, n_games: 50, n_total_games: 100, coverage_pct: 50 },
    ]
    expect(coverageWarning(rows)).toContain('10.0% in 2024')
  })
})
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd frontend && npx vitest run src/lib/charts.test.ts`
Expected: FAIL — `charts.ts` does not exist yet (module not found).

- [ ] **Step 4: Write the implementation**

Create `frontend/src/lib/charts.ts`:

```ts
import type { Layout, PlotData } from 'plotly.js'
import { THEME } from './theme'

function titleCase(column: string): string {
  return column
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

function rgba(hex: string, alpha: number): string {
  const clean = hex.replace('#', '')
  const r = parseInt(clean.slice(0, 2), 16)
  const g = parseInt(clean.slice(2, 4), 16)
  const b = parseInt(clean.slice(4, 6), 16)
  return `rgba(${r},${g},${b},${alpha})`
}

export interface LineChartOptions<T> {
  height?: number
  xTitle?: string
  yTitle?: string
  hoverExtra?: { column: keyof T & string; label: string }
}

// Generic (not Record<string, ...>) deliberately: plain interfaces like
// RatingPoint/AcplPoint have no index signature, so TS's direct
// assignability check against Record<string, X> rejects them at call
// sites (a real "Index signature is missing" compile error, confirmed
// while drafting this plan) -- keyof T sidesteps that entirely and also
// gets column-name typos caught at compile time.
export function lineChart<T>(
  rows: T[],
  x: keyof T & string,
  y: keyof T & string,
  color: string,
  options: LineChartOptions<T> = {},
): { data: Partial<PlotData>[]; layout: Partial<Layout> } {
  const height = options.height ?? 320
  const xTitle = options.xTitle ?? titleCase(x)
  const yTitle = options.yTitle ?? titleCase(y)

  let hovertemplate = `%{x}<br>${yTitle}: %{y:.2f}`
  let customdata: Array<string | number> | undefined
  if (options.hoverExtra) {
    const { column, label } = options.hoverExtra
    customdata = rows.map((row) => row[column] as unknown as string | number)
    hovertemplate += `<br>${label}: %{customdata}`
  }

  const trace = {
    x: rows.map((row) => row[x] as unknown as number),
    y: rows.map((row) => row[y] as unknown as number),
    type: 'scatter',
    mode: 'lines+markers',
    line: { color, width: 2 },
    marker: { size: 5 },
    customdata,
    hovertemplate: hovertemplate + '<extra></extra>',
  } as Partial<PlotData>

  const axisTheme = {
    gridcolor: rgba(THEME.text, 0.1),
    linecolor: rgba(THEME.text, 0.33),
    tickfont: { color: THEME.text },
    automargin: true,
  }

  const layout: Partial<Layout> = {
    title: { text: '' },
    height,
    paper_bgcolor: THEME.bg,
    plot_bgcolor: THEME.bgSecondary,
    font: { color: THEME.text, size: 13 },
    margin: { l: 40, r: 20, t: 40, b: 40 },
    xaxis: { title: { text: xTitle }, ...axisTheme },
    yaxis: { title: { text: yTitle }, ...axisTheme },
    hoverlabel: { bgcolor: THEME.bgSecondary, font: { color: THEME.text } },
  }

  return { data: [trace], layout }
}

export interface AcplTrajectoryPoint {
  year: number
  acpl: number
  n_games: number
  n_total_games: number
  coverage_pct: number
}

export function coverageWarning(rows: AcplTrajectoryPoint[]): string | null {
  if (rows.length < 2) return null
  const minRow = rows.reduce((a, b) => (a.coverage_pct <= b.coverage_pct ? a : b))
  const maxRow = rows.reduce((a, b) => (a.coverage_pct >= b.coverage_pct ? a : b))
  if (maxRow.coverage_pct >= 2 * Math.max(minRow.coverage_pct, 0.1)) {
    return (
      `⚠️ Analysis coverage varies sharply by year — from ` +
      `${minRow.coverage_pct.toFixed(1)}% in ${minRow.year} to ` +
      `${maxRow.coverage_pct.toFixed(1)}% in ${maxRow.year}.`
    )
  }
  return null
}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run src/lib/charts.test.ts`
Expected: 9/9 PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/lib/charts.ts frontend/src/lib/charts.test.ts
git commit -m "Add lib/charts.ts line-chart and coverage-warning helpers"
```

---

## Task 3: Frontend — `useEvolutionData` hook

**Files:**
- Create: `frontend/src/hooks/useEvolutionData.ts`
- Test: `frontend/src/hooks/useEvolutionData.test.ts`

**Interfaces:**
- Consumes: `GET http://127.0.0.1:8123/api/overview/rating-trajectory` (existing), `GET http://127.0.0.1:8123/api/overview/acpl-trajectory` (Task 1).
- Produces: `useEvolutionData(): { ratingTrajectory: RatingPoint[] | null, acplTrajectory: AcplPoint[] | null, loading: boolean, error: boolean }`, exported `RatingPoint` (`year, avg_rating, n_games`) and `AcplPoint` (`year, acpl, n_games, n_total_games, coverage_pct`) interfaces — consumed by Task 4 (`EvolutionZone`) and Task 5 (`OverviewPage`).

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/hooks/useEvolutionData.test.ts`:

```ts
import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useEvolutionData } from './useEvolutionData'

const SAMPLE_RATING_TRAJECTORY = [
  { year: 2024, avg_rating: 1400, n_games: 50 },
  { year: 2025, avg_rating: 1500, n_games: 60 },
]
const SAMPLE_ACPL_TRAJECTORY = [
  { year: 2024, acpl: 45.2, n_games: 20, n_total_games: 50, coverage_pct: 40.0 },
]

const RESPONSES: Record<string, unknown> = {
  '/api/overview/rating-trajectory': SAMPLE_RATING_TRAJECTORY,
  '/api/overview/acpl-trajectory': SAMPLE_ACPL_TRAJECTORY,
}

function mockFetchSuccess() {
  return vi.fn((url: string) => {
    const path = new URL(url).pathname
    return Promise.resolve({ ok: true, json: async () => RESPONSES[path] })
  })
}

describe('useEvolutionData', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('starts in a loading state with no error', async () => {
    vi.stubGlobal('fetch', mockFetchSuccess())
    const { result } = renderHook(() => useEvolutionData())
    expect(result.current.loading).toBe(true)
    expect(result.current.error).toBe(false)

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })
  })

  it('populates both trajectories when every request succeeds', async () => {
    vi.stubGlobal('fetch', mockFetchSuccess())
    const { result } = renderHook(() => useEvolutionData())

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })
    expect(result.current.error).toBe(false)
    expect(result.current.ratingTrajectory).toEqual(SAMPLE_RATING_TRAJECTORY)
    expect(result.current.acplTrajectory).toEqual(SAMPLE_ACPL_TRAJECTORY)
  })

  it('reports an error state if a request fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network error')))
    const { result } = renderHook(() => useEvolutionData())

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })
    expect(result.current.error).toBe(true)
    expect(result.current.ratingTrajectory).toBeNull()
    expect(result.current.acplTrajectory).toBeNull()
  })

  it('reports an error state on a non-ok response', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: false, status: 500 })))
    const { result } = renderHook(() => useEvolutionData())

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })
    expect(result.current.error).toBe(true)
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx vitest run src/hooks/useEvolutionData.test.ts`
Expected: FAIL — `useEvolutionData.ts` does not exist yet (module not found).

- [ ] **Step 3: Write the implementation**

Create `frontend/src/hooks/useEvolutionData.ts`:

```ts
import { useEffect, useState } from 'react'

const API_BASE = 'http://127.0.0.1:8123'

export interface RatingPoint {
  year: number
  avg_rating: number
  n_games: number
}

export interface AcplPoint {
  year: number
  acpl: number
  n_games: number
  n_total_games: number
  coverage_pct: number
}

export interface EvolutionData {
  ratingTrajectory: RatingPoint[] | null
  acplTrajectory: AcplPoint[] | null
  loading: boolean
  error: boolean
}

async function fetchJson<T>(path: string): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`)
  if (!r.ok) throw new Error(`status ${r.status}`)
  return r.json() as Promise<T>
}

const EMPTY_STATE: EvolutionData = {
  ratingTrajectory: null,
  acplTrajectory: null,
  loading: true,
  error: false,
}

export function useEvolutionData(): EvolutionData {
  const [state, setState] = useState<EvolutionData>(EMPTY_STATE)

  useEffect(() => {
    let cancelled = false

    Promise.all([
      fetchJson<RatingPoint[]>('/api/overview/rating-trajectory'),
      fetchJson<AcplPoint[]>('/api/overview/acpl-trajectory'),
    ])
      .then(([ratingTrajectory, acplTrajectory]) => {
        if (!cancelled) {
          setState({ ratingTrajectory, acplTrajectory, loading: false, error: false })
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

Run: `cd frontend && npx vitest run src/hooks/useEvolutionData.test.ts`
Expected: 4/4 PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/hooks/useEvolutionData.ts frontend/src/hooks/useEvolutionData.test.ts
git commit -m "Add useEvolutionData hook for the Overview Evolution zone"
```

---

## Task 4: Frontend — `EvolutionZone` component

**Files:**
- Create: `frontend/src/components/EvolutionZone.tsx`
- Test: `frontend/src/components/EvolutionZone.test.tsx`

**Interfaces:**
- Consumes: `RatingPoint`, `AcplPoint` types from `../hooks/useEvolutionData` (Task 3); `lineChart`, `coverageWarning` from `../lib/charts` (Task 2); `THEME` from `../lib/theme`; `Plot` default export from `react-plotly.js`.
- Produces: `export default function EvolutionZone({ ratingTrajectory, acplTrajectory }: { ratingTrajectory: RatingPoint[], acplTrajectory: AcplPoint[] })` — consumed by Task 5 (`OverviewPage`). Always renders (no internal empty-check) — the caller decides whether to render it at all, same convention as `MilestonesRow`.

- [ ] **Step 1: Install `react-plotly.js` and its types**

```bash
cd frontend && npm install react-plotly.js && npm install --save-dev @types/react-plotly.js
```

- [ ] **Step 2: Write the failing tests**

Create `frontend/src/components/EvolutionZone.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import EvolutionZone from './EvolutionZone'

// vi.hoisted + vi.mock are both hoisted above these imports by vitest's
// transform, so EvolutionZone's own `import Plot from 'react-plotly.js'`
// resolves to this mock -- avoids rendering real Plotly (canvas/WebGL,
// ResizeObserver-driven layout) inside jsdom.
const { plotMock } = vi.hoisted(() => ({ plotMock: vi.fn() }))

vi.mock('react-plotly.js', () => ({
  default: (props: unknown) => {
    plotMock(props)
    return <div data-testid="plot" />
  },
}))

const RATING_TRAJECTORY = [
  { year: 2024, avg_rating: 1400, n_games: 50 },
  { year: 2025, avg_rating: 1500, n_games: 60 },
]

describe('EvolutionZone', () => {
  it('renders the zone heading and two Plot charts', () => {
    render(
      <EvolutionZone
        ratingTrajectory={RATING_TRAJECTORY}
        acplTrajectory={[
          { year: 2024, acpl: 40, n_games: 5, n_total_games: 10, coverage_pct: 50 },
          { year: 2025, acpl: 42, n_games: 6, n_total_games: 10, coverage_pct: 60 },
        ]}
      />,
    )

    expect(screen.getByText('Rating & accuracy over time')).toBeInTheDocument()
    expect(plotMock).toHaveBeenCalledTimes(2)
  })

  it('passes the rating trajectory data to the first chart in gold', () => {
    render(<EvolutionZone ratingTrajectory={RATING_TRAJECTORY} acplTrajectory={[]} />)

    const [ratingCall] = plotMock.mock.calls.map((c) => c[0])
    expect(ratingCall.data[0].y).toEqual([1400, 1500])
    expect(ratingCall.data[0].line.color).toBe('#C19A4B')
  })

  it('shows the coverage warning caption when coverage varies sharply', () => {
    render(
      <EvolutionZone
        ratingTrajectory={[]}
        acplTrajectory={[
          { year: 2024, acpl: 40, n_games: 1, n_total_games: 100, coverage_pct: 1 },
          { year: 2025, acpl: 42, n_games: 50, n_total_games: 100, coverage_pct: 50 },
        ]}
      />,
    )

    expect(screen.getByText(/Analysis coverage varies sharply/)).toBeInTheDocument()
  })

  it('does not show the coverage warning caption when coverage is even', () => {
    render(
      <EvolutionZone
        ratingTrajectory={[]}
        acplTrajectory={[
          { year: 2024, acpl: 40, n_games: 5, n_total_games: 10, coverage_pct: 50 },
          { year: 2025, acpl: 42, n_games: 6, n_total_games: 10, coverage_pct: 60 },
        ]}
      />,
    )

    expect(screen.queryByText(/Analysis coverage varies sharply/)).not.toBeInTheDocument()
  })
})
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd frontend && npx vitest run src/components/EvolutionZone.test.tsx`
Expected: FAIL — `EvolutionZone.tsx` does not exist yet (module not found).

- [ ] **Step 4: Write the implementation**

Create `frontend/src/components/EvolutionZone.tsx`:

```tsx
import Plot from 'react-plotly.js'
import type { AcplPoint, RatingPoint } from '../hooks/useEvolutionData'
import { coverageWarning, lineChart } from '../lib/charts'
import { THEME } from '../lib/theme'

export default function EvolutionZone({
  ratingTrajectory,
  acplTrajectory,
}: {
  ratingTrajectory: RatingPoint[]
  acplTrajectory: AcplPoint[]
}) {
  const ratingChart = lineChart(ratingTrajectory, 'year', 'avg_rating', THEME.accentGold, {
    height: 200,
    xTitle: 'Year',
    yTitle: 'Average rating',
  })

  const acplRows = acplTrajectory.map((row) => ({
    ...row,
    hover_coverage: `${row.n_games} of ${row.n_total_games} games (${row.coverage_pct.toFixed(1)}%)`,
  }))
  const acplChart = lineChart(acplRows, 'year', 'acpl', THEME.negative, {
    height: 200,
    xTitle: 'Year',
    yTitle: 'ACPL',
    hoverExtra: { column: 'hover_coverage', label: 'Analyzed' },
  })

  const warning = coverageWarning(acplTrajectory)

  return (
    <div className="mt-6">
      <h2 className="text-xs uppercase tracking-wide text-text-muted">
        Rating &amp; accuracy over time
      </h2>
      <div className="mt-2 grid grid-cols-2 gap-4">
        <Plot
          data={ratingChart.data}
          layout={ratingChart.layout}
          config={{ displayModeBar: false }}
          style={{ width: '100%' }}
        />
        <Plot
          data={acplChart.data}
          layout={acplChart.layout}
          config={{ displayModeBar: false }}
          style={{ width: '100%' }}
        />
      </div>
      {warning && <p className="mt-2 text-xs text-text-muted">{warning}</p>}
    </div>
  )
}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run src/components/EvolutionZone.test.tsx`
Expected: 4/4 PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/components/EvolutionZone.tsx frontend/src/components/EvolutionZone.test.tsx
git commit -m "Add EvolutionZone component (rating/ACPL charts)"
```

---

## Task 5: Wire `EvolutionZone` into `OverviewPage`

**Files:**
- Modify: `frontend/src/pages/OverviewPage.tsx`
- Modify: `frontend/src/pages/OverviewPage.test.tsx`

**Interfaces:**
- Consumes: `useEvolutionData()` (Task 3), `EvolutionZone` (Task 4).

- [ ] **Step 1: Write the failing tests**

In `frontend/src/pages/OverviewPage.test.tsx`, add a `react-plotly.js` mock and a `useEvolutionData` mock alongside the existing ones, and set its default loading state in `beforeEach`:

```tsx
import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import OverviewPage from './OverviewPage'
import type { OverviewData } from '../hooks/useOverviewData'

vi.mock('react-plotly.js', () => ({
  default: () => <div data-testid="plot" />,
}))

const mockUseOverviewData = vi.fn()
vi.mock('../hooks/useOverviewData', () => ({
  useOverviewData: () => mockUseOverviewData(),
}))

const mockUseMilestones = vi.fn()
vi.mock('../hooks/useMilestones', () => ({
  useMilestones: () => mockUseMilestones(),
}))

const mockUseEvolutionData = vi.fn()
vi.mock('../hooks/useEvolutionData', () => ({
  useEvolutionData: () => mockUseEvolutionData(),
}))

const EMPTY: OverviewData = {
  stats: null, ratingSnapshot: null, streak: null, findings: null, narrative: null,
  loading: false, error: false,
}

describe('OverviewPage', () => {
  beforeEach(() => {
    mockUseMilestones.mockReturnValue({ milestones: null, loading: true, error: false })
    mockUseEvolutionData.mockReturnValue({
      ratingTrajectory: null, acplTrajectory: null, loading: true, error: false,
    })
  })

  // ... existing tests unchanged ...

  it('renders the evolution zone independently of identity-zone loading/error state', () => {
    mockUseOverviewData.mockReturnValue({ ...EMPTY, loading: false, error: true })
    mockUseEvolutionData.mockReturnValue({
      ratingTrajectory: [{ year: 2024, avg_rating: 1400, n_games: 10 }],
      acplTrajectory: [{ year: 2024, acpl: 40, n_games: 5, n_total_games: 10, coverage_pct: 50 }],
      loading: false,
      error: false,
    })
    render(<OverviewPage />)

    expect(screen.getByText('Rating & accuracy over time')).toBeInTheDocument()
  })

  it('renders no evolution zone while its own fetch is still loading', () => {
    mockUseOverviewData.mockReturnValue({ ...EMPTY, loading: true })
    mockUseEvolutionData.mockReturnValue({
      ratingTrajectory: null, acplTrajectory: null, loading: true, error: false,
    })
    render(<OverviewPage />)

    expect(screen.queryByText('Rating & accuracy over time')).not.toBeInTheDocument()
  })
})
```

Apply the new `react-plotly.js`/`useEvolutionData` mocks, the `beforeEach` addition, and the two new `it` blocks to the real file without disturbing the existing eight `it` blocks — they stay exactly as they are today; only the imports, mocks, `beforeEach` body, and the two new tests are additions.

- [ ] **Step 2: Run the tests to verify the new ones fail**

Run: `cd frontend && npx vitest run src/pages/OverviewPage.test.tsx`
Expected: the 2 new tests FAIL (`EvolutionZone`/`useEvolutionData` not wired into `OverviewPage` yet); the 8 pre-existing tests still PASS.

- [ ] **Step 3: Wire the hook and component into `OverviewPage`**

In `frontend/src/pages/OverviewPage.tsx`, add imports:

```tsx
import EvolutionZone from '../components/EvolutionZone'
import MilestonesRow from '../components/MilestonesRow'
import { useEvolutionData } from '../hooks/useEvolutionData'
import { useMilestones } from '../hooks/useMilestones'
import { useOverviewData, type Finding } from '../hooks/useOverviewData'
```

Add the hook call inside the component body, right after the existing `useMilestones()` call:

```tsx
export default function OverviewPage() {
  const { stats, ratingSnapshot, streak, findings, narrative, loading, error } =
    useOverviewData()
  const { milestones } = useMilestones()
  const { ratingTrajectory, acplTrajectory } = useEvolutionData()
```

Add the zone itself as the last child of the outer `<div className="p-8">`, after the existing `{milestones && <MilestonesRow milestones={milestones} />}` line — rendered independently of `loading`/`error` from `useOverviewData`, since the Evolution zone has no dependency on identity-zone data:

```tsx
      {milestones && <MilestonesRow milestones={milestones} />}
      {ratingTrajectory && acplTrajectory && (
        <EvolutionZone ratingTrajectory={ratingTrajectory} acplTrajectory={acplTrajectory} />
      )}
    </div>
  )
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run src/pages/OverviewPage.test.tsx`
Expected: 10/10 PASS (8 existing + 2 new).

- [ ] **Step 5: Run the full frontend suite and typecheck**

Run: `cd frontend && npm test && npm run typecheck`
Expected: all tests PASS, typecheck reports no errors.

**Real bug found here, not anticipated by the plan:** `npm test` failed one
pre-existing suite, `src/App.test.tsx` — `Cannot find module
'.../node_modules/plotly.js/dist/plotly' imported from
'.../node_modules/react-plotly.js/dist/index.mjs'. Did you mean to import
"plotly.js/dist/plotly.js"?`. Root-caused via systematic-debugging:
`react-plotly.js@4.0.0`'s published ESM build (`dist/index.mjs`) does
`import Plotly from "plotly.js/dist/plotly"` with no file extension — legal
for CommonJS `require()` (which auto-appends `.js`, and which the package's
`dist/index.cjs` build uses instead) but illegal under strict ESM
resolution, which Vite/Vitest apply. This is a real defect in the upstream
package, not a mistake in this plan's code, and it would break the actual
packaged app too (Vite's dev server and production build both resolve ESM
first), not just tests.

**Fix, two parts:**
1. `frontend/vite.config.ts` — added a `resolve.alias` entry forcing
   `'react-plotly.js'` to resolve to its CJS build
   (`node_modules/react-plotly.js/dist/index.cjs`) instead of the broken
   ESM one. Vite bundles CJS dependencies transparently either way, so this
   has no behavioral effect beyond sidestepping the broken import.
2. `frontend/src/App.test.tsx` — after the alias fix, a second, distinct
   problem surfaced: this file is the only test that renders the real
   `OverviewPage` component tree without mocking `react-plotly.js`
   (`OverviewPage.test.tsx` and `EvolutionZone.test.tsx` both already mock
   it). `EvolutionZone`'s static `import Plot from 'react-plotly.js'`
   executes as soon as `OverviewPage.tsx` is imported — regardless of
   whether `useOverviewData`'s mocked "loading" state ever lets
   `EvolutionZone` actually render — so the real ~11MB `plotly.js` bundle
   loaded and touched canvas/WebGL/`URL.createObjectURL` APIs jsdom
   doesn't implement. Fixed by adding the same
   `vi.mock('react-plotly.js', ...)` stub already used in the other two
   test files.

Re-run `npm test && npm run typecheck` after both fixes: 15/15 test files,
53/53 tests PASS, typecheck clean.

**Deferred, not done here:** `plotly.js` (the full package) bundles every
trace type including WebGL (`scattergl`) and Mapbox support that this
slice's plain line charts never use — a real, evidenced bundle-size
optimization opportunity (`plotly.js-basic-dist` or
`plotly.js-cartesian-dist` would be far smaller) surfaced by this
investigation but out of scope for this bug fix. Worth raising in a future
Phase 3 performance pass (`docs/scoping/frontend-rewrite-development-path-2026-07-12.md`'s
own Phase 3 section already flags per-page code-splitting/bundle-size as
an open consideration) rather than acted on speculatively now.

- [ ] **Step 6: Commit**

```bash
git add frontend/vite.config.ts frontend/src/App.test.tsx frontend/src/pages/OverviewPage.tsx frontend/src/pages/OverviewPage.test.tsx docs/superpowers/plans/2026-07-12-overview-evolution-zone.md
git commit -m "Render EvolutionZone on OverviewPage"
```

---

## Task 6: Live verification and roadmap update

**⚠️ Run this task directly yourself — do not dispatch it to a subagent.** Per this
project's standing directive (`orchestrator_runs_tests_not_subagents` memory), a
subagent launching its own dev servers can hang waiting on a notification channel
that isn't its own. This task also requires the Playwright MCP browser tools.

**Files:**
- Modify: `docs/scoping/frontend-rewrite-development-path-2026-07-12.md`

- [ ] **Step 1: Run the full backend test suite once more**

Run: `python3 -m pytest tests/integration/test_api_overview.py -v`
Expected: 13/13 PASS.

- [ ] **Step 2: Start the backend dev server**

```bash
python3 -m uvicorn api.main:app --host 127.0.0.1 --port 8123 &
```

Confirm it's serving and capture the real values for comparison in Step 4:

```bash
curl -s http://127.0.0.1:8123/api/overview/rating-trajectory
curl -s http://127.0.0.1:8123/api/overview/acpl-trajectory
```

Expected: two `200` responses — non-empty lists against the real 32,295-game dev DB.

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

1. Navigate to `/overview`. Confirm the page renders (not stuck on "Loading…") and
   that the existing identity zone and milestones row still render correctly
   (unaffected by this slice).
2. Confirm a "Rating & accuracy over time" section renders below the milestones
   row, with two visible charts (Plotly canvases/SVGs).
3. Cross-check the chart data against the `curl` responses captured in Step 2 —
   use `mcp__plugin_playwright_playwright__browser_evaluate` to read the rendered
   Plotly figures' `data[0].x`/`data[0].y` arrays from the DOM (Plotly stores the
   figure on the plot `<div>`'s `.data` property) and diff them against the raw
   API JSON — they must match exactly.
4. Cross-check the same two charts against what the current Streamlit Overview
   page shows in its own "Rating & accuracy over time" panel for the same DB — a
   correctness sanity check, not a pixel-diff.
5. If the real dev DB's ACPL-by-year coverage varies sharply between years (check
   the Step 2 `curl` output directly), confirm the coverage warning caption
   renders with matching min/max percentages and years; otherwise confirm it does
   not render.
6. Take a screenshot for a visual sanity check (readable, not broken layout, dark
   theme applied to both charts — not Plotly's default light template).
7. Check console messages
   (`mcp__plugin_playwright_playwright__browser_console_messages`). Confirm zero
   errors.
8. Stop the frontend dev server, kill the `uvicorn` process, confirm no orphaned
   processes remain (`ps aux | grep -E "vite|uvicorn"`).

If any check fails, fix the relevant frontend/backend code from the task that owns
it, re-run that task's automated tests, then repeat this Step 4 from the top.

- [ ] **Step 5: Update the roadmap doc**

In `docs/scoping/frontend-rewrite-development-path-2026-07-12.md`, after the
existing "Open question resolved (2026-07-12): picked (a), finish this page..."
paragraph at the end of the file, add a new dated paragraph in the same style,
summarizing: the new `/api/overview/acpl-trajectory` endpoint (no caching, thin
wrapper) and the now-consumed `rating-trajectory` endpoint; the `react-plotly.js`
choice (user-decided, no bake-off); the `lib/charts.ts` helpers ported 1:1 from
`dashboard/charts.py`'s `line_chart` and the coverage-skew threshold logic; the
`useEvolutionData` + `EvolutionZone` frontend pieces (independent hook, charts
render even on 0 rows unlike milestones' empty-collapse rule); and the concrete
live-verified result observed in Step 4 (the real rating/ACPL chart values and
whether the coverage warning fired). Note explicitly that recent form, career
highlight, the Coaching zone, and the engine-status strip remain deferred to
their own follow-on slices.

- [ ] **Step 6: Commit the roadmap update**

```bash
git add docs/scoping/frontend-rewrite-development-path-2026-07-12.md
git commit -m "Update roadmap doc: Overview Evolution-zone charts slice done"
```
