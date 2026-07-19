# Patterns & Tendencies Page — Design

Status: pending user review
Branch: worktree-frontend-spike

## Context

`docs/frontend_migration_status.md` lists `patterns_view.py` ("Patterns &
Tendencies") as ⛔ not started, with its own note flagging it as "the
largest Streamlit view... likely needs its own multi-slice breakdown
rather than one pass." This spec confirms that and produces the actual
breakdown: a page-wide design (architecture, IA, new shared primitives)
plus a 7-slice build roadmap, each slice sized like every other
`port-view-slice` unit shipped so far (Overview's zones, Matchups'
`RatingFormTab`/`NamedOpponentsTab`).

The Streamlit source (`dashboard/patterns_view.py`, ~1035 lines, plus
`dashboard/data/patterns.py`, ~1367 lines) is a source for business logic
and requirements only, per the standing "Streamlit is reference not
blueprint" directive — it renders 7 always-expanded tabs
(`st.tabs` + `st.fragment`) totaling ~30 panels, none collapsible, all
computed eagerly the moment their tab mounts.

Per this session's explicit direction, the visual/interaction design is
not a 1:1 port either. Web research done this session (2026-07-14) on
current dashboard UX practice found the field has moved away from
"more charts visible = more powerful" toward progressive disclosure —
Nielsen Norman Group's guidance that dashboards with more than ~7
competing elements above the fold see higher abandonment, and that a
three-layer model (headline summary → open detail → expand-on-intent)
outperforms flat KPI grids. Aimchess (a direct product comparable — chess
performance analytics scored across ~6 tendency categories) was also
reviewed as a concrete precedent for a scored-category summary layer.
Patterns & Tendencies is the one page in this app's whole migration where
that research is most directly applicable: it is the single densest page
by panel count, more than 4x any page ported so far.

## Goals

- Full parity with all 7 Streamlit tabs' underlying questions and every
  chart/table they currently show — no analysis capability lost.
- Cut perceived density via a 3-layer progressive-disclosure structure
  (scorecard → tabs → accordion) instead of flattening ~30 always-open
  panels, without inventing new backend analysis to do it.
- Reuse already-built infrastructure over re-deriving it: the `Tabs`
  primitive, `InsightCard`/`ConfidenceBadge`'s visual language, the
  `_TTLCache` bundled-endpoint pattern from Matchups.
- Produce a concrete, ordered slice roadmap so this page can be built
  incrementally across sessions like every other page, instead of
  attempted as one oversized plan.

## Key decisions (from this session's brainstorm + web research)

1. **Three-layer structure: Tendency Scorecard → Tabs (same 7 areas as
   Streamlit) → Accordion within each tab.** The 7-way split itself is
   kept (it's a real, already-validated information architecture — the
   6c.4 merge that produced it is documented in `patterns_view.py`'s own
   docstring) — the win-rate problem is panel density *within* a tab, not
   the top-level split, so only two new layers are added around the
   existing one, not a full IA rewrite.
2. **Tendency Scorecard is new: 7 cards, one per tab, each showing one
   headline stat** pulled from that tab's own primary query (e.g. Clock &
   Time → blunder rate at critical vs. plenty clock; Turning Points →
   median decisive-move number and phase). Computed server-side from
   functions `dashboard/data/patterns.py` already exposes — no new
   analysis, this is the "pick the headline number out of an existing
   result" pattern, same spirit as Overview's `CareerHighlight`. Clicking
   a card activates that tab (`Tabs`' existing `defaultValue`/controlled-
   value support).
3. **New `Accordion` primitive, not a second `Tabs` nesting.** Within a
   tab, the 1-2 panels closest to that tab's headline question render
   open by default; the rest collapse. Accordion (not nested tabs) because
   these panels are sequential elaborations of one question, not
   independent alternatives — nested tabs would imply mutual exclusivity
   that isn't true here (e.g. Clock & Time's 4 panels are all "yes, and"
   the same time-pressure question, not "either/or").
4. **Two new chart primitives added to `lib/charts.ts`, each used across
   multiple slices**: `heatmap()` (ports Streamlit's `charts.heatmap`,
   needed by Game Context's day/hour win-rate map and Piece Handling's
   per-square blunder map) and `groupedBarChart<T>()` (true n-series
   grouped bars — piece × phase is 3 series, piece × sharpness is 5;
   the existing `overlayBarChart` only supports exactly 2 fixed series
   and doesn't fit either). Both built once, in the first slice that
   needs each, then reused as-is by every later slice.
5. **No new generic `<Table>` abstraction.** Every table on this page
   (material-structure, all-sessions, named-tournaments) is hand-rolled
   per component, matching this codebase's existing convention
   (`OpeningsTableSection`, `NemesisTable`, `GameExplorerTable` each do
   this already) rather than introducing a shared table component this
   page would be the first user of.
6. **Streamlit's two radio-button toggles become query params**, not
   client-side re-filters of a pre-fetched superset:
   `material_structure_type`/`grouped` on the Positions endpoint,
   `piece_view_by` on the Pieces endpoint — mirrors how `/api/matchups/
   nemesis` already takes `min_games` as an optional query param rather
   than fetching all variants up front.
7. **One bundled endpoint per tab (8 total, including the scorecard),
   not one per query.** Every tab's panels are always needed together on
   first mount with no independent per-panel loading state (same
   reasoning `/api/matchups/rating-form`'s docstring already gives for
   bundling its 6 queries) — 8 bundled fetches beats ~25 individual ones,
   and keeps one `_TTLCache` entry per tab.

## Page structure

```
PatternsPage
├── TendencyScorecard          (new — 7 TendencyCards, always visible)
└── Tabs (existing primitive)
    ├── Clock & Time tab       → Accordion: 4 panels (1-2 open)
    ├── Comparisons tab        → Accordion: 6 panels (1-2 open)
    ├── Game Context tab       → Accordion: 2 panels
    ├── Playing Sessions tab   → Accordion: 6 panels (1-2 open)
    ├── Positions tab          → Accordion: 6 panels (1-2 open)
    ├── Piece Handling tab     → Accordion: 5 panels (1-2 open)
    └── Turning Points tab     → 1 panel, no accordion needed
```

Each tab panel is lazy-mounted (existing `Tabs` behavior) — a tab's hook
only fires once that tab has been activated at least once, same as
Matchups/Openings.

## New shared primitives

### `components/ui/accordion.tsx`

Minimal, presentational: `<Accordion defaultOpen={string[]}>` wrapping
`<AccordionItem value id title>` children, each toggling its own open
state independently (not single-open-at-a-time — several panels in
Comparisons are meant to be compared side by side once open). No
animation library dependency; a CSS `grid-template-rows` 0fr/1fr
transition (the standard height-auto-animation technique) is sufficient
and keeps this dependency-free like every other `components/ui/*`
primitive in this codebase.

### `lib/charts.ts` additions

- `heatmap<T>(pivotedRows, x, y, z, colorscale, options)` — takes
  already-pivoted `{x, y, z}` long-form rows (the FastAPI endpoint pivots
  server-side via pandas, same as Streamlit's `data.py` functions already
  do, then the JSON payload is long-form triples rather than a 2D array —
  simpler to serialize and type than shipping a matrix over JSON). No
  in-cell text (matches Streamlit's contrast-driven "hover + colorbar
  only" convention, `charts.py`'s `heatmap()` docstring). `hoverExtra`
  mirrors `lineChart`'s mechanism: an optional extra value per cell,
  pre-formatted by the caller.
- `groupedBarChart<T>(rows, x, groupCol, y, options)` — one bar-trace per
  distinct `groupCol` value, `barmode: 'group'`, palette assigned in
  series order from `THEME` (falls back to a small fixed sequence beyond
  `THEME`'s named colors if a group cardinality ever exceeds it — not
  expected here: max 5 sharpness buckets).

### `components/TendencyCard.tsx`

Presentational: `{ label, headline, detail, onClick }`. Visually a
lighter sibling of `InsightCard` (same card shell, condensed label,
`--cw-copper` accent) but without `InsightCard`'s severity chip or
`ConfidenceBadge` — scorecard entries are headline stats, not scored
`Finding` objects, so forcing them through the `Finding` severity model
would misrepresent panels (Comparisons, Playing Sessions, Turning Points)
that have no corresponding entry in `dashboard/data/insights.py`'s
`get_career_findings` at all.

## Backend: FastAPI endpoints (`api/main.py`)

One `_TTLCache(60)` per tab (8 total, all added to `reset_caches()`),
same pattern as `_matchups_static_cache`:

```python
@app.get("/api/patterns/summary")
def patterns_summary():
    """One headline stat per tab, computed from the same functions the
    per-tab endpoints below call — no new queries, just picking the
    lead number out of each existing result."""
    ...

@app.get("/api/patterns/clock-time")
def patterns_clock_time():
    # bundles: blunder_rate_by_time_pressure, acpl_by_time_control,
    # thinking_time_blunder_correlation, instant_move_rate_by_phase,
    # instant_move_accuracy_by_legal_replies

@app.get("/api/patterns/comparisons")
def patterns_comparisons():
    # bundles: favorite_underdog_performance, clock_pressure_by_rating_bucket,
    # openings_by_rating_bucket, clock_pressure_by_outcome,
    # clock_pressure_by_color, clock_pressure_by_opening

@app.get("/api/patterns/game-context")
def patterns_game_context():
    # bundles: phase_accuracy, day_hour_heatmap

@app.get("/api/patterns/sessions")
def patterns_sessions():
    # bundles: session_rollup, prior_outcome_performance,
    # session_position_performance, event_type_performance,
    # event_name_breakdown

@app.get("/api/patterns/positions")
def patterns_positions(structure_type: str = "endgame", grouped: bool = False):
    # bundles: sharpness_blunder_correlation, material_structure_table
    # OR material_structure_bucket_table (per `grouped`), bishop_color_ending_performance,
    # position_character_performance, game_side_performance

@app.get("/api/patterns/pieces")
def patterns_pieces(view_by: str = "phase"):
    # bundles: piece_movement_patterns, piece_blunder_by_phase OR
    # piece_blunder_by_sharpness (per `view_by`), bishop_square_color_performance,
    # rook_king_backrank_performance, square_blunder_heatmap, castling_performance

@app.get("/api/patterns/turning-points")
def patterns_turning_points():
    # bundles: decisive_moments
```

Notes:
- Every handler calls `data.get_*` from `dashboard/data/patterns.py`
  exactly as it exists today, then `.to_dict(orient="records")` /
  `.to_dict()` — zero new SQL, per the port-view-slice core rule.
- `structure_type`/`grouped`/`view_by` are the only endpoints taking
  query params; every other tab's queries are fully argument-less
  (mirrors `/api/matchups/rating-form`).
- Any 64-bit hash/ID column reachable from this page (none currently
  identified in `patterns.py`'s return columns, but re-check at
  implementation time) must round-trip as a JSON string per the
  `port-view-slice` skill's `zobrist_hash` precedent.

## Slice roadmap

Each slice below follows the `port-view-slice` recipe in full (backend
endpoint + test, frontend hook + test, frontend component + test, wire
into `PatternsPage`, live-verify, commit, update
`docs/frontend_migration_status.md`). This spec does not re-derive that
recipe per slice — only what's specific to each one.

1. **Scorecard + Clock & Time.** Builds `TendencyCard`, `Accordion`,
   `patterns/summary` + `patterns/clock-time` endpoints,
   `useTendencyScorecard`/`usePatternsClockTime` hooks. Highest
   player-value tab (the page's own caption already frames the whole
   page as "when do you play worse, when do you play better" — Clock &
   Time is the most direct answer to that). No new chart primitives
   needed (reuses existing `barChart`).
2. **Turning Points.** Smallest tab (1 panel, no accordion needed) —
   cheap slice to prove the scorecard-card → tab-activation link works
   before committing to it on 6 more tabs.
3. **Piece Handling.** Introduces `heatmap()` (square blunder map) and
   `groupedBarChart()` (piece × phase / piece × sharpness toggle).
4. **Positions.** Reuses both primitives from slice 3, adds the
   structure-type/grouped toggle table (hand-rolled, per decision 5) and
   the bishop-ending comparison cards.
5. **Game Context.** Reuses `heatmap()` from slice 3 (day/hour win-rate
   map) — smallest remaining tab (2 panels).
6. **Comparisons.** Largest single tab (6 panels, several overlay
   comparisons via the existing `overlayBarChart`) — built once every
   primitive it could need already exists from slices 1-5.
7. **Playing Sessions.** Last — shares two cached query results with
   Game Context (`get_session_position_performance`,
   `get_prior_outcome_performance` both also feed Game Context's
   `phase_accuracy`-adjacent questions in Streamlit, per
   `patterns_view.py`'s own fragment-isolation comment), so building it
   last means both tabs' shapes are already settled.

No slice after the first two strictly depends on a prior slice's
*code* (each tab's data is independent, per `patterns_view.py`'s own
"no cross-tab state/data dependency" comment) — the ordering above is
sequencing for primitive-reuse efficiency and risk (cheapest/highest-
value first), not a hard dependency chain. Slices 3-7 could be
reordered or parallelized across sessions without breaking anything.

## Non-goals

- Any change to `dashboard/patterns_view.py` or `dashboard/data/patterns.py`
  — left exactly as-is; the Streamlit page keeps working unmodified.
- New backend analysis beyond what `patterns.py` already computes — the
  scorecard's headline stats are extracted from existing results, not
  new queries.
- Claude-narrative commentary for this page — Streamlit's
  `patterns_view.py` has none today, so there's no parity gap to close.
- A shared generic `<Table>` component (decision 5) — out of scope here,
  would be a separate, page-agnostic proposal if ever pursued.
- Collapsing the 7-tab split itself into fewer top-level sections — this
  session tested that option (see the "IA approach" discussion) and
  chose the 3-layer approach over consolidation.

## Testing

Per-slice, following `port-view-slice`'s established shape:
`tests/integration/test_api_patterns.py` (one file, all 8 endpoints,
grouped by slice as they land, using `TestClient` + `migrated_db_path`
+ `reset_caches()`), one `use*.test.ts` per hook (loading → success/error
transitions, mocked `fetch`), one `*.test.tsx` per component (mock hook
data; assert `null` render on loading/error/empty), `Accordion.test.tsx`
and `heatmap`/`groupedBarChart` covered once in `charts.test.ts` since
both are shared across slices, `PatternsPage.test.tsx` last (scorecard
card click activates the right tab, lazy hook firing per tab). Live
verification via the `verify` skill after each slice, against the
worktree's real `chess.db`.

## Open items for each slice's implementation plan to resolve

- Exact `Accordion` open/close persistence (per-session React state only,
  vs. `persist_filter`-style survival across a page revisit) — Streamlit's
  own tabs/radios don't persist across a full page nav either, so default
  to no persistence unless a slice's live-verification pass suggests
  users expect otherwise.
- Whether `TendencyCard`'s "click to activate tab" needs the scorecard to
  scroll into the tab's position or whether `Tabs`' existing panel
  swap is enough on its own (page is tall enough with 7 tabs that a
  scorecard-then-tabs layout may put the clicked tab's content below the
  fold) — resolve during slice 1's live-verification pass.
- Whether `patterns/summary`'s 7 headline stats are computed by calling
  each tab's own bundled-query functions a second time (simple, but a
  double DB hit on first Scorecard+tab-open combo) or factored to share
  results with the per-tab endpoint via the `_TTLCache` — resolve at
  slice 1 implementation time by measuring actual cost on the real DB
  (32k games) rather than assuming.
