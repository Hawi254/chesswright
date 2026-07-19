# Game Endings Page — "Ending Tree" Design

Status: pending user review
Branch: worktree-frontend-spike

## Context

`docs/frontend_migration_status.md` lists `game_endings_view.py` ("Game
Endings") as ⛔ not started. Per this session's explicit direction, this
is a **fresh design**, not a port of the Streamlit page's structure (6
stacked `st.container(border=True)` panels: end-type bar chart, end-type
% heatmap by time control, endgame-material grouped bar + table,
resignation-cause bar + 2 sub-breakdowns, a resignation trend line, a
time-forfeit cause breakdown + its own trend line). `dashboard/data/
game_endings.py` is read for business logic and underlying queries only,
per the standing "Streamlit is reference not blueprint" directive — kept
as-is, called from new code, never edited by this design.

Web research done this session on hierarchical-categorical dataviz
(icicle vs. sunburst charts), single-proportion callouts (waffle
charts), and how comparable products (Aimchess, ChessGoals, chess.com's
now-removed termination stats) frame "why did I lose" data informed the
layout below — see the brainstorm transcript for sources.

## Goals

- Answer "how do my games end, and why" as one coherent narrative
  instead of six independent charts covering overlapping dimensions
  (the Streamlit page's end-type bar chart and end-type-by-time-control
  heatmap both show the same End-type dimension twice).
- Let a loss's termination reason (resignation cause / time-forfeit
  cause) read as a genuine drill-down *into* the end-type breakdown,
  not a separate, disconnected panel.
- Add game-level drill-down (click a cause → see the actual games),
  which the Streamlit page has nowhere — matches the precedent already
  set by Matchups' nemesis tables and Game Explorer's row-click.
- Keep the existing "not yet analyzed" honesty from the Streamlit
  page's captions (resignation causes needing engine analysis vs.
  clock-based signals that don't) — this is a real data-quality fact,
  not decoration, and must survive the redesign.

## Non-goals

- Endgame Material Reached section drill-down into games — decided
  against for v1 to keep new backend surface scoped to the tree; still
  aggregate-only, same as today.
- Any change to `dashboard/data/game_endings.py`'s existing functions —
  read-only inputs; only new sibling functions are added.
- Ply-level deep link into a drilled-through game, sharing/export.
- Any Claude-generated narrative text — captions/labels are all
  template-filled from real fields, matching Tactical Highlights'
  precedent.
- A literal Sankey diagram — considered during research, rejected in
  favor of an icicle chart (better label legibility, no radial
  compression, and its rectangle-length encoding is easier to compare
  than Sankey's flow-width encoding for this non-flow, strictly
  hierarchical data).

## Data scope (from `dashboard/data/game_endings.py`, read-only)

| Section | Source function(s) |
|---|---|
| Ending Tree | `get_game_end_type_breakdown`, `get_resignation_loss_causes`, `get_time_forfeit_loss_breakdown` |
| Hero stats | Same three, aggregated further (see below) |
| Endgame Material Reached | `get_endgame_type_performance` |
| Trends | `get_resignation_time_pressure_trend`, `get_time_forfeit_loss_breakdown`'s `trend_df` |

## Layout

Single-column page, four `ZoneHead`-sectioned zones top to bottom:
**Hero stats** → **Ending Tree** (icicle + drill-down panel) →
**Endgame Material Reached** → **Trends**. No `Tabs` primitive — the
icicle's own interaction is the page's primary navigation, unlike
Matchups/Patterns which need tabs to fit more content than displays at
once.

### 1. Hero stats row

Three tiles, new small `EndingStatTile` component (own row, styled like
`MilestonesRow`'s chip row but larger — closer to `HeroInsight`'s
single-card treatment, one per stat):

1. **Total games** — count + decisive/draw split, e.g. "2,847 games —
   71% decisive, 29% draws," from `get_game_end_type_breakdown`'s
   `overall` frame (win+loss end types vs. draw end types).
2. **Resignation losses explained** — new `WaffleStat` component (10×10
   grid, one cell per percentage point, filled cells = explained share)
   showing `reason_df`'s `n_explained / n_total` from
   `get_resignation_loss_causes` — the Streamlit page's existing "62 of
   100 explained" caption, given a real visual. Not-yet-analyzed cells
   render in `THEME.textMuted`, explained cells in `THEME.accentGold`.
3. **Flagged while ahead** — callout stat, `material_df`'s "ahead by
   N+ points" row's `pct` from `get_time_forfeit_loss_breakdown` — the
   single most actionable number in the dataset (mirrors Aimchess's
   "Advantage Capitalization" framing: banked points left on the
   table). Rendered in `THEME.negative` — it's a loss-side stat.

Any tile whose source frame is empty renders a muted "not enough games
yet" state instead of a stat, same spirit as `thin_data_message`.

### 2. Ending Tree — icicle chart

New `EndingTreeIcicle` component wrapping a `Plot` (`react-plotly.js`,
`type: 'icicle'`) via a new `icicleChart()` helper in
`frontend/src/lib/charts.ts`, following the existing helpers' shape
(`rows`, options, returns `{ data, layout }`).

**Hierarchy** (Plotly icicle's flat `ids`/`labels`/`parents`/`values`
shape, assembled server-side — see Backend section):

```
All games
├─ Win
│  ├─ Checkmate
│  ├─ Resignation (opponent)
│  ├─ Time forfeit (opponent)
│  └─ ... (other end types, from _END_TYPE_LABELS)
├─ Draw
│  ├─ Repetition
│  ├─ Stalemate
│  ├─ Draw by agreement
│  ├─ 50-move rule
│  └─ Insufficient material
└─ Loss
   ├─ Checkmate                          (leaf — no cause data)
   ├─ Resignation
   │  ├─ Hung a piece
   │  ├─ Faced a forced mate
   │  ├─ Time pressure
   │  ├─ Other / gradual decline
   │  └─ Not yet analyzed              (muted color — data gap, not a finding)
   └─ Time forfeit
      ├─ Ahead on material
      ├─ Roughly level
      └─ Behind on material
```

Only Loss→Resignation and Loss→Time-forfeit get a cause level — every
other leaf (e.g. Win→Checkmate) terminates one level early since
`game_endings.py` has no cause classification for wins/draws or for
checkmate losses. Win/Loss/Draw's own end-type children reuse
`_END_TYPE_LABELS`' wording (ported to a shared frontend constant, not
re-typed).

**Time-control filter**: a segmented control (All / Bullet / Blitz /
Rapid / Classical, matching the time-control categories already used
elsewhere in the app) above the chart re-scopes the whole tree via a
`time_control` query param. This is a deliberate decision to **not**
carry over the Streamlit page's end-type-%-by-time-control heatmap as a
separate panel — the icicle's own filter covers the same comparison
interactively; the trade-off (can't see all time controls
simultaneously) was confirmed with the user.

**Color**: Win branch in `THEME.positive`, Draw in `THEME.accentGold`,
Loss branch in `THEME.negative`, with each branch's own children a
lighter/muted shade of the same hue (Plotly icicle supports per-node
color arrays) — "Not yet analyzed" is the one exception, always
`THEME.textMuted` regardless of branch, so the data-gap reads visually
distinct from an actual chess finding at a glance.

**Node click → drill-down panel** (`EndingTreeDrilldown`, renders below
the chart on all viewports — a true side-by-side panel was considered
but rejected since the chart itself needs full width to keep node
labels legible per the research above):

- Breadcrumb (e.g. "Loss → Resignation → Hung a piece"), count, and %
  of its immediate parent.
- `ClickableGameList` (existing component) of the underlying games,
  capped at 20 with a "+N more" note, routed through a new
  `game-endings/:gameId` → `GameDetailPage` hidden route (same pattern
  as `game-explorer/:gameId`, `matchups/:gameId`,
  `tactical-highlights/:gameId` already in `App.tsx`).
- Cause-leaf nodes only: a small secondary bar chart reusing the
  existing `barChart()` helper — hung-piece nodes show `piece_df` (which
  piece), faced-mate nodes show `mate_df` (mate distance), time-forfeit
  material-bucket nodes show the matching `scramble_df` slice (opponent's
  clock at the flag) since scramble context is a crossed axis, not a
  further hierarchy level (nesting both material and scramble in the
  icicle would push depth to 5 levels, past where research says labels
  stay legible).
- Root/no-selection state: shows the same panel scoped to "All games"
  (no game list — 2,847 rows isn't a useful list — just the breadcrumb
  and a prompt to click a segment).

### 3. Endgame Material Reached

Separate section — a different axis (game phase reached, not
termination reason), doesn't belong inside the icicle's hierarchy.
Grouped bar (win/draw/loss % by Queen/Rook/Minor-piece/King&pawn
endgame, reusing `groupedBarChart()`) plus a row of small stat cards
(ACPL, blunder rate, game count per type) styled like Patterns'
`TendencyCard`, replacing the Streamlit page's raw `st.dataframe`. No
drill-down (see Non-goals).

### 4. Trends

One panel, a segmented toggle switching between two views instead of
the Streamlit page's two stacked panels:

- **"Resignations: time pressure"** — single line
  (`get_resignation_time_pressure_trend`'s `pct`), reuses `lineChart()`
  as-is.
- **"Time forfeits: ahead vs. scrambling"** — two-line
  (`trend_df`'s `pct_ahead`/`pct_mutual`), reuses `multiLineChart()` as-is.

No new chart code for this section — the reduction from 2 panels to 1
is purely an IA simplification.

### Empty/thin-data states

Same convention as every other ported page: any zero-row aggregate
renders an inline empty-state message instead of a blank chart. The
icicle specifically falls back to just the Win/Draw/Loss → End-type
levels (no Cause level rendered at all) if `reason_df` and
`time_forfeit`'s frames are both empty — i.e., no losses have any cause
data yet, which is a real state for a freshly-onboarded account.

## Backend

### New API endpoints (`api/main.py`)

```python
@app.get("/api/game-endings/tree")
def game_endings_tree(time_control: str | None = None):
    sqlite_conn, duck_conn = get_db_connections()
    return data.build_ending_tree(sqlite_conn, duck_conn, time_control=time_control)


@app.get("/api/game-endings/games")
def game_endings_games(path: str = Query(...)):
    # path is the icicle node's id, e.g. "loss/resignation/hung_piece"
    sqlite_conn, duck_conn = get_db_connections()
    return data.get_games_for_ending_node(sqlite_conn, duck_conn, path)


@app.get("/api/game-endings/summary")
def game_endings_summary():
    # hero stats + endgame-material section + trends, one bundled
    # payload matching the "one payload per page section" precedent
    # already used by Analysis Jobs' status endpoint and each Patterns tab
    sqlite_conn, duck_conn = get_db_connections()
    return data.build_ending_summary(sqlite_conn, duck_conn)
```

Three endpoints, not one bundled payload, because the icicle's own
time-control filter needs to re-fetch independently of the rest of the
page, and the drill-down game list is fetched lazily per click (loading
all buckets' game lists up front would be wasted work on a page most
users won't click every node of).

### New data-layer functions (`dashboard/data/game_endings.py`)

- `build_ending_tree(sqlite_conn, duck_conn, time_control=None)` —
  calls the three existing aggregate functions, optionally passing
  `time_control` through to a new optional filter parameter on
  `get_game_end_type_breakdown`, `get_resignation_loss_causes`, and
  `get_time_forfeit_loss_breakdown` (each gains a `time_control=None`
  kwarg that adds a `WHERE time_control_category = ?` to its existing
  query — the causes queries currently have no time-control awareness
  at all, so this is genuinely new filtering, not just plumbing).
  Assembles the flat `ids`/`labels`/`parents`/`values` icicle shape
  client-callable from `EndingTreeIcicle`, each node's `id` being the
  slash-joined path (e.g. `"loss/resignation/hung_piece"`) reused
  verbatim as `EndingTreeDrilldown`'s lookup key.
- `get_games_for_ending_node(sqlite_conn, duck_conn, path)` — parses
  `path`, dispatches to one of three new small sibling query functions
  that mirror the exact WHERE-clause/CTE semantics of the matching
  aggregate function but `SELECT game_id` (capped, ordered by date
  descending) instead of `COUNT(*)`:
  - `_game_ids_for_result_endtype(duck_conn, result, end_type, time_control=None)`
    — mirrors `get_game_end_type_breakdown`'s grouping.
  - `_game_ids_for_resignation_cause(duck_conn, reason, config_path=None)`
    — mirrors `get_resignation_loss_causes`'s CTE chain, same priority
    order (hung_piece > faced_mate > time_pressure > other >
    not_analyzed).
  - `_game_ids_for_time_forfeit_bucket(duck_conn, bucket, config_path=None)`
    — mirrors `get_time_forfeit_loss_breakdown`'s material-bucket logic.
- `build_ending_summary(sqlite_conn, duck_conn)` — hero-stat
  aggregation (decisive/draw split, resignation-explained ratio,
  flagged-while-ahead pct) plus the existing `get_endgame_type_performance`,
  `get_resignation_time_pressure_trend`, and time-forfeit `trend_df`,
  bundled into one payload for the three lower sections.

## Frontend

### Hooks

- **`useEndingTree(timeControl)`** — refetches on `timeControl` change,
  matches `useOpeningsTable`'s param-driven refetch style (not a
  polling hook). Returns `{ tree, loading, error }`.
- **`useEndingTreeDrilldown(path)`** — lazy, fires only when `path` is
  set (a node was clicked), matches the "fetch on demand" style already
  used by Matchups' per-opponent panel fetch. Returns
  `{ games, secondaryChart, loading, error }`.
- **`useEndingSummary()`** — single fetch on mount, matches
  `useOverviewData`'s style. Returns `{ summary, loading, error }`.

### Components

- **`GameEndingsPage.tsx`** — composes the three hooks, owns
  `timeControl` and `selectedPath` state, renders the four zones.
- **`EndingStatTile.tsx`** / **`WaffleStat.tsx`** — hero row tiles;
  `WaffleStat` is the one genuinely new visual primitive, a plain CSS
  grid (no Plotly — a 10×10 grid of `div`s is cheaper and easier to
  theme than a chart library for this), reusable later if another page
  wants a single-proportion callout.
- **`EndingTreeIcicle.tsx`** — the `Plot` wrapper, takes `tree` +
  `onNodeClick`.
- **`EndingTreeDrilldown.tsx`** — breadcrumb + `ClickableGameList` +
  conditional secondary `barChart()`.
- **`EndgameMaterialSection.tsx`** — grouped bar + `TendencyCard`-style
  stat row.
- **`EndingTrendsPanel.tsx`** — segmented toggle + `lineChart()` /
  `multiLineChart()`.

### Page wiring

`PAGE_COMPONENTS['game-endings'] = GameEndingsPage` in `App.tsx` (nav
entry already exists in `navCandidates.ts:18`, currently falling back
to `PageStub`). New hidden route:

```tsx
<Route path="game-endings/:gameId" element={<GameDetailPage />} />
```

## Testing

- `tests/integration/test_api_game_endings.py` (new): tree assembly
  correctness (node `values` sum to parent, "Not yet analyzed" only
  appears under Loss→Resignation, no Cause level under Win/Draw or
  Loss→Checkmate), `time_control` filtering narrows correctly,
  `get_games_for_ending_node` returns game IDs matching each of the
  three dispatch branches' aggregate-query semantics (cross-checked
  against the existing aggregate functions' counts), empty-DB case
  (tree collapses to a single "All games" root node, summary returns
  zeroed stats).
- `useEndingTree.test.ts` / `useEndingTreeDrilldown.test.ts` /
  `useEndingSummary.test.ts` — success/error/loading shape, refetch-on-
  param-change for the tree hook, fetch-on-demand for the drilldown hook.
- Component tests: `WaffleStat.test.tsx` (cell count matches
  percentage), `EndingTreeIcicle.test.tsx` (node click fires
  `onNodeClick` with the right path), `EndingTreeDrilldown.test.tsx`
  (breadcrumb rendering, game list cap + "+N more", secondary chart
  only for cause-leaf paths), `EndgameMaterialSection.test.tsx`,
  `EndingTrendsPanel.test.tsx` (toggle switches series),
  `GameEndingsPage.test.tsx` (composition, time-control filter
  triggers refetch, node click sets `selectedPath`).
- Live verification (`verify` skill): confirm the tree renders real
  proportions from the dev `chess.db`, confirm a resignation
  hung-piece node's drill-down games actually show a hung piece near
  the game's end, confirm the time-control filter changes the tree,
  confirm drill-through opens the right game.

## Open items for the implementation plan to resolve

- Exact cap and ordering for `ClickableGameList` under a large bucket
  (e.g. "Loss → Time forfeit" could have hundreds of games) — 20 +
  "+N more" is provisional, confirm it reads well live rather than
  needing pagination.
- Whether the icicle's "Not yet analyzed" muted color needs a legend
  entry or is self-explanatory from the drill-down panel's breadcrumb —
  decide once it's on screen.
- Confirm Plotly's `icicle` trace type's built-in interaction (default
  click-to-zoom behavior) doesn't fight the custom `onNodeClick`
  drill-down handler — may need `layout.icicle.pathbar` or a hover-only
  zoom config; verify against the real Plotly.js version pinned in
  `frontend/package.json` at implementation time.
