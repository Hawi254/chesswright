# Batch Impact — Design

Status: approved by user (design sections), pending spec review
Branch: worktree-frontend-spike

## Context

`docs/frontend_migration_status.md` lists `batch_impact_view.py` ("Batch
Impact") as ⛔ not started. Per explicit user direction, this is a
**fresh design**, not a port of the Streamlit page's layout — the
Streamlit source (`dashboard/batch_impact_view.py`,
`dashboard/data/analysis_batches.py`) was read for requirements and
data-layer understanding only, per the standing "Streamlit is reference
not blueprint" directive.

The Streamlit page's data model compares one selected `analysis_runs`
row against *all cumulative history up to it* (before = every prior
batch, after = that batch + everything before it). Per this session's
brainstorm, the fresh design switches to a genuine **two-endpoint diff**:
pick any two batches (Run A, Run B) and see what changed between those
two checkpoints specifically — closer to a git-diff/CI-impact-report
mental model than a single-run "what did this batch add" digest. The
old model is a special case of the new one (From = "Start", To = the
run in question), so nothing the Streamlit page could show is lost.

This also activates a currently-inert link: `AnalysisJobsPage`'s
`BatchFinishedCard` has a disabled "See what changed →" affordance,
disabled specifically because this page didn't exist yet (see the
2026-07-15 Analysis Jobs design spec, decision 6). Wiring it up is part
of this work.

## Research

Web research (2026-07-16) on visualization patterns for paired
before/after category comparisons:

- **Slope charts** emphasize *direction of change* and rank shifts
  across two or more points — the right tool when the path/rank matters
  more than the absolute values, and best under ~15 categories.
- **Dumbbell (lollipop) charts** emphasize *gap magnitude* between
  exactly two values per category, while still showing both absolute
  values explicitly — the standard pattern for "before vs. after,"
  "actual vs. target" comparisons, and the pattern code-coverage diff
  tools (Codecov, GitLab MR coverage annotations) converge on for
  baseline-vs-current category breakdowns. Documented as working well
  for 5–30 categories sorted by gap size.
- The app's existing `differenceBarChart` primitive was considered and
  rejected for this use: it only plots the *delta*, discarding the
  actual before/after numbers — a regression from the current page's
  tables, which show precise values, not just direction.
- No chess-specific prior art exists for this page (as with the Points
  page before it) — neither Lichess nor chess.com expose a
  batch-analysis-impact view at all.

**Verdict**: dumbbell charts for phase accuracy, endgame accuracy, and
motif frequency — replacing four visually-disconnected before→after
text tables with one consistent visual idiom. Slope charts were the
runner-up but fit a "rank across many checkpoints" story this page
doesn't need to tell (that's the cumulative trend chart's job, kept
separately, as a line chart).

## Goals

- Answer "what changed between two analysis batches," not just "what
  did the latest batch add" — genuinely more capable than the Streamlit
  page, not just a reskin.
- Replace four disconnected before→after tables with one visual
  language (dumbbell charts) reused across every section.
- Give the cumulative trend chart a real interactive job (endpoint
  picker) instead of being a passive chart at the bottom of the page.
- Activate `BatchFinishedCard`'s dangling link.
- Reuse `dashboard/data/analysis_batches.py`'s existing query logic and
  boundary-correctness reasoning (its docstring's AUTOINCREMENT
  chronological-ordering argument) — extend it with range-parameterized
  siblings, don't reinvent it.

## Page structure

Top to bottom:

1. Title + one-line explainer.
2. **Endpoint picker**: two selects, "From" / "To", populated from
   `list_analysis_runs` (most-recent-first in the dropdown, as today).
   "From" additionally offers a synthetic **"Start (no history)"**
   option (`run_a = null`), subsuming the Streamlit page's "first-ever
   batch" case. Default: From = second-most-recent annotated run (or
   "Start" if only one exists), To = most-recent. If picked in reverse
   order, silently normalized (swap), no error shown. If From == To,
   fetching is blocked client-side with an inline "Pick two different
   batches to see a diff" hint rather than showing a degenerate
   all-zero page. Lifetime counter caption (total batches / total games
   analyzed, unchanged content from today) sits beside the picker.
3. **Trend chart**: the same two-panel cumulative ACPL / blunder-rate
   line charts as today (kept as two separate charts, not one dual-axis
   chart — centipawns and percent aren't comparable on one axis, same
   reasoning the current page already uses). New role: clickable.
   Clicking a point sets the earlier endpoint, a second click sets the
   later endpoint, a third click restarts from the first — same
   `onClick`/`event.points[0].customdata` pattern already proven by
   `PointsSankey`'s click-to-filter. The dropdowns remain the source of
   truth (chart clicks just fill them in); the selected range is
   visually marked between the two chosen points.
4. **Headline delta row**: the same four figures as today (ACPL,
   blunder rate, blunders/brilliancies found, top motif), relabeled for
   a range: "Between Run #A and Run #B." Renders a `pendingAnnotation`
   info banner instead ("hasn't been through the annotation pass yet")
   when the To-run's moves aren't annotated — same real gap the
   Streamlit page's BRIEF §6u note already found, retargeted from "this
   run" to "the To run."
5. **Records set in this range**: generalizes the Streamlit page's
   single-run "🏆 personal record" callout into a short list — any run
   strictly after From and at-or-before To that was a personal-best
   ACPL or blunder-rate *at the time it happened* gets one line.
   Renders nothing if the range contains no records (same
   noise-avoidance rule as today: most ranges won't have one).
6. **Accuracy by game phase** / **Endgame accuracy**: each section gets
   two side-by-side dumbbell charts (ACPL, Blunder rate) — replacing
   today's text-arrow table columns. Categories sorted by |delta|
   descending, per the dumbbell-chart sizing research above.
7. **Tactical motifs missed**: one dumbbell chart, missed-count before
   vs. after per motif, top 10 sorted by |delta| descending (same cap
   as today).
8. **New blunders in this range** table: same columns
   (game/ply/san/cpl/motif) and row-click-to-`GameDetailPage` behavior
   as today's "new blunders this run," retitled for a range.

New chart primitive: `dumbbellChart()` in `frontend/src/lib/charts.ts`,
alongside the existing `sankeyChart`/`icicleChart`/`differenceBarChart`
— stays in Plotly, consistent with every other chart in the app.

## Backend (`dashboard/data/analysis_batches.py`)

New range-parameterized functions alongside the existing single-`run_id`
ones (left untouched — `batch_impact_view.py` still calls them, so the
Streamlit page keeps working unmodified even though nothing points at it
from the new frontend):

- `get_batch_range_delta(sqlite_conn, run_a: int | None, run_b: int)` —
  same four headline numbers as `get_batch_headline_delta`, boundary
  generalized: `before = analysis_run_id IS NULL OR analysis_run_id <=
  run_a` (skipped/empty when `run_a is None`, reproducing the "first
  batch" case), `after = analysis_run_id IS NULL OR analysis_run_id <=
  run_b`. "In-range" stats (new blunders/brilliancies, top motif) use
  `analysis_run_id > run_a AND analysis_run_id <= run_b` (just `<=
  run_b` when `run_a is None`).
- `get_phase_accuracy_batch_range_delta`, `get_endgame_type_batch_range_delta`,
  `get_motif_batch_range_delta` — same before/after generalization
  applied to each existing single-run query's SQL.
- `get_new_blunders_in_range(sqlite_conn, run_a, run_b)` — same shape as
  `get_new_blunders_this_run`, range-filtered.
- **No new function for "records in range."** The FastAPI endpoint
  calls the existing `get_batch_trend()` once and does a single linear
  scan tracking running-min ACPL/blunder-rate, flagging any row in
  `(run_a, run_b]` that improves on every row at-or-before it. Avoids N
  redundant `get_batch_trend`/`get_batch_record_flags` calls for a range
  spanning many batches.
- `list_analysis_runs`, `get_batch_counter`, `get_batch_trend` are
  reused unchanged — already history-wide, not single-run-scoped.

## API

One bundled endpoint, mirroring the "everything the filter touches, one
call" precedent from Points/Analysis Jobs:

```
GET /api/batch-impact/summary?run_a=<int, omitted for "Start">&run_b=<int>
```

Backend re-normalizes (swaps `run_a`/`run_b` if `run_a > run_b`) as a
defensive backstop to the frontend's own normalization — never a 400,
since there's always a well-defined answer once swapped.

Response shape:

```
{
  runs: [{ id, label, gamesAnalyzed, endedAt }],
  counter: { totalBatches, totalGamesAnalyzed },
  range: { runA: number | null, runB: number },
  pendingAnnotation: boolean,
  headline: {
    gamesInRange, acplBefore, acplAfter, blunderRateBefore, blunderRateAfter,
    newBlunders, newBrilliant, topMotif, topMotifCount
  } | null,   // null exactly when pendingAnnotation is true
  records: [{ runId, label, metric: 'acpl' | 'blunder_rate', value, priorBest }],
  trend: [{ runId, endedAt, gamesAnalyzed, cumulativeAcpl, cumulativeBlunderRate }],
  phase: [{ phase, acplBefore, acplAfter, blunderRateBefore, blunderRateAfter, nMovesInRange }],
  endgame: [{ endgameType, acplBefore, acplAfter, blunderRateBefore, blunderRateAfter, nMovesInRange }],
  motifs: [{ motif, before, after, delta }],
  newBlunders: [{ gameId, ply, san, cpl, motif }]
}
```

`trend` is the full history (unfiltered by the selected range — it's
the picker's own data source, same rows `get_batch_trend` already
returns), not range-scoped like every other field.

One hook, `useBatchImpact(runA, runB)` — one fetch per param change,
same pattern as `usePointsLedger`.

## Frontend

- **`BatchImpactPage.tsx`** — composes `useBatchImpact`, reads
  `runA`/`runB` from `useSearchParams` (falling back to the page's own
  defaults when absent), renders the sections above in order.
- **`EndpointPicker.tsx`** — the two selects (+ "Start" sentinel) and
  the 3-click chart-selection state machine; owns the "From == To"
  block and the reverse-order swap.
- Trend chart rendered inline in `BatchImpactPage` (or a small
  `BatchTrendChart.tsx` wrapper) with the click handler, reusing
  `lineChart()` plus the `onClick`/`customdata` pattern from
  `PointsSankey`.
- **`RangeHeadline.tsx`** — the 4-figure row + range label + the
  `pendingAnnotation` banner.
- **`RangeRecords.tsx`** — the record-list callout; renders nothing
  when `records` is empty.
- **`DumbbellSection.tsx`** — reusable: one instance-pair for phase
  (ACPL + blunder-rate dumbbells), one instance-pair for endgame, one
  single instance for motifs (count-only, different value shape but the
  same underlying `dumbbellChart()` primitive).
- **`NewBlundersInRangeTable.tsx`** — same click-to-`GameDetailPage`
  idiom as Points' costliest-games table.

**Routing** (`App.tsx`): `PAGE_COMPONENTS['batch-impact'] =
BatchImpactPage`; new hidden route `batch-impact/:gameId` reusing
`GameDetailPage`, matching the `points/:gameId` /
`matchups/:gameId` precedent.

**Activating the link**: `BatchFinishedCard`'s inert `<span>` becomes
`<Link to={`/batch-impact?runB=${runId}`}>`. No `runA` needed — when
this card is showing, `runId` is the most recent run, so the page's own
default From-resolution (previous annotated run, or "Start") already
produces exactly "what did this batch change" without a special case.

## Empty / error states

- Zero `analysis_runs` rows → today's "start one from Analysis Jobs"
  info banner, nothing else renders.
- To-run not yet annotated → `pendingAnnotation` banner in place of the
  headline (section 4); every other section below it still renders
  against whatever range data does exist, same "one thin section never
  blocks the others" rule used throughout this app.
- From == To → blocked before fetching (see Endpoint picker above).
- Each of phase / endgame / motifs shows its own "not enough data yet"
  caption independently if its slice is empty, matching today's
  per-section captions.
- Records list empty → section omitted entirely.

## Non-goals

- Any change to `dashboard/batch_impact_view.py` or the existing
  single-`run_id` functions in `analysis_batches.py` — both keep
  working as-is for whatever still calls them.
- A calendar-time comparison axis — that's Repertoire Evolution's
  territory, same boundary `analysis_batches.py`'s own module docstring
  already documents (endgame win/draw/loss and the points ledger are
  excluded from this page for the same reason they're excluded today).
- Drag-select range brushing on the trend chart — click-twice-to-set
  only, not click-and-drag.
- Any new engine/config-change annotation (e.g. flagging that depth
  changed mid-range) — out of scope, same as today.

## Testing

- `tests/integration/test_analysis_batches.py` (extend): the 5 new
  range-query functions, including the `run_a is None` ("Start") path
  and the swap-on-reversed-args path.
- FastAPI endpoint test for `/api/batch-impact/summary`: thin-wrapper
  assembly, reversed/degenerate params, `pendingAnnotation` path,
  records-in-range linear-scan logic (construct a small multi-run
  fixture with a known record run in the middle of the range).
- Vitest test for `dumbbellChart()` (node/series construction, sort-by-
  |delta| ordering).
- Hook test for `useBatchImpact` (mocked fetch, param changes).
- Component tests: `EndpointPicker` (all 3 click states + swap + From==To
  block), `RangeHeadline`, `RangeRecords` (empty vs. non-empty),
  `DumbbellSection`, `NewBlundersInRangeTable`, `BatchFinishedCard`
  (now-active link points at the right URL).
- Live verification (`verify` skill) against the real dev `chess.db`:
  confirm the chart-click endpoint picker actually drives the dropdowns,
  confirm the "Start" option reproduces the old first-batch numbers,
  and confirm the Analysis Jobs "See what changed →" link lands on the
  correct pre-filled range.

## Open items for the implementation plan to resolve

- Exact Plotly recipe for `dumbbellChart()` (per-category `shapes` line
  + two `scatter` marker traces vs. some other construction) — decide
  at implementation time against what renders cleanly with Plotly's
  categorical y-axis.
- Whether `DumbbellSection` is one generic component parameterized over
  value-shape (ACPL/blunder-rate pair vs. motif count) or two thin
  wrappers around a shared internal chart-builder — resolve once the
  motif dumbbell's data shape is being wired up and it's clear how much
  actually differs.
- Confirm `navCandidates.ts`'s static candidate list already has a
  `batch-impact` entry (mirroring how every prior slice found it already
  present, falling back to `PageStub`) rather than assuming — check
  before wiring `PAGE_COMPONENTS`.
