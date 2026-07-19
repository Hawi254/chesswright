# Overview Evolution Zone — "Rating & accuracy over time" (Design Spec)

**Date:** 2026-07-12
**Status:** approved, ready for implementation planning.

## Context

The identity-zone slice (`docs/superpowers/specs/2026-07-12-overview-identity-zone-port-design.md`)
deliberately deferred the Evolution zone, flagging that it "pulls in a
charting-library decision not needed here." Per
`docs/scoping/frontend-rewrite-development-path-2026-07-12.md`'s latest
entry, "finish Overview" turned out to be five independent pieces with
different dependency profiles; the milestones/achievements chip row was
already shipped as the cheapest of the five
(`docs/superpowers/specs/2026-07-12-overview-milestones-row-design.md`).
This slice is the next piece: the Evolution zone's charts.

The old Streamlit Evolution zone (`dashboard/overview_view.py`,
`_render_evolution_zone`) actually bundles four things: (1) rating/ACPL
line charts, (2) milestones chips (already ported), (3) a "recent form"
ticker (last 5 games), (4) a "career highlight" box linking to Game
Detail. Confirmed directly by reading the function: milestones is
already done, and career highlight needs a Game Detail route that
doesn't exist anywhere in the new frontend's `App.tsx`/`STATIC_CANDIDATES`
— out of scope regardless.

**Decided with the user (2026-07-12):** this slice ports only piece (1),
"Rating & accuracy over time" — the two line charts and their coverage
caveat. The "recent form" ticker is left for its own follow-on slice,
same reasoning as career highlight: keep each slice to one
self-contained piece rather than bundling unrelated pieces because they
happen to sit in the same old Streamlit function.

## Charting library: react-plotly.js

Decided directly by the user, no bake-off: reuse `react-plotly.js` +
`plotly.js`. This is a deliberate difference from the Phase 1 frontend
stack bake-off's own precedent (that one *did* do a comparative
research pass) — the user chose to skip comparison here and go straight
to the library that preserves the most continuity with the existing
Python-side Plotly config (`dashboard/charts.py`), rather than treating
this as equally open. Not re-litigated by this spec.

## Backend: one new endpoint

Same thin-wrapper style as every other Overview endpoint in
`api/main.py` — no changes to `dashboard/data/*.py`.

- **`GET /api/overview/acpl-trajectory`** — wraps
  `data.get_acpl_trajectory(duck_conn)` as-is, returns
  `df.to_dict(orient="records")` (identical shape/pattern to the
  existing `rating-trajectory` endpoint below).

`GET /api/overview/rating-trajectory` already exists (added during the
identity-zone slice for the narrative endpoint's internal `top_game`/
`rating_df` computation) but has never been consumed by the frontend
until now — no changes needed, this slice is simply its first real
consumer.

**No caching.** Checked directly: `get_acpl_trajectory` is a single
`moves` JOIN `games` GROUP BY query, not the multi-query fan-out that
justified the `narrative`/`career-findings` TTL cache in the
identity-zone slice. `get_rating_trajectory` is even simpler (no join).
Neither has an evidenced cost problem.

## Frontend

**New dependencies:** `plotly.js`, `react-plotly.js`, added to
`frontend/package.json`.

**`useEvolutionData()`** (`frontend/src/hooks/useEvolutionData.ts`) — an
independent hook, mirroring `useMilestones`'s shape rather than being
folded into `useOverviewData`. Fires `rating-trajectory` and
`acpl-trajectory` in parallel:

```ts
interface EvolutionData {
  ratingTrajectory: RatingPoint[] | null
  acplTrajectory: AcplPoint[] | null
  loading: boolean
  error: boolean
}
```

On error, the hook's consumer renders nothing (same as
`useMilestones`/`MilestonesRow`'s empty-and-error-both-collapse
pattern) rather than surfacing a page-level error — this zone has no
data dependency on the identity zone and a failure here shouldn't block
or blank the rest of Overview.

**`frontend/src/lib/charts.ts`** — a small `lineChart(data, x, y, color,
opts)` helper that builds a Plotly `{ data, layout }` pair, mirroring
`dashboard/charts.py`'s `line_chart` builder: dark theme layout
(background/grid colors matching `theme.apply_plotly_theme`), a
hovertemplate with axis-labeled values, optional `hoverExtra` for a
per-point caveat string (used by the ACPL chart's coverage annotation).
Colors are literal hex constants matching
`frontend/src/index.css`'s `--color-accent-gold` (`#C19A4B`) and
`--color-negative` (`#B0584F`) — already identical to `theme.py`'s
`ACCENT_GOLD`/`NEGATIVE`, confirmed by direct comparison, not assumed.

**`EvolutionZone.tsx`** (`frontend/src/components/EvolutionZone.tsx`):
- Two `<Plot>` charts side by side (Tailwind `grid grid-cols-2 gap-4`,
  matching `OverviewPage`'s existing grid conventions): avg rating by
  year (gold), ACPL by year (negative/red tone).
- The ACPL chart's hover text includes the same
  `"{n_games} of {n_total_games} games ({coverage_pct}%)"` string built
  client-side from the endpoint's `n_games`/`n_total_games`/
  `coverage_pct` fields — same fields the Python version already
  computes and returns, no new backend computation.
- Coverage-skew warning caption: ported 1:1 from
  `_render_evolution_zone`'s Python logic — when `acplTrajectory.length
  >= 2`, find the min- and max-coverage_pct rows; if
  `max.coverage_pct >= 2 * Math.max(min.coverage_pct, 0.1)`, render
  `"Analysis coverage varies sharply by year — from {min}% in {year} to
  {max}% in {year}."` beneath the charts.
- Charts render even when both trajectories are empty arrays (0 rows) —
  Plotly renders an empty axes frame, matching the old page's behavior.
  This differs deliberately from `MilestonesRow`'s "hide entirely when
  empty" rule: an empty chart container isn't visually broken the way an
  empty chip row would be, so there's no reason to hide it.

**`OverviewPage.tsx`**: render `<EvolutionZone />` directly below the
existing `<MilestonesRow />`, matching the old page's zone order
(identity → evolution).

## Testing plan

- **Backend:** extend `tests/integration/test_api_overview.py` with one
  new test for `acpl-trajectory` (same `api_client` fixture pattern as
  the existing `rating-trajectory` test — response shape, empty-DB
  case).
- **Frontend:**
  - `useEvolutionData.test.ts` — mocked `fetch`, covering loading,
    success, and error states (same style as `useMilestones.test.ts`).
  - `charts.test.ts` — unit tests for `lineChart`'s output shape and,
    separately, the coverage-skew threshold function (pure logic, easy
    to test directly against the same boundary cases the Python
    docstring already reasons about).
  - `EvolutionZone.test.tsx` — mocked hook: both charts render from
    sample data, the coverage caption appears/doesn't appear at the
    right threshold, and the whole zone renders nothing on hook error.
- **Live verification:** Playwright against the real dev DB (32,295
  games, per `frontend_spike_worktree_real_chessdb_copy`), cross-checking
  rendered chart data against the current Streamlit Evolution zone's
  charts for the same DB — a correctness sanity check, not a
  pixel-diff. Also verify the empty-DB case (`config.yaml` pointed at a
  fresh/empty scratch DB, same discipline as the identity-zone slice's
  fresh-install verification) renders empty chart frames without
  crashing.

## Out of scope (deliberately deferred)

- Recent form ticker (last 5 games) — its own follow-on slice, no
  charting-library dependency, but a distinct enough UI piece (an HTML
  table, not a chart) to keep separate from this slice.
- Career highlight teaser — blocked on a Game Detail route not yet
  added to the new frontend's route table.
- Coaching zone (full findings list) — its own follow-on slice, reuses
  the `career-findings` payload the identity-zone slice already fetches.
- Achievements badges beyond the milestones chip row, live engine-status
  strip — unrelated to this zone.
