# Patterns & Tendencies — Slices 2+3 (Turning Points, Piece Handling) — Design

Status: pending user review
Branch: worktree-frontend-spike
Parent spec: `docs/superpowers/specs/2026-07-14-patterns-tendencies-page-design.md`
  (page-wide architecture, IA, and the original 7-slice roadmap — this doc
  only covers what's specific to slices 2 and 3, combined into one
  implementation unit per this session's explicit request)

## Context

Slice 1 (Scorecard + Clock & Time) shipped 2026-07-15. This spec covers
the next two slices from the roadmap — **Turning Points** (originally
slice 2) and **Piece Handling** (originally slice 3) — combined into a
single implementation unit at the user's request, rather than sequenced
separately.

**Trade-off, stated once here rather than re-litigated per section:**
Turning Points was deliberately sized as a cheap, low-risk validation
step ("prove the scorecard-card → tab-activation link works... before
committing to it on 6 more tabs"). Piece Handling is the largest scope
jump in the whole roadmap (5 panels, 2 new shared chart primitives, a
`view_by` toggle). Combining them means the first slice to add a second
scorecard entry + second tab is also the first slice exercising brand
new chart infrastructure. Both tabs have zero cross-tab code dependency
(confirmed in the parent spec), so this is safe to combine — just a
larger, less isolated unit of work than the original sequencing intended.
Accepted as-is per user direction.

The Streamlit source for both tabs (`dashboard/patterns_view.py`'s
`_render_tab_turning` at line 965 and `_render_tab_pieces` at line 869,
plus `dashboard/data/patterns.py`) is reference-only, per the standing
"Streamlit is reference not blueprint" directive. Neither
`patterns_view.py` nor `data/patterns.py` is modified by this work
except for one addition described below.

## Key decisions

1. **Turning Points' chart bucketing moves into the data layer, not the
   API layer or the client.** Streamlit currently does this bucketing
   (move-number bins, phase grouping, clock-fraction bucketing) inline in
   `patterns_view.py`'s render function — a Streamlit-convenience
   artifact, not evidence it belongs in the view layer. It's data-shaping
   of an already-computed query result (same category as the existing
   `bucket_acpl_blunder_rate`/`TIME_PRESSURE_BUCKETS` precedent already
   in `patterns.py`), not new analysis, so it stays consistent with every
   other slice's "thin FastAPI handler, presentational React component"
   convention. See "Backend: Turning Points" below.
2. **`groupedBarChart()` gains an optional explicit-color override**,
   beyond what the parent spec originally specced (palette assigned in
   series order only). The rook/king back-rank panel needs semantic
   colors (back rank = positive/green, elsewhere = negative/red, not
   palette order) — the same semantic-color need every existing
   single-series `bar_chart` call in this codebase already has via a
   fixed color argument. This is a small, backward-compatible extension
   to the primitive the parent spec already introduces in this same
   work, not a redesign — every other `groupedBarChart` caller keeps the
   default series-order palette.
3. **The square-blunder heatmap's pivot→long-form conversion happens in
   the FastAPI handler**, per the parent spec's own description of the
   `heatmap()` primitive's data contract (decision 4 in the parent spec)
   — `get_square_blunder_heatmap` already returns a pivoted DataFrame;
   the handler melts it into `{file, rank, blunder_rate, n_moves}` rows.
   This is serialization, not new analysis.

## Scope

### Turning Points tab (1 panel, no accordion)

Port of `_render_tab_turning`: for each loss where the position was
contested (win probability 30–70%), the single move that dropped the
most win probability. Shows a headline metric (median move number + most
common phase), a 2-up move-number/phase bar chart pair, and a
clock-remaining bar chart.

### Piece Handling tab (5 panels, accordion)

Port of `_render_tab_pieces`:
1. Piece ACPL + blunder rate (2-up bar charts) — **open by default**,
   matches its own scorecard headline.
2. Piece × phase / piece × sharpness (`view_by` toggle, grouped bar
   chart) — collapsed.
3. Bishop square-color performance + rook/king back-rank performance (bar
   chart + grouped bar chart with explicit colors) — collapsed.
4. Square blunder heatmap, with coverage disclaimer and conditional
   motif-backfill caption — collapsed.
5. Castling and king safety (bar chart + text caption) — collapsed.

## Backend

### Turning Points

**New in `dashboard/data/patterns.py`**: `get_decisive_moments_breakdown(duck_conn)`.
Calls the existing `get_decisive_moments(duck_conn)` once internally,
then produces the three transforms currently inlined in
`patterns_view.py` (same bins/labels/phase-order/`TIME_PRESSURE_BUCKETS`
as today — no behavior change, just relocated). Returns:

```python
{
    "n_losses": int,
    "median_move": int | None,           # None iff n_losses == 0
    "most_common_phase": str | None,      # None iff n_losses == 0
    "by_move_bucket": [{"bucket": str, "n_losses": int}, ...],
    "by_phase": [{"phase": str, "n_losses": int}, ...],
    "by_clock_bucket": [{"bucket": str, "n_losses": int}, ...],
    "n_no_clock_data": int,
}
```

On zero contested losses: `n_losses=0`, `median_move`/`most_common_phase`
`None`, all three list fields `[]`, `n_no_clock_data=0` — no exception,
matching every other `get_*` function's empty-input handling.

**`api/main.py`**: `/api/patterns/turning-points` — thin:
`_json_safe(data.get_decisive_moments_breakdown(duck_conn))`. New
`_patterns_turning_points_cache = _TTLCache(60)`, added to
`reset_caches()`.

**Scorecard card**: `_turning_points_tendency_card(duck_conn)` in
`main.py`, same location/shape as `_clock_time_tendency_card` — calls
`data.get_decisive_moments_breakdown(duck_conn)` independently (accepting
the double-compute on a Scorecard+tab-open combo, per slice 1's resolved
open item). Returns `None` only when `n_losses == 0` — no per-bucket
confidence gate needed (this aggregates to one median/mode across all
losses, unlike Clock & Time's per-bucket rates). Shape:

```python
{"tab_id": "turning-points", "label": "Turning Points",
 "headline": f"Losses typically turn at move {median_move} ({most_common_phase})",
 "detail": f"Based on {n_losses} losses with a contested position"}
```

### Piece Handling

**`api/main.py`**: `/api/patterns/pieces?view_by=phase|sharpness`
(default `phase`) — bundles, unchanged from `data.py`:
`get_piece_movement_patterns(duck_conn)`,
`get_piece_blunder_by_phase(sqlite_conn)` OR
`get_piece_blunder_by_sharpness(duck_conn)` per `view_by`,
`get_bishop_square_color_performance(duck_conn)`,
`get_rook_king_backrank_performance(duck_conn)`,
`get_square_blunder_heatmap(duck_conn)`, `get_castling_performance(duck_conn)`,
`tactical.motif_backfill_needed(duck_conn)`. Zero new SQL. New
`_patterns_pieces_cache = _TTLCache(60)` — cache key must include
`view_by` (two distinct cached payloads), added to `reset_caches()`.

Response shape:

```python
{
    "piece_movement": [{"piece": str, "piece_name": str, "n_moves": int,
                         "acpl": float, "blunder_rate": float}, ...],
    "piece_by_view": [{"piece": str, "piece_name": str,
                        "phase" | "bucket": str,   # key name depends on view_by
                        "n_moves": int, "blunder_rate": float}, ...],
    "bishop_square_color": [{"square_color": str, "n_moves": int,
                              "acpl": float, "blunder_rate": float}, ...],
    "rook_king_backrank": [{"piece": str, "piece_name": str, "location": str,
                             "n_moves": int, "acpl": float,
                             "blunder_rate": float}, ...],
    "square_heatmap": {
        "cells": [{"file": str, "rank": int, "blunder_rate": float,
                    "n_moves": int}, ...],   # [] if pivot is None
        "n_analyzed": int,
        "n_total_in_scope": int,
    },
    "motif_backfill_needed": bool,
    "castling": {
        "win": [{"status": str, "n_games": int, "win_pct": float}, ...],
        "acpl": [{"status": str, "n_games": int, "n_moves": int,
                   "acpl": float}, ...],
    },
}
```

The `square_heatmap.cells` melt happens in the handler:
`blunder_pivot`/`n_moves_pivot` (both indexed by rank, columned by file)
→ one row per non-null cell, `n_moves` sourced from the matching
`n_moves_pivot` cell.

**Scorecard card**: `_piece_handling_tendency_card(duck_conn)` — worst
blunder-rate piece from `get_piece_movement_patterns`'s result vs. the
all-piece mean, same worst-vs-baseline extraction shape as
`_clock_time_tendency_card`. Gated on the same
`confidence_tier(n_moves, BUCKET_MOVES_THRESHOLDS)` check used elsewhere;
returns `None` if fewer than 2 pieces clear the confidence gate.

```python
{"tab_id": "piece-handling", "label": "Piece Handling",
 "headline": f"{worst.piece_name} blunders most often, at {worst.blunder_rate:.1f}%",
 "detail": f"vs. {mean_blunder_rate:.1f}% average across all pieces"}
```

### `patterns_summary()`

`cards` list grows from `[_clock_time_tendency_card(duck_conn)]` to
`[_clock_time_tendency_card(duck_conn), _turning_points_tendency_card(duck_conn),
_piece_handling_tendency_card(duck_conn)]`, still filtered for `None`.

## New / extended shared primitives

### `lib/charts.ts`: `heatmap<T>()`

New, per parent spec decision 4: `heatmap(cells, x, y, z, colorscale,
options)` taking long-form `{x, y, z}` triples (here: `file`, `rank`,
`blunder_rate`). No in-cell text (matches Streamlit's hover+colorbar-only
convention). `hoverExtra` mirrors `lineChart`'s mechanism — an optional
extra pre-formatted value per cell (here: `"{n_moves} moves"` or `"--"`
for missing data, matching `patterns_view.py`'s existing
`n_moves_display` formatting).

**New addition to `lib/theme.ts`**: a `THEME.sequentialGold` colorscale
constant, ported from `dashboard/theme.py`'s
`SEQUENTIAL_GOLD_COLORSCALE` (read the Python constant's exact stops at
implementation time and port them 1:1 — this is a visual-parity
requirement, not a value to re-derive).

### `lib/charts.ts`: `groupedBarChart<T>()`

New, per parent spec decision 4, **with one extension over the parent
spec's original description**: `groupedBarChart(rows, x, groupCol, y,
options)` takes an optional `options.colors?: Record<string, string>` —
when present, each trace's color is looked up by its `groupCol` value
instead of assigned by series order. Used only by the rook/king
back-rank panel (`{"back rank": THEME.positive, "elsewhere": THEME.negative}`);
every other caller (piece × phase, piece × sharpness) omits `colors` and
gets the existing series-order palette behavior.

## Frontend

### `usePatternsTurningPoints` / `TurningPointsTab.tsx`

Hook: identical shape to `usePatternsClockTime`. Component: if
`n_losses === 0`, renders the established inline
`<p className="text-xs text-[var(--cw-muted)]">Not enough data yet.</p>`
convention (no shared empty-state component exists in this codebase —
every tab does this inline). Otherwise: a metric line (`Typically move
{median_move} ({most_common_phase})`, captioned with `n_losses`), then
`grid grid-cols-2 gap-4` (the established `render_comparison_panel`
equivalent already used in `RatingFormTab`/`NamedOpponentsTab`/
`OpponentProfilePanel`) for move-number + phase charts, then the
clock-bucket chart full-width below with a caption for `n_no_clock_data`
when nonzero.

### `usePatternsPieces` / `PieceHandlingTab.tsx`

Hook: takes `viewBy: 'phase' | 'sharpness'` and refetches on change
(query param, not a client-side re-filter — matches parent spec decision
6's precedent for `structure_type`/`grouped`/`piece_view_by`).
`viewBy` state lives in `PieceHandlingTab`, not lifted to `PatternsPage`.
Component: `Accordion` with panel 1 (`piece_movement`) open by default,
panels 2–5 collapsed:
- Panel 1: 2-up `barChart` (ACPL, blunder rate) via `piece_movement`.
- Panel 2: toggle control (`view phase` / `view sharpness`) +
  `groupedBarChart` on `piece_by_view` (`groupCol` is `"phase"` or
  `"bucket"` depending on `viewBy`).
- Panel 3: `barChart` on `bishop_square_color` + `groupedBarChart` (with
  `colors` override) on `rook_king_backrank`.
- Panel 4: if `square_heatmap.cells.length === 0`, the same
  "not enough data" inline convention (with `n_analyzed`/
  `n_total_in_scope` in the caption, matching
  `theme.thin_data_message`'s wording); else `heatmap` + coverage caption
  + conditional motif-backfill caption when `motif_backfill_needed`.
- Panel 5: `barChart` on `castling.win` + a text caption built from
  `castling.acpl` (matching the Streamlit caption's per-status ACPL
  join).

### `PatternsPage.tsx`

Grows from 1 tab to 3: `TabsTab`/`TabsPanel` entries for `turning-points`
and `piece-handling` added alongside the existing `clock-time`. Lazy-
mount behavior (existing `Tabs` primitive) unchanged — each tab's hook
only fires once activated.

## Testing

Per-tab, following the established recipe:
- `test_api_patterns.py`: both new endpoints (empty-DB and real-data
  cases for each; `view_by` both values for `/api/patterns/pieces`;
  `patterns_summary()`'s card count/order with all 3 cards present).
- `test_data_layer.py`: unit test for `get_decisive_moments_breakdown`
  (empty input, single-loss input, multi-bucket input).
- `usePatternsTurningPoints.test.ts`, `usePatternsPieces.test.ts`
  (loading → success/error, mocked `fetch`; the latter also covers a
  `viewBy` change triggering a refetch with the new query param).
- `TurningPointsTab.test.tsx`, `PieceHandlingTab.test.tsx` (mocked hook
  data; assert the "not enough data" text on empty inputs — no longer a
  blanket null-render, since Turning Points' whole-tab-empty case and
  Piece Handling's heatmap-empty case both need visible fallback text,
  matching Streamlit's own `st.info` behavior).
- `charts.test.ts`: `heatmap` and `groupedBarChart` (including the
  `colors` override case), covered once since both are shared
  infrastructure, not per-tab.
- `PatternsPage.test.tsx`: updated for 3 tabs and 3 scorecard cards,
  each card's click activating the right tab.
- Live verification via the `verify` skill against the real dev
  `chess.db`, after both tabs are wired in.

## Non-goals

- Any change to `dashboard/patterns_view.py` — left exactly as-is.
- Any change to `dashboard/data/patterns.py`'s existing functions —
  `get_decisive_moments_breakdown` is additive only.
- New backend analysis beyond what `patterns.py`/`tactical.py` already
  compute.
- A generic `<Table>` component (parent spec non-goal, still out of
  scope — neither tab in this slice has a table anyway).
- Confidence-tier gating on Turning Points' tab body itself — Streamlit
  doesn't have one here either (only its scorecard card does, via the
  simpler zero-check).
- `Accordion` open/close persistence across page revisits (parent spec
  open item — still unresolved, default to no persistence per that
  spec's reasoning).

## Open items for the implementation plan to resolve

- Exact `SEQUENTIAL_GOLD_COLORSCALE` stop values to port from
  `dashboard/theme.py` (read at implementation time, not guessed here).
- Whether `_patterns_pieces_cache`'s `view_by`-keyed caching is
  implemented as two separate `_TTLCache` instances or one cache keyed
  by a `(view_by,)` tuple — either is fine, resolve by whichever is less
  code against the existing `_TTLCache` implementation.
- Confirm live, on the real dev DB, that `square_heatmap.cells` is
  non-empty (i.e. `square_heatmap_min_moves` is cleared by at least one
  square) — if empty, the heatmap panel's empty-state path needs the
  same live-verification attention as every other "thin data" fallback
  on this page.
