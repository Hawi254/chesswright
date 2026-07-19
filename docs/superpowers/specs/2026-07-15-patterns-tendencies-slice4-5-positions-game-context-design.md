# Patterns & Tendencies — Slices 4+5 (Positions, Game Context) — Design

Status: pending user review
Branch: worktree-frontend-spike
Parent spec: `docs/superpowers/specs/2026-07-14-patterns-tendencies-page-design.md`
  (page-wide architecture, IA, and the original 7-slice roadmap — this doc
  only covers what's specific to slices 4 and 5)
Prior slice spec: `docs/superpowers/specs/2026-07-15-patterns-tendencies-
  slice2-3-turning-points-piece-handling-design.md` (Turning Points +
  Piece Handling, shipped 2026-07-15 — established the dict-of-`_TTLCache`
  param-caching precedent and the `heatmap()`/`groupedBarChart()`
  primitives this spec reuses unchanged)

## Context

Slices 1–3 (Scorecard + Clock & Time; Turning Points; Piece Handling)
have shipped. This spec covers the next two slices from the roadmap —
**Positions** (originally slice 4) and **Game Context** (originally slice
5) — combined into one implementation unit per this session's explicit
direction, the same reasoning slices 2+3 were combined on: both tabs have
zero cross-tab code dependency (confirmed in the parent spec), and
pairing the roadmap's largest remaining tab (Positions, 7 panels) with
its smallest (Game Context, 2 panels) keeps the combined unit similarly
sized to slices 2+3, while Game Context fully reuses the `heatmap()`
primitive slice 3 already built — no new chart infrastructure needed by
either tab in this slice.

The Streamlit source for both tabs (`dashboard/patterns_view.py`'s
`_render_tab_position` at line 678 and `_render_tab_rhythm` at line 489,
plus `dashboard/data/patterns.py`) is reference-only, per the standing
"Streamlit is reference not blueprint" directive. Neither
`patterns_view.py` nor `dashboard/data/patterns.py` is modified by this
work.

**Correction to the parent spec:** its page-structure diagram estimates
Positions at "6 panels." Reading `_render_tab_position` directly shows 7
real UI panels — `get_position_character_performance` and
`get_game_side_performance` each drive two panels from one query
(open/semi-open/closed + symmetric/asymmetric; castling + queenside/
kingside action, respectively). The bundled-query list in the parent
spec's endpoint sketch was already correct (5 queries); only the
UI-panel count needed correcting. This doc uses 7 throughout.

## Key decisions

1. **Positions' endpoint caches on a 4-way dict**, keyed by
   `(structure_type, grouped)` — `_patterns_positions_cache: dict[tuple[str,
   bool], _TTLCache]`, all four combos constructed up front and looped
   over in `reset_caches()`. Directly extends the `_patterns_pieces_cache`
   dict-of-`_TTLCache` precedent slice 3 established for a single param;
   same accepted trade-off carries over unchanged — the 5 params-
   independent queries (sharpness, bishop endings, position character,
   game side) recompute identically across all 4 cache slots, exactly as
   Piece Handling's bundle already recomputes its 4 params-independent
   queries across its 2 `view_by` slots.
2. **`material_sig` display formatting happens server-side.**
   `chess_display.material_sig_str` (Python-only, not ported to TS) is
   called in the handler before serializing non-grouped rows, and the
   response uses one unified `label` key regardless of `grouped` — the
   frontend table never branches on which column holds the row label,
   unlike Streamlit's `label_col`/`label_header` switch, which existed
   only because `st.dataframe`'s `column_config` needs an actual column
   *name* to key off of, a constraint a hand-rolled React `<table>`
   doesn't share. Matches the "pre-formatted by the caller" principle the
   `heatmap()` primitive's `hoverExtra` already established.
3. **Day-of-week int→label mapping (`Mon`..`Sun`) happens server-side**,
   before the day/hour melt into long-form cells — same reasoning, and
   matches how slice 3's square-blunder heatmap melt was done entirely in
   the handler rather than partly on the client.
4. **`n_unanalyzed` (material structure) and the coverage caption logic
   (`_coverage_caption`) are computed differently**: `n_unanalyzed` is a
   trivial count, computed server-side and returned as a field (avoids
   re-deriving it from raw rows in the component). `_coverage_caption`'s
   string-building (win-table/ACPL-table sample-size join) is pure
   presentation logic with no chess-domain dependency, so it's ported
   client-side as a small shared helper in `PositionsTab.tsx`, reused by
   all 4 of that tab's comparison-style panels rather than duplicated 4x.
5. **No new chart primitives.** Both tabs are fully served by
   `barChart` (existing since slice 1) and `heatmap` (existing since
   slice 3, used unchanged for the day/hour grid — same long-form
   `{x, y, z}` contract, just a different x/y domain).

## Scope

### Positions tab (7 panels, accordion)

Port of `_render_tab_position`:
1. Blunder rate vs. position sharpness (`barChart`) — **open by
   default**, drives the scorecard headline.
2. Material structure win rate — hand-rolled `<table>` (per parent spec's
   no-generic-`<Table>` non-goal) with a structure-type radio
   (endgame/middlegame) and a grouped checkbox above it — **open by
   default**, the tab's centerpiece analysis. Coverage caption for
   `n_unanalyzed`.
3. Same-color vs. opposite-color bishop endings — 2 stat tiles (hand-
   rolled inline, same shape as `TurningPointsTab`'s "decisive moment
   profile" tile — no `MetricCard` component exists in this codebase) —
   collapsed. Renders the "not enough data" fallback when fewer than 2
   buckets are present.
4. Open, semi-open, or closed? — 2-up `barChart` comparison (win %,
   ACPL) + shared coverage caption + conditional central-tension caption
   — collapsed.
5. Symmetric vs. asymmetric pawn structure — 2-up `barChart` comparison
   — collapsed.
6. Castling configuration — 2-up `barChart` comparison — collapsed.
7. Where did the fight happen: queenside or kingside? — 2-up `barChart`
   comparison — collapsed.

Panels 4–7 all render the same "not enough data" fallback when their
source table is empty (`position_character.n_classified === 0` gates
panels 4–5; `game_side.castling_win`/`action_win` empty gates panels 6–7
independently, matching `_render_tab_position`'s per-panel `.empty`
checks).

### Game Context tab (2 panels, no accordion)

Port of `_render_tab_rhythm`: ACPL by game phase (`barChart`), then the
day/hour win-rate `heatmap` with the rating-diff disclaimer caption above
it and `rating_diff_display` wired as `hoverExtra`. Both panels always
render — no accordion, no collapse, matching Turning Points' precedent
(2 panels is not a density problem).

## Backend

### `/api/patterns/positions`

```python
@app.get("/api/patterns/positions")
def patterns_positions(structure_type: Literal["endgame", "middlegame"] = "endgame",
                        grouped: bool = False):
    def compute():
        sqlite_conn, duck_conn = get_db_connections()
        sharpness_df = data.get_sharpness_blunder_correlation(duck_conn)
        if grouped:
            structure_df = data.get_material_structure_bucket_table(sqlite_conn, structure_type)
            label_header, label_col = "Category", "bucket"
        else:
            structure_df = data.get_material_structure_table(sqlite_conn, structure_type)
            label_header, label_col = "Position Type", "material_sig"
        bishop_df = data.get_bishop_color_ending_performance(duck_conn, sqlite_conn)
        pc = data.get_position_character_performance(duck_conn)
        gs = data.get_game_side_performance(duck_conn)
        ...
    return _patterns_positions_cache[(structure_type, grouped)].get(compute)
```

Response:

```python
{
  "sharpness": [{"bucket": str, "n_moves": int, "acpl": float, "blunder_rate": float}, ...],
  "material_structure": {
    "rows": [{"label": str, "n_games": int, "win_pct": float, "draw_pct": float,
               "loss_pct": float, "acpl": float | None, "n_analyzed": int}, ...],
    "label_header": "Position Type" | "Category",
    "n_unanalyzed": int,
  },
  "bishop_endings": [{"bucket": str, "n_moves": int, "acpl": float}, ...],   # [] if <2 buckets
  "position_character": {
    "bucket_win": [{"bucket": str, "n_games": int, "win_pct": float}, ...],
    "bucket_acpl": [{"bucket": str, "n_games": int, "n_moves": int,
                       "acpl": float, "blunder_rate": float}, ...],
    "symmetric_win": [{"symmetry_label": str, "n_games": int, "win_pct": float}, ...],
    "symmetric_acpl": [{"symmetry_label": str, "n_games": int, "n_moves": int,
                          "acpl": float, "blunder_rate": float}, ...],
    "central_tension_pct": float | None,
    "n_classified": int,
    "n_total_games": int,
  },
  "game_side": {
    "castling_win": [{"castling_config": str, "n_games": int, "win_pct": float}, ...],
    "castling_acpl": [...],
    "action_win": [{"action_side": str, "n_games": int, "win_pct": float}, ...],
    "action_acpl": [...],
  },
}
```

Every list is `.to_dict(orient="records")` of the existing DataFrames
verbatim, except `material_structure.rows` (column renamed to the
unified `label` key and `material_sig_str`-formatted when `grouped` is
`False`) and `n_unanalyzed` (`int((structure_df.n_analyzed == 0).sum())`,
computed once server-side instead of per-render client-side).

New cache:

```python
_patterns_positions_cache = {
    (st, gr): _TTLCache(60)
    for st in ("endgame", "middlegame") for gr in (False, True)
}
```

added to `reset_caches()` via `for c in _patterns_positions_cache.values(): c.reset()`.

### `/api/patterns/game-context`

```python
@app.get("/api/patterns/game-context")
def patterns_game_context():
    def compute():
        sqlite_conn, duck_conn = get_db_connections()
        phase_df = data.get_phase_accuracy(sqlite_conn)
        win_pivot, rating_pivot = data.get_day_hour_heatmap(duck_conn)
        cfg = get_config()
        ...
    return _patterns_game_context_cache.get(compute)
```

Response:

```python
{
  "phase_accuracy": [{"phase": str, "n_games": int, "n_moves": int,
                        "acpl": float, "blunder_rate": float}, ...],
  "day_hour_heatmap": {
    "cells": [{"day": str, "hour_local": int, "win_pct": float,
                "rating_diff_display": str}, ...],
    "utc_offset_hours": int,
  },
}
```

`day` is already `Mon`..`Sun` (day_labels applied server-side, same
mapping `_render_tab_rhythm` uses today); `rating_diff_display` is
pre-formatted `f"{v:+.0f}"` or `"--"` for NaN, matching the existing
Streamlit caption convention. `hour_local` stays numeric (0–23) — the
existing `heatmap()` primitive doesn't require string axis values,
confirmed by its slice-3 square-blunder usage where `rank` is also
numeric.

New cache: `_patterns_game_context_cache = _TTLCache(60)`.

### Scorecard cards

`_positions_tendency_card(duck_conn)` — same worst-vs-best-bucket
extraction as `_clock_time_tendency_card`, over
`get_sharpness_blunder_correlation`'s `[bucket, n_moves, acpl,
blunder_rate]` result (identical shape to time-pressure's, so this is a
near-literal copy of that function with a different data call and
label text):

```python
{"tab_id": "positions", "label": "Positions",
 "headline": f"Blunder rate peaks at {worst.blunder_rate:.1f}% in \"{worst.bucket}\" positions",
 "detail": f"vs. {best.blunder_rate:.1f}% in \"{best.bucket}\" positions"}
```

`_game_context_tendency_card(duck_conn)` — worst-vs-best *phase* by
`acpl` (the phase-accuracy panel's own axis, not blunder rate) over
`get_phase_accuracy`'s 3-row result. No confidence-tier gate (only 3
phases; every phase with any analyzed moves qualifies) — returns `None`
only if `get_phase_accuracy` returns an empty frame (zero analyzed player
moves total):

```python
{"tab_id": "game-context", "label": "Game Context",
 "headline": f"ACPL is highest in the {worst.phase}, at {worst.acpl:.0f}",
 "detail": f"vs. {best.acpl:.0f} in the {best.phase}"}
```

`patterns_summary()`'s `cards` list grows from 3 entries to 5, still
filtered for `None`.

## Frontend

### `usePatternsPositions(structureType, grouped)` / `PositionsTab.tsx`

Hook takes both params, refetches when either changes (query params, not
client re-filtering — matches parent spec decision 6 and slice 3's
`viewBy` precedent). Param state lives in `PositionsTab`, not lifted to
`PatternsPage`.

Component: `Accordion` with panels 1–2 open by default, 3–7 collapsed.

- Panel 1: `barChart` on `sharpness`.
- Panel 2: structure-type radio + grouped checkbox (drive the hook's
  params), then a hand-rolled `<table>` over `material_structure.rows`
  keyed by the unified `label` field, `label_header` as the first column
  header, `acpl` rendered as `"--"` when `null`, plus the `n_unanalyzed`
  caption when nonzero.
- Panel 3: if `bishop_endings.length < 2`, the established "not enough
  data" inline fallback; else 2 stat tiles (opposite/same-color ACPL +
  move count) + the fixed "no meaningful win/draw difference" caption
  (static text, ported verbatim — it's not derived from the response).
- Panel 4: if `position_character.n_classified === 0`, fallback; else
  2-up `barChart` (`bucket_win`, `bucket_acpl`) + shared coverage caption
  helper + conditional central-tension caption.
- Panel 5: same `n_classified === 0` gate; 2-up `barChart`
  (`symmetric_win`, `symmetric_acpl`) + coverage caption.
- Panel 6: if `game_side.castling_win.length === 0`, fallback; else 2-up
  `barChart` (`castling_win`, `castling_acpl`) + coverage caption.
- Panel 7: if `game_side.action_win.length === 0`, fallback; else 2-up
  `barChart` (`action_win`, `action_acpl`) + coverage caption.

A small local `coverageCaption(winRows, acplRows, keyField)` helper
(ported from `_coverage_caption`'s string-building, pure presentation
logic) is shared by panels 4–7 rather than duplicated four times.

### `usePatternsGameContext` / `GameContextTab.tsx`

Hook: argument-less, identical shape to `usePatternsTurningPoints`.
Component: no `Accordion` — `barChart` on `phase_accuracy`, then the
rating-diff disclaimer caption, then `heatmap` on `day_hour_heatmap.cells`
(`x: hour_local, y: day`) with `hoverExtra` from `rating_diff_display`.

### `PatternsPage.tsx`

Grows from 3 tabs to 5: `positions` and `game-context` entries added.
Lazy-mount behavior unchanged.

## Testing

Same recipe as every prior slice:
- `test_api_patterns.py`: both new endpoints; Positions across all 4
  `structure_type`×`grouped` combos plus empty-DB cases for each
  sub-result (bishop endings <2 buckets, position-character
  n_classified=0, game-side empty); `patterns_summary()`'s card
  count/order with all 5 cards present.
- `usePatternsPositions.test.ts` (loading → success/error, mocked
  `fetch`, param-change triggering a refetch with both query params),
  `usePatternsGameContext.test.ts` (loading → success/error).
- `PositionsTab.test.tsx` (mocked hook data; each panel's "not enough
  data" fallback exercised independently, table renders the unified
  `label` column for both `grouped` values), `GameContextTab.test.tsx`
  (mocked hook data; both panels always render, `hoverExtra` wired
  through to the heatmap trace).
- `PatternsPage.test.tsx`: updated for 5 tabs and 5 scorecard cards, each
  card's click activating the right tab.
- Live verification via the `verify` skill against the real dev
  `chess.db`, after both tabs are wired in — in particular confirming
  the material-structure table's `n_unanalyzed` caption and the bishop-
  endings/position-character/game-side empty-state paths against real
  coverage numbers (185/32,295 analyzed games, per slice 1's live-
  verification note), not assumed from row counts alone.

## Non-goals

- Any change to `dashboard/patterns_view.py` or existing
  `dashboard/data/patterns.py` functions — this slice adds zero new data-
  layer functions (unlike slices 2+3's `get_decisive_moments_breakdown`),
  since every needed query already exists and returns exactly the shape
  needed.
- New backend analysis beyond what `patterns.py` already computes.
- A generic `<Table>` component (parent spec non-goal, still out of
  scope) — Positions' material-structure table is hand-rolled, matching
  `OpeningsTableSection`/`NemesisTable`/`GameExplorerTable`'s existing
  convention.
- `Accordion` open/close persistence across page revisits (parent spec
  open item, still unresolved — default to no persistence).
- Porting `chess_display.material_sig_str` to TypeScript — stays
  Python-only, called server-side per key decision 2.

## Open items for the implementation plan to resolve

- Confirm live, on the real dev DB, that `bishop_endings`,
  `position_character`, and `game_side` all clear their respective
  "enough data" gates (2+ bishop-ending buckets; `n_classified > 0`;
  non-empty castling/action tables) — slice 1's live-verification note
  already established the DB has 32,295 games with only 185 analyzed, so
  ACPL-dependent panels (bishop endings, the ACPL half of position-
  character/game-side) may show thinner data than the win/draw/loss half,
  which needs no analysis pass at all. Resolve by checking actual
  response payloads during live verification, not by assuming from row
  counts.
- Whether the material-structure table's `acpl: null` cells need any
  visual treatment beyond the plain `"--"` text Streamlit uses (e.g. a
  disabled/muted style) — resolve during live-verification if the plain
  text reads ambiguously against the hand-rolled `<table>`'s other
  columns.
