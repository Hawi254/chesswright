# Patterns & Tendencies — Slices 6+7 (Comparisons, Playing Sessions) — Design

Status: pending user review
Branch: worktree-frontend-spike
Parent spec: `docs/superpowers/specs/2026-07-14-patterns-tendencies-page-design.md`
  (page-wide architecture, IA, and the original 7-slice roadmap — this doc
  only covers what's specific to slices 6 and 7)
Prior slice spec: `docs/superpowers/specs/2026-07-15-patterns-tendencies-
  slice4-5-positions-game-context-design.md` (Positions + Game Context,
  shipped 2026-07-15 — established the nested-hand-rolled-table and
  client-side-presentation-helper precedents this spec reuses)

## Context

Slices 1–5 (Scorecard + Clock & Time; Turning Points; Piece Handling;
Positions; Game Context) have shipped — 5 of 7 tabs done, per
`docs/frontend_migration_status.md`. This spec covers the last two —
**Comparisons** (originally slice 6) and **Playing Sessions** (originally
slice 7) — combined into one implementation unit, the same reasoning
slices 2+3 and 4+5 were combined on: both tabs have zero cross-tab code
dependency (confirmed in the parent spec), and every chart/UI primitive
either tab needs (`overlayBarChart`, `Accordion`, hand-rolled tables, the
inline stat-tile shell) already exists from slices 1–5 — no new
infrastructure is introduced by this slice.

The Streamlit source for both tabs (`dashboard/patterns_view.py`'s
`_render_tab_comparisons` at line 319 and `_render_tab_sessions` at line
522, plus `dashboard/data/patterns.py`) is reference-only, per the
standing "Streamlit is reference not blueprint" directive. Neither
`patterns_view.py` nor `dashboard/data/patterns.py` is modified by this
work.

**Correction to the parent spec:** its page-structure diagram estimates
Playing Sessions at "6 panels." Reading `_render_tab_sessions` directly
shows **9** real UI panels — two of Streamlit's `st.expander` blocks
("All sessions", "Named tournaments & arenas") are top-level siblings to
the bordered containers in that function, not nested inside one, so each
becomes its own accordion item rather than a reveal nested in another
panel. This is the same kind of correction the slice 4+5 spec made for
Positions (6→7). Comparisons' panel count checks out at 6 as the parent
spec estimated.

## Key decisions

1. **Comparisons' endpoint returns every query's DataFrame verbatim, with
   zero server-side reshaping.** The underdog-vs-favorite (and win/loss,
   white/black) split, the "opening family present in both compared clock
   buckets" intersection, and the even-bucket weighted-average caption are
   all pure client-side array filtering/arithmetic with no chess-domain
   dependency — same reasoning as `coverageCaption` (slice 4+5's decision
   4). Small local helpers in `ComparisonsTab.tsx`, not new response
   fields.
2. **One new-but-tiny pattern: a nested `<details>` reveal inside an
   accordion panel.** Comparisons' "Openings: underdog vs. favorite win
   rate" panel has a Streamlit `st.expander` nested *inside* its own
   `st.container(border=True)` block (unlike Playing Sessions' two
   sibling expanders, see the correction above) — ports as a plain native
   `<details>` disclosure inside that one `AccordionItem`'s content, not a
   second top-level accordion item. No new component: `<details>` is
   dependency-free, matching `Accordion`'s own no-animation-library
   stance (parent spec's `components/ui/accordion.tsx` note).
3. **No new chart primitives.** Comparisons is fully served by
   `overlayBarChart` (built in the parent spec's primitive list, unused by
   any slice until now — 5 of its 6 panels are two-series overlays) plus
   one 3-stat-tile panel. Playing Sessions is fully served by `barChart`
   (3 panels) and `lineChart` (2 panels), plus 2 hand-rolled `<table>`s and
   2 stat-tile groups reusing the inline tile shell `TurningPointsTab`'s
   "decisive moment profile" and `PositionsTab`'s bishop-endings tiles
   already established (`rounded-md border border-[var(--cw-line)]
   bg-[var(--cw-panel-2)] p-4` shell, condensed label, `text-xl` value,
   muted detail line) — still no dedicated `MetricCard` component, per the
   parent spec's non-goal.
4. **Single argument-less `_TTLCache(60)` per endpoint**, not a
   dict-of-caches — both tabs take zero query params (unlike Positions/
   Pieces' toggles), same as Clock & Time / Turning Points / Game
   Context's caches.
5. **`get_openings_by_rating_bucket` and `get_clock_pressure_by_opening`
   are called with their default `top_n`/config-driven parameters** —
   Comparisons introduces no new query params on its endpoint, matching
   decision 6 of the parent spec (only Positions'
   `structure_type`/`grouped` and Pieces' `view_by` take query params on
   this whole page).
6. **Playing Sessions gets one full-tab empty state**, ported directly
   from `_render_tab_sessions`'s own early return (`if df.empty: st.info
   (...); return`) — if `session_rollup` comes back empty, `SessionsTab`
   renders the empty-state message and nothing else, not an accordion
   with 9 individually-empty panels.

## Scope

### Comparisons tab (6 panels, accordion, panels 1–2 open by default)

Port of `_render_tab_comparisons`:

1. **Favorite vs. underdog: overall record** — **open by default**, drives
   the scorecard headline. 3 stat tiles (underdog/even/favorite win %,
   each with an ACPL caption line, `"--"` text when that bucket has no
   analyzed games) + a shared coverage caption (reusing the
   `coverageCaption` helper shape from slice 4+5, keyed on `bucket`).
   Renders "no games" text in place of a tile for any bucket with zero
   rows, matching `_render_tab_comparisons`' per-column check.
2. **Clock pressure: underdog vs. favorite** — **open by default**. 2×
   `overlayBarChart` (ACPL, blunder rate; series = underdog/favorite rows
   split from `clock_pressure_by_rating_bucket`) + an even-strength
   weighted-average caption (`weightedAverage` helper over the `even`
   rows).
3. **Openings: underdog vs. favorite win rate** — collapsed. 1×
   `overlayBarChart` (win %; series = underdog/favorite rows split from
   `openings_by_rating_bucket`) + nested `<details>` ("See all three
   buckets, including even-strength games") containing a hand-rolled
   `<table>` over the full, unsplit response (all 3 buckets). Renders the
   established "not enough data" fallback when the underdog/favorite
   subset is empty.
4. **Clock pressure: wins vs. losses** — collapsed. 2× `overlayBarChart`
   (ACPL, blunder rate; series = win/loss rows split from
   `clock_pressure_by_outcome`).
5. **Clock pressure: as White vs. as Black** — collapsed. 2×
   `overlayBarChart` (ACPL, blunder rate; series = white/black rows split
   from `clock_pressure_by_color`).
6. **Openings: accuracy under time pressure** — collapsed. 1×
   `overlayBarChart` (ACPL; series = "critical (<5%)"/"plenty (60-100%)"
   rows from `clock_pressure_by_opening`, restricted client-side to
   opening families present in *both* buckets via the `commonFamilies`
   helper). Renders the "not enough data" fallback when the intersection
   is empty — this is the panel slice 4+5's own live-verification note
   flagged as the most likely to be thin, given the DB's analyzed-move
   coverage.

### Playing Sessions tab (9 panels, accordion, panels 1–2 open by default)

Port of `_render_tab_sessions`. Full-tab empty state (see key decision 6)
gates everything below it.

1. **Session summary** — **open by default**. 3 stat tiles, all computed
   client-side from `session_rollup`: total session count, mean
   `n_games` per session, and the games-weighted overall win %
   (`weightedAverage`-style reduction, mirrors `_render_tab_sessions`'
   own inline `df.n_games.mean()` / weighted-sum computation).
2. **Win rate over time** — **open by default**. `lineChart` on the most
   recent 60 sessions (`session_rollup.slice(-60)`, computed client-side)
   + a "Showing the most recent 60 of N sessions" caption when capped.
3. **Games per session** — collapsed. `barChart`, same 60-session cap
   (shared `recentSessions` slice from panel 2, not recomputed).
4. **ACPL trend across sessions** — collapsed. `lineChart` on the
   ACPL-not-null subset of the capped 60 + a coverage caption (hand-
   written, ported directly from `_render_tab_sessions`' own inline
   string — doesn't fit the shared `coverageCaption` helper's win/ACPL-pair
   shape, same reasoning the Streamlit source itself gives for not reusing
   `_coverage_caption` here).
5. **All sessions** — collapsed. Hand-rolled `<table>` over the full,
   uncapped `session_rollup`, `acpl` rendered as `"--"` when `null`.
6. **Performance after a win vs. after a loss** — collapsed. `barChart`
   on `prior_outcome` (`bucket`/`acpl`), drives the scorecard headline.
7. **Performance by position within a session** — collapsed. `barChart`
   on `session_position` (`position`/`acpl`).
8. **Casual vs. tournament & arena play** — collapsed. 2 dual-stat-tile
   groups (one per `event_type` row: win % tile + ACPL tile, `"--"` when
   `acpl` is `null`) + a per-category caption (`n_games`, `draw_pct`).
   Renders the established "not enough data" fallback when `event_type`
   is empty.
9. **Named tournaments & arenas** — collapsed. Hand-rolled `<table>` over
   `event_name_breakdown` (server already applies the `min_games` gate),
   `acpl` rendered as `"--"` when `null`, a caption stating the row count.
   Renders the "not enough data" fallback when empty.

## Backend

### `/api/patterns/comparisons`

```python
@app.get("/api/patterns/comparisons")
def patterns_comparisons():
    def compute():
        _, duck_conn = get_db_connections()
        win_df, acpl_df = data.get_favorite_underdog_performance(duck_conn)
        return _json_safe({
            "favorite_underdog": {
                "win": win_df.to_dict(orient="records"),
                "acpl": acpl_df.to_dict(orient="records"),
            },
            "clock_pressure_by_rating_bucket":
                data.get_clock_pressure_by_rating_bucket(duck_conn).to_dict(orient="records"),
            "openings_by_rating_bucket":
                data.get_openings_by_rating_bucket(duck_conn).to_dict(orient="records"),
            "clock_pressure_by_outcome":
                data.get_clock_pressure_by_outcome(duck_conn).to_dict(orient="records"),
            "clock_pressure_by_color":
                data.get_clock_pressure_by_color(duck_conn).to_dict(orient="records"),
            "clock_pressure_by_opening":
                data.get_clock_pressure_by_opening(duck_conn).to_dict(orient="records"),
        })
    return _patterns_comparisons_cache.get(compute)
```

Response:

```python
{
  "favorite_underdog": {
    "win": [{"bucket": str, "n_games": int, "win_pct": float}, ...],   # bucket in underdog/even/favorite
    "acpl": [{"bucket": str, "n_games": int, "n_moves": int, "acpl": float}, ...],
  },
  "clock_pressure_by_rating_bucket": [
    {"rating_bucket": str, "time_bucket": str, "n_moves": int, "acpl": float, "blunder_rate": float}, ...
  ],
  "openings_by_rating_bucket": [
    {"rating_bucket": str, "opening_family": str, "n_games": int, "win_pct": float}, ...
  ],
  "clock_pressure_by_outcome": [
    {"outcome": str, "time_bucket": str, "n_moves": int, "acpl": float, "blunder_rate": float}, ...
  ],
  "clock_pressure_by_color": [
    {"color": str, "time_bucket": str, "n_moves": int, "acpl": float, "blunder_rate": float}, ...
  ],
  "clock_pressure_by_opening": [
    {"opening_family": str, "time_bucket": str, "n_moves": int, "acpl": float, "blunder_rate": float}, ...
  ],
}
```

Every field is `.to_dict(orient="records")` of the existing DataFrame
verbatim, including `favorite_underdog`, where `win`/`acpl` are kept as
two separate lists (not merged) — matches how `_render_tab_comparisons`
itself keeps `win_df`/`acpl_df` as two frames and looks up `acpl` per
bucket via a dict, and matches decision 1's "zero server-side reshaping"
rule.

New cache: `_patterns_comparisons_cache = _TTLCache(60)`.

### `/api/patterns/sessions`

```python
@app.get("/api/patterns/sessions")
def patterns_sessions():
    def compute():
        sqlite_conn, duck_conn = get_db_connections()
        return _json_safe({
            "session_rollup": data.get_session_rollup(sqlite_conn).to_dict(orient="records"),
            "prior_outcome": data.get_prior_outcome_performance(sqlite_conn).to_dict(orient="records"),
            "session_position": data.get_session_position_performance(sqlite_conn).to_dict(orient="records"),
            "event_type": data.get_event_type_performance(duck_conn).to_dict(orient="records"),
            "event_name_breakdown": data.get_event_name_breakdown(duck_conn).to_dict(orient="records"),
        })
    return _patterns_sessions_cache.get(compute)
```

Response:

```python
{
  "session_rollup": [
    {"session_start": str, "session_end": str, "n_games": int, "win_pct": float,
     "draw_pct": float, "loss_pct": float, "acpl": float | None, "n_analyzed": int}, ...
  ],
  "prior_outcome": [
    {"bucket": str, "n_games": int, "n_moves": int, "acpl": float, "blunder_rate": float}, ...
  ],  # bucket in first_game_of_session / after a win / after a loss
  "session_position": [
    {"position": str, "n_games": int, "n_moves": int, "acpl": float, "blunder_rate": float}, ...
  ],
  "event_type": [
    {"category": str, "n_games": int, "win_pct": float, "draw_pct": float,
     "loss_pct": float, "acpl": float | None, "n_analyzed": int}, ...
  ],  # exactly 2 rows: Casual, Tournament / Arena
  "event_name_breakdown": [
    {"event": str, "n_games": int, "win_pct": float, "draw_pct": float,
     "loss_pct": float, "acpl": float | None, "n_analyzed": int}, ...
  ],  # already min_games-filtered server-side, sorted by n_games desc
}
```

`session_start`/`session_end` serialize as ISO datetime strings via
`_json_safe` (same treatment every other timestamp column on this page
already gets — no special-casing needed here).

New cache: `_patterns_sessions_cache = _TTLCache(60)`.

### Scorecard cards

```python
def _comparisons_tendency_card(duck_conn):
    """Underdog-vs-favorite win-rate gap, from the tab's own headline
    panel (get_favorite_underdog_performance's win_df) -- the single most
    legible number this tab has, since every other panel is itself a
    comparison rather than a single worst-vs-best bucket. Returns None if
    either the underdog or favorite bucket has zero games."""
    win_df, _ = data.get_favorite_underdog_performance(duck_conn)
    underdog = win_df[win_df.bucket == "underdog"]
    favorite = win_df[win_df.bucket == "favorite"]
    if underdog.empty or favorite.empty:
        return None
    u, f = underdog.iloc[0], favorite.iloc[0]
    return {"tab_id": "comparisons", "label": "Comparisons",
            "headline": f"Win rate as underdog: {u.win_pct:.1f}%",
            "detail": f"vs. {f.win_pct:.1f}% as favorite"}


def _sessions_tendency_card(duck_conn):
    """Worst-vs-best ACPL bucket from get_prior_outcome_performance --
    same worst-vs-best-bucket extraction shape as _clock_time_tendency_
    card, gated the same way (confidence_tier over n_moves). Uses
    get_db_connections() for sqlite_conn directly, same reasoning
    _game_context_tendency_card already documents for this pattern.
    Returns None if fewer than 2 buckets clear the confidence gate."""
    sqlite_conn, _ = get_db_connections()
    df = data.get_prior_outcome_performance(sqlite_conn)
    qualifying = df[df.n_moves.map(
        lambda n: confidence_tier(n, BUCKET_MOVES_THRESHOLDS) != "insufficient")]
    if len(qualifying) < 2:
        return None
    worst = qualifying.loc[qualifying.acpl.idxmax()]
    best = qualifying.loc[qualifying.acpl.idxmin()]
    return {"tab_id": "sessions", "label": "Playing Sessions",
            "headline": f"ACPL is highest {worst.bucket}, at {worst.acpl:.0f}",
            "detail": f"vs. {best.acpl:.0f} {best.bucket}"}
```

`patterns_summary()`'s `cards` list grows from 5 entries to **7** — the
full, final set for this page.

## Frontend

### `usePatternsComparisons()` / `ComparisonsTab.tsx`

Hook: argument-less, identical shape to `usePatternsTurningPoints`/
`usePatternsGameContext` (loading → success/error, no params, no
refetch triggers).

Local helpers (module-scope in `ComparisonsTab.tsx`, all pure, no chess-
domain dependency):

- `splitBy<T extends Record<string, unknown>>(rows: T[], key: keyof T,
  value: string): T[]` — generic filter, replaces the 4 separate
  `df[df.x == y]` call sites in `_render_tab_comparisons` (rating_bucket,
  outcome, color, time_bucket).
- `weightedAverage(rows, valueCol, weightCol): number | null` — powers
  the even-strength caption in panel 2.
- `commonFamilies<T>(a: T[], b: T[], key: keyof T): Set<string>` —
  intersection of `opening_family` values present in both the critical
  and plenty-clock subsets for panel 6.

Component: `Accordion` with panels 1–2 (`favorite-underdog`,
`clock-pressure-rating`) open by default, 3–6 collapsed. Each overlay
panel builds its two `OverlaySeries` inputs via `splitBy` immediately
before calling `overlayBarChart`, matching `PositionsTab`'s existing
"filter, then chart" inline style rather than pre-computing derived state.

### `usePatternsSessions()` / `SessionsTab.tsx`

Hook: argument-less, same shape.

Component: `if (data.session_rollup.length === 0) return <EmptyState/>`
before rendering anything else (key decision 6). Otherwise `Accordion`
with panels 1–2 (`summary`, `win-rate-trend`) open by default, 3–9
collapsed. `recentSessions = data.session_rollup.slice(-60)` computed
once at the top of the component, shared by panels 2 and 3 (not
recomputed per panel).

### `PatternsPage.tsx`

Grows from 5 tabs to **7** — the full, final tab list for this page:
`comparisons` and `sessions` entries added. Lazy-mount behavior
unchanged.

## Testing

Same recipe as every prior slice:

- `test_api_patterns.py`: both new endpoints, including the empty-
  `session_rollup` full-tab-empty case, the empty-underdog/favorite-
  subset case (panel 1/3), and the empty-common-families case (panel 6);
  `patterns_summary()`'s card count/order with all 7 cards present, plus
  each new card's own `None`-return path.
- `usePatternsComparisons.test.ts` / `usePatternsSessions.test.ts`
  (loading → success/error, mocked `fetch`, argument-less).
- `ComparisonsTab.test.tsx` (mocked hook data; each panel's "not enough
  data" fallback exercised independently; the nested `<details>` reveal
  renders the full 3-bucket table when opened), `SessionsTab.test.tsx`
  (mocked hook data; full-tab empty state when `session_rollup` is empty;
  the 60-session cap and its caption; each panel's independent empty
  fallback).
- `PatternsPage.test.tsx`: updated for 7 tabs and 7 scorecard cards, each
  card's click activating the right tab.
- Live verification via the `verify` skill against the real dev
  `chess.db`, checking in particular: whether the "critical vs. plenty
  clock" opening-family intersection (Comparisons panel 6) and the
  `min_games`-gated named-tournaments table (Sessions panel 9) return any
  rows at all, given the DB's thin analyzed-move coverage (185/32,295
  games, per slice 1's live-verification note) — resolve by checking
  actual response payloads, not assumed from row counts.

## Non-goals

- Any change to `dashboard/patterns_view.py` or
  `dashboard/data/patterns.py` — this slice adds zero new data-layer
  functions, since every needed query already exists and returns exactly
  the shape needed.
- New backend analysis beyond what `patterns.py` already computes.
- A generic `<Table>` component (parent spec non-goal, still out of
  scope) — both of this slice's hand-rolled tables (All sessions, Named
  tournaments & arenas) follow the same per-component convention as
  `PositionsTab`'s material-structure table.
- New chart primitives — `overlayBarChart`, `barChart`, and `lineChart`
  cover every chart both tabs need.
- `Accordion` open/close persistence across page revisits (parent spec
  open item, still unresolved — default to no persistence, consistent
  with every prior slice).

## Open items for the implementation plan to resolve

- Confirm live, on the real dev DB, whether Comparisons panel 6
  (critical-vs-plenty clock openings) and Sessions panel 9 (named
  tournaments & arenas) clear their respective "enough data" gates —
  both are flagged above as the most likely of this slice's panels to be
  thin, given the DB's analyzed-move coverage and the tournament-naming
  `min_games` floor. Resolve by inspecting actual response payloads
  during live verification.
- Whether the nested `<details>` reveal (Comparisons panel 3) needs any
  visual styling beyond the browser-default disclosure triangle to read
  well against this page's existing panel chrome — resolve during
  live-verification if the plain element looks out of place.
- **This is the last slice on the roadmap.** Once shipped and live-
  verified, update `docs/frontend_migration_status.md`'s Patterns &
  Tendencies row from 🟡 to ✅ (7 of 7 tabs), and treat the parent spec's
  three remaining "Open items for each slice's implementation plan to
  resolve" (Accordion persistence, scorecard-click scroll-into-view,
  `patterns/summary`'s double-DB-hit question) as accepted-as-is for the
  page's initial release unless this slice's own live-verification pass
  surfaces a concrete reason to revisit one — not left as unresolved
  loose ends implied to block completion.
