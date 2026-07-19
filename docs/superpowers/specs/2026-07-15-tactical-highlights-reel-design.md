# Tactical Highlights Page — "Highlight Reel" Design

Status: pending user review
Branch: worktree-frontend-spike

## Context

`docs/frontend_migration_status.md` lists `tactical_highlights_view.py`
("Tactical Highlights") as ⛔ not started. Per this session's explicit
direction, this is a **fresh design**, not a port of the Streamlit
page's structure (7 stacked `st.container(border=True)` sections, each a
slider + table). The Streamlit source and `dashboard/data/tactical.py`
are read for business logic and underlying queries only, per the
standing "Streamlit is reference not blueprint" directive — the data
this page can draw on is kept, but the framing, layout, and interaction
model are designed from scratch, informed by web research on
highlight-reel UX (chess.com's brilliant-move game report, sports
highlight-reel card/carousel patterns, Spotify Wrapped's one-moment-at-
a-time storytelling) done during this session's brainstorm.

The Streamlit page's own copy already frames this material as "a
curated reel of moments most worth remembering" — this design commits
to that framing fully, rather than presenting it as 7 data tables.

## Goals

- Surface the player's most story-worthy tactical moments — brilliant
  sacrifices, clean punishing conversions of an opponent's blunder,
  best-move streaks, forced mates that slipped away, and recoveries
  from a hung piece — as a browsable reel, one moment at a time.
- Every moment must be genuinely story-worthy, not a raw diagnostic
  row: narrowing rules (below) drop the "boring half" of several
  existing queries (e.g. blown mates that didn't actually cost the
  game, hallucination blunders that just ended in a quick resignation).
- Drill through to the real game (`GameDetailPage`) from any moment.
- No new analytical/diagnostic content — that belongs on Patterns &
  Tendencies, not here.

## Data scope (from `dashboard/data/tactical.py`)

Five categories, each a narrowed view of an existing query. Two
existing query results (missed-tactical-motifs breakdown, "knight on
the rim" proverb test) are **dropped entirely** — both are analytical,
not reel material; not rebuilt anywhere in this pass.

| Category | Source | Narrowing | Magnitude field | Caption template |
|---|---|---|---|---|
| `brilliant` | `get_brilliant_candidates` | none | `material_delta` (cp given up) | "Sacrificed {material} on move {move} — it worked." |
| `puzzle_conversion` | `get_puzzle_sequences` | `is_player_move == 0` (opponent blundered, player converted) | `puzzle_sequence_length` | "{opponent} blundered on move {move} — {n} accurate replies in a row closed it out." |
| `best_move_streak` | `get_best_move_streaks` | none (keeps existing `unforced_count >= 1` floor) | `best_move_streak_length` | "Matched the engine's top move {n} times running, starting move {move}." |
| `blown_mate` | `get_blown_mates` | `outcome_for_player == 'loss'` only | `eval_mate` | "Mate in {n} was on the board at move {move} — played something else, lost anyway." |
| `great_escape` | `get_hallucination_blunders` + `get_hallucination_context`'s `resigned_quickly` flag | `resigned_quickly == False` AND `outcome_for_player` in (`win`, `draw`) | `plies_remaining` | "Hung a piece on move {move} — survived {n} more moves and {won_or_drew} anyway." |

`material_delta`/`eval_mate` render in player-facing units (material as
"a rook" / "an exchange" / centipawn value falls back to "material" if
it doesn't cleanly map to a piece name; mate as "mate in N").

## Ranking

Within a single category filter: sort by that category's own magnitude
field descending — same order the Streamlit page already uses.

Within "All": interleave by a normalized 0–1 **highlight strength**
per row, computed by scaling each category's magnitude against a fixed
per-category cap (not the observed max in this DB, so strength is
stable across accounts): `brilliant` → `material_delta / 900` (900cp ≈
a rook), `puzzle_conversion` → `puzzle_sequence_length / 10`,
`best_move_streak` → `best_move_streak_length / 12`, `blown_mate` →
`eval_mate / 10`, `great_escape` → `plies_remaining / 20` — each
clamped to `[0, 1]`. This is a heuristic for interleaving five
different units into one feed, not a scientific score — same spirit as
Game Explorer's existing `drama_score`, not held to a higher bar.

## Caps

Each category query result is capped at its existing default (top 15,
matching the Streamlit sliders' default). The "All" view shows the top
20 by strength across the combined ≤75-row pool. A category filter
shows its own full ≤15-row list, sorted by magnitude.

## Layout & interaction

- **`HighlightCategoryFilter`** — a chip row above the reel: All + the
  5 categories, each with a count badge, using the existing
  `TONE_CLASSES` chip styling from `lib/badges.ts` (same visual
  language as `CareerHighlight`'s badge chips, so this reads as the
  same product). Selecting a chip re-scopes the reel and jumps to its
  first (highest-ranked) card.
- **`HighlightReel`** — the hero: one moment at a time.
  - A static board thumbnail via the existing `Chessboard` component
    (`interactive={false}`, ~320px, resizes via its own
    `ResizeObserver` like every other usage), with an arrow drawn from
    the moment's key move (`from`/`to` resolved the same way
    `PositionInspector.tsx`'s `resolveArrow` already does — reused, not
    reimplemented).
  - The move in SAN, the category tag, the templated one-line caption
    (filled with real fields, no LLM call), the magnitude stat,
    opponent name + date, outcome.
  - "View full game →" — opens the hidden drill-through route.
  - Prev/Next buttons, left/right arrow-key navigation (matching Game
    Detail's and Openings' existing arrow-key convention), and a
    position indicator ("4 / 18") with clickable dots (the filtered
    list is always ≤20, so dots stay usable).
- **Empty states**:
  - Whole-page: zero moments across all 5 categories (new/mostly-
    unanalyzed account) → friendly message + "Go to Analysis Jobs" CTA,
    mirroring the existing motif-backfill empty state's pattern.
  - Per-category: framed positively for `blown_mate` and
    `great_escape` (zero is good news — no forced mates lost, no
    pieces hung and survived only by luck), neutrally for the other
    three.
- **Drill-through**: hidden route `tactical-highlights/:gameId` reusing
  `GameDetailPage`, matching the `game-explorer/:gameId` /
  `matchups/:gameId` precedent already in `App.tsx`. No ply-level deep
  link — consistent with every other drill-through in this app (Openings
  explicitly declined this too).

## Backend: FastAPI endpoint (`api/main.py`)

One bundled `GET /api/tactical-highlights/reel`, matching the
established "one payload per page" precedent (Analysis Jobs' status
endpoint, each Patterns tab, `/api/matchups/rating-form`).

```python
@app.get("/api/tactical-highlights/reel")
def tactical_highlights_reel():
    sqlite_conn, duck_conn = get_db_connections()
    return data.build_highlight_reel(sqlite_conn, duck_conn)
```

New data-layer function in `dashboard/data/tactical.py`:

```python
_STRENGTH_CAPS = {
    "brilliant": 900.0,           # ~ a rook, in centipawns
    "puzzle_conversion": 10.0,    # sequence length
    "best_move_streak": 12.0,     # streak length
    "blown_mate": 10.0,           # mate-in depth
    "great_escape": 20.0,         # plies survived
}


def build_highlight_reel(sqlite_conn, duck_conn, config_path=None):
    """Merges the 5 narrowed highlight queries into one ranked reel.
    Each row gets a category tag, a fen (via get_fen_at_ply), and a
    0-1 `strength` for interleaving in the 'All' view. Capped at 15
    rows per category before merge."""
    rows = []
    rows += _brilliant_rows(duck_conn)
    rows += _puzzle_conversion_rows(duck_conn)
    rows += _best_move_streak_rows(duck_conn)
    rows += _blown_mate_rows(duck_conn)
    rows += _great_escape_rows(duck_conn, config_path)

    for row in rows:
        row["fen"], row["lastmove_from"], row["lastmove_to"] = (
            _fen_and_arrow(sqlite_conn, row["game_id"], row["ply"], row["san"]))

    counts = {cat: sum(1 for r in rows if r["category"] == cat) for cat in _STRENGTH_CAPS}
    return {"moments": rows, "counts": counts}
```

Each `_<category>_rows` helper: calls the existing narrowed query
(`get_brilliant_candidates(duck_conn, top_n=15)`,
`get_puzzle_sequences(duck_conn, top_n=None).query("is_player_move == 0").head(15)`,
etc.), joins `games` for `opponent_name`/`utc_date`/`outcome_for_player`
(same join pattern `get_blown_mates` already uses), computes
`strength = min(magnitude / _STRENGTH_CAPS[category], 1.0)`, and fills
the caption template from Section "Data scope" above. Kept as separate
small helpers rather than one mega-query — each category's source
query already has different shapes (DuckDB vs. needing the context
query for `great_escape`), so a single SQL statement would fight the
existing query boundaries for no real benefit.

New tiny lookup in `dashboard/data/game_explorer.py` (next to
`get_game_detail`):

```python
def get_fen_at_ply(sqlite_conn, game_id, ply):
    """Single indexed point lookup (idx_moves_game(game_id, ply)) --
    cheaper than reconstructing the whole game via get_game_detail when
    only one position is needed."""
    row = sqlite_conn.execute(
        "SELECT fen_before FROM moves WHERE game_id=? AND ply=?",
        (game_id, ply)).fetchone()
    return row[0] if row else None
```

`_fen_and_arrow` (private helper in `tactical.py`) calls
`get_fen_at_ply` then resolves the `san` to a `from`/`to` square pair
via `python-chess`, mirroring what `resolveArrow` does client-side in
`PositionInspector.tsx` — done server-side here since the fen is
already being fetched server-side and the frontend shouldn't need
`chess.js` just to draw one arrow on a static thumbnail.

Notes:
- No caching layer — this data only changes after a new analysis batch
  finishes, and the 5 underlying queries are each already bounded
  (`top_n=15` or capped joins); a single page-load fetch is cheap
  enough as-is, matching e.g. `/api/openings/table`'s uncached style.
- `great_escape` needs `get_hallucination_context` only for its
  `resigned_quickly`-derived narrowing on the same `hangs` DataFrame
  `get_hallucination_blunders` already returns — no new query, just
  reusing the existing two-function pairing as-is.

## Frontend

### Hook

- **`useTacticalHighlightsReel()`** — single `fetch` on mount, no
  polling (matches `useOverviewData`/`useOpeningsTable`'s style, not
  `useAnalysisJobStatus`'s interval style — this data is static between
  analysis batches). Returns `{ moments, counts, loading, error }`.

### Components

- **`TacticalHighlightsPage.tsx`** — composes the hook, owns
  `activeCategory` (`'all' | Category`) and `activeIndex` state,
  derives the filtered/sorted list, renders
  `HighlightCategoryFilter` + `HighlightReel`, or the whole-page empty
  state when `moments.length === 0`.
- **`HighlightCategoryFilter.tsx`** — chip row, takes
  `counts`/`activeCategory`/`onSelect`.
- **`HighlightReel.tsx`** — the hero card: `Chessboard` thumbnail +
  caption block + prev/next + arrow-key handling (a `useEffect` keydown
  listener scoped to the component, matching Game Detail's existing
  pattern) + dot indicator. Renders the per-category empty state itself
  when the filtered list is empty but `moments` overall isn't.

### Page wiring

`PAGE_COMPONENTS['tactical-highlights'] = TacticalHighlightsPage` in
`App.tsx` (the nav entry already exists in `navConfig.ts`/
`navCandidates.ts`, currently falling back to `PageStub`). New hidden
route:

```tsx
<Route path="tactical-highlights/:gameId" element={<GameDetailPage />} />
```

## Non-goals

- Missed-tactical-motifs breakdown and the "knight on the rim" proverb
  test — dropped, not rebuilt elsewhere in this pass (they're Patterns
  & Tendencies material, out of scope here).
- The "you blundered, opponent converted" half of `get_puzzle_sequences`
  and the quick-resign half of `get_hallucination_blunders` — diagnostic,
  not reel material; still queryable via `dashboard/data/tactical.py`
  if a future diagnostic page wants them, just not surfaced here.
- Blown mates that didn't cost the game (`outcome_for_player != 'loss'`)
  — dropped per the narrowing rule above.
- Ply-level deep link into Game Detail, sharing/export of a moment, any
  Claude-generated narrative text (captions are template-filled from
  real fields only).
- Any change to `dashboard/tactical_highlights_view.py` or
  `dashboard/data/tactical.py`'s existing functions — all read-only
  inputs to this design, called as-is; only new functions are added.

## Testing

- `tests/integration/test_api_tactical_highlights.py` (new): narrowing
  correctness per category (e.g. a `puzzle_sequences` row with
  `is_player_move=1` never appears; a `blown_mates` row with
  `outcome_for_player='win'` never appears), strength clamping at 1.0
  for an out-of-range magnitude, `counts` matching `moments` length per
  category, empty-DB case (all-zero counts, empty `moments`), `fen`
  present on every row.
- `useTacticalHighlightsReel.test.ts` — success/error/loading shape.
- Component tests: `HighlightCategoryFilter.test.tsx` (selection,
  count badges), `HighlightReel.test.tsx` (prev/next, arrow-key nav,
  dot-click, per-category empty state, drill-through link target),
  `TacticalHighlightsPage.test.tsx` (composition, whole-page empty
  state, category-switch resets `activeIndex`).
- Live verification (`verify` skill): confirm real brilliancies/
  streaks/etc. from the dev `chess.db` render with correct board
  thumbnails and arrows, confirm category filtering and counts match
  the underlying data, confirm drill-through opens the right game.

## Open items for the implementation plan to resolve

- Exact piece-name mapping for `material_delta` → "a rook" / "an
  exchange" / etc. in captions (e.g. a small cp-value → piece-name
  table) — needs a concrete threshold table, decide at implementation
  time by checking what values `material_delta` actually takes in the
  real dev DB.
- Whether `great_escape`'s "won" vs. "drew" wording in the caption
  needs its own template branch or can stay as one generic
  "{won_or_drew}" — trivial, resolve while writing
  `_great_escape_rows`.
- Confirm `python-chess`'s SAN→square resolution needs the exact same
  disambiguation handling `resolveArrow` uses client-side (promotion
  notation, castling) — verify against a few real `great_escape`/
  `brilliant` rows rather than assuming parity.
