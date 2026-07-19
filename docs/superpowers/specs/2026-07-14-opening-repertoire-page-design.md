# Openings & Repertoire Page — Design

Status: pending user review
Branch: worktree-frontend-spike

## Context

`docs/frontend_migration_status.md` lists `openings_view.py` ("Openings &
Repertoire") as ⛔ not started — 18 of 21 Streamlit pages are still
unported. This spec covers porting it in full as a single "production
grade" page (not a trimmed slice), following the `port-view-slice`
skill's core rule: the FastAPI layer adds **zero new business logic**,
every endpoint is a thin wrapper over an existing `dashboard/data/*.py`
function.

The Streamlit source (`dashboard/openings_view.py`, 491 lines) is a
source for business logic and requirements only, per the standing
"Streamlit is reference not blueprint" directive — its
`st.session_state`/`@st.fragment`/`st.rerun(scope="fragment")` control
flow does not carry over, and per this session's explicit direction its
*interaction and visual design* are also not copied 1:1: wherever
React's component model enables a real improvement over Streamlit's
widget-per-rerun constraints, this spec takes it, grounded in patterns
this codebase has already proven out (Game Detail's master-detail grid,
Game Explorer's intensity-bar convention, Game Detail's arrow-key
navigation) rather than inventing novel interactions.

The page has four independent sections, each its own `@st.fragment` in
Streamlit: **Your openings** (sortable table + Claude commentary),
**Most-repeated positions** (table + board), **Repertoire holes** (table
+ board + drill-export link), **Where does accuracy drop** (per-move CPL
chart + compare-against overlay). None of the four reads another's
filter/selection state — confirmed independent in the Streamlit source's
own comments (section 4 was deliberately decoupled from section 1's
`min_games` filter after a real coupling bug).

## Goals

- Full parity with the Streamlit page's four sections and their
  Claude-commentary / drill-down / comparison capabilities.
- Reuse already-built infrastructure instead of re-deriving it: the
  shared `Chessboard` component, `useAnalysePosition` +
  `POST /api/analyse-position` (board+eval display, live-engine
  fallback, Lichess-cloud-eval fallback — all already built for Game
  Detail), and the `_TTLCache` pattern already used for other
  expensive/argument-less endpoints.
- Apply the "don't copy Streamlit 1:1" directive concretely: one
  consistent table+detail-panel interaction across all four sections,
  not four independently-stacked widget groups.

## Key decisions (from this session's brainstorm)

1. **Tabs, not one long scrolling page.** The four sections answer four
   different questions (browse your repertoire / drill into a specific
   position / find weak spots / study one line's move-by-move accuracy)
   and two of them want a master-detail board panel that needs real
   vertical room. Tabs give each section the full viewport; only the
   active tab's hook fires (a real improvement over Streamlit, which
   effectively loaded all four fragments on first visit). Needs one new
   primitive: `components/ui/tabs.tsx`, a thin wrapper over
   `@base-ui/react/tabs` (already an installed dependency, used the same
   way `dialog.tsx` wraps `@base-ui/react/dialog` — no new external
   dependency).
2. **Row click is the selection mechanism, everywhere.** Streamlit's
   "Your openings" section has a table *and* a separate "Tell me about
   this opening" selectbox listing the same rows again; sections 2-3
   have a table plus a scroll-down-to-see-the-board step. The React
   version unifies all three into one idiom: click a table row, a detail
   panel (commentary, or the position board) appears alongside it in a
   `grid-cols-[minmax(280px,440px)_1fr]` layout — the exact grid Game
   Detail already established for its own board+content split. This
   removes the redundant selectbox in section 1 entirely.
3. **Keyboard row navigation in sections 2-3**, via Up/Down arrow keys —
   reuses the exact convention Game Detail already established for ply
   stepping, rather than inventing a new one.
4. **Visual encodings reuse Game Explorer's precedent directly**: the
   win/draw/loss triple in "Your openings" renders as one inline stacked
   bar (same `var(--cw-copper)`/width% idiom as `GameExplorerTable`'s
   `drama_score` bar) instead of three numeric columns; `hole_score` in
   "Repertoire holes" renders the same way instead of a bare number.
5. **Board arrows are resolved client-side via chess.js**, not a new
   backend field. `Chessboard` already renders `arrows` as
   `{from, to, color}`; given a `fen` and a SAN string (player's usual
   move or engine's best move), `new Chess(fen).moves({verbose: true})`
   finds the matching move's `from`/`to` in the browser. `data.py`'s
   existing `resolve_move_squares` (used elsewhere for Board Chat's
   `show_arrow` tool) stays exactly as-is and is not touched by this
   work — this is a second, independent way to get the same kind of
   answer, not a replacement for it.
6. **"Compare against" is a toggle, not an always-visible second
   selector.** Streamlit always shows a second selectbox plus, once
   chosen, two more charts stacked below the first. The React version
   shows only the single-opening chart by default; a "Compare against
   another opening" toggle reveals the second selector and both
   comparison charts. Reduces default clutter with no loss of
   capability.
7. **Drill-export is omitted entirely for this pass.** The Streamlit
   "Repertoire holes" section's "→ Export these as drill positions"
   button deep-links to Drill Export, which is itself still ⛔
   unported. Re-added as a small follow-up once Drill Export has a real
   route to link to.
8. **Global Search's opening-family deep link is out of scope.** The
   React `CommandPalette`/`navCandidates.ts` system is page-level only
   right now (`{category: 'page', title, url_path}`, no per-item
   entries) — per-opening deep-linking isn't wired up anywhere in the
   new frontend yet, not just here, so it isn't invented for this page
   in isolation.

## Backend: FastAPI endpoints (`api/main.py`)

All seven endpoints call existing `dashboard/data/openings.py` /
`dashboard/analytics.py` / `dashboard/claude_narrative.py` functions
directly — `data.get_openings_table`, `data.get_most_repeated_positions`,
`data.get_opening_ply_accuracy`, `data.get_repertoire_holes`,
`data.get_position_fen`, `data.get_cached_narrative`,
`data.save_narrative` are all already re-exported at the `dashboard.data`
package level (`dashboard/data/__init__.py`), so no new imports are
needed beyond `analytics` (not currently imported in `api/main.py`).

```python
import analytics  # new import; ensure_repeated_positions_cache / ensure_repertoire_holes_cache

_openings_table_cache = _TTLCache(60)  # add alongside the four existing _TTLCache instances;
                                        # add to reset_caches() too


@app.get("/api/openings/table")
def openings_table():
    def compute():
        sqlite_conn, duck_conn = get_db_connections()
        return data.get_openings_table(duck_conn, sqlite_conn, min_games=1).to_dict(orient="records")
    return _openings_table_cache.get(compute)


@app.get("/api/openings/{family}/{color}/narrative")
def get_opening_narrative(family: str, color: str):
    sqlite_conn, _ = get_db_connections()
    cached = data.get_cached_narrative(sqlite_conn, "opening", f"{family}|{color}")
    if cached is None:
        return {"narrative": None, "generated_at": None}
    response_text, generated_at = cached
    return {"narrative": response_text, "generated_at": generated_at}


@app.post("/api/openings/{family}/{color}/narrative/generate")
def generate_opening_narrative(family: str, color: str):
    sqlite_conn, duck_conn = get_db_connections()
    table_rows = _openings_table_cache.get(
        lambda: data.get_openings_table(duck_conn, sqlite_conn, min_games=1).to_dict(orient="records"))
    row = next((r for r in table_rows
                if r["opening_family"] == family and r["player_color"] == color), None)
    if row is None:
        raise HTTPException(status_code=404, detail="Unknown opening")
    stats = data.get_headline_stats(duck_conn, sqlite_conn)
    try:
        response_text = claude_narrative.generate_opening_commentary(
            pd.Series(row), stats["win_pct"], stats["analyzed_games"], stats["total_games"])
    except claude_narrative.MissingApiKeyError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Claude API call failed: {e}")
    data.save_narrative(sqlite_conn, "opening", f"{family}|{color}", response_text, claude_narrative.MODEL)
    return {"narrative": response_text}


@app.get("/api/openings/repeated-positions")
def repeated_positions(top_n: int = 20):
    sqlite_conn, _ = get_db_connections()
    analytics.ensure_repeated_positions_cache(sqlite_conn)
    return data.get_most_repeated_positions(sqlite_conn, top_n=top_n).to_dict(orient="records")


@app.get("/api/openings/position-fen")
def position_fen(ply: int, zobrist_hash: int):
    sqlite_conn, _ = get_db_connections()
    fen = data.get_position_fen(sqlite_conn, ply, zobrist_hash)
    if fen is None:
        raise HTTPException(status_code=404, detail="Position not found")
    return {"fen": fen}


@app.get("/api/openings/repertoire-holes")
def repertoire_holes(min_appearances: int = 5, top_n: int = 20):
    sqlite_conn, _ = get_db_connections()
    analytics.ensure_repertoire_holes_cache(sqlite_conn)
    return data.get_repertoire_holes(
        sqlite_conn, min_appearances=min_appearances, top_n=top_n).to_dict(orient="records")


@app.get("/api/openings/ply-accuracy")
def ply_accuracy(opening_family: str, player_color: str, min_appearances: int = 3):
    _, duck_conn = get_db_connections()
    return data.get_opening_ply_accuracy(
        duck_conn, opening_family, player_color, min_appearances=min_appearances).to_dict(orient="records")
```

Notes:
- The `subject_key` format (`f"{family}|{color}"`) matches
  `openings_view.py`'s own `subject_key` exactly, so narratives generated
  from either the Streamlit or React frontend against the same `chess.db`
  land in the same `narratives` row — a real convergence benefit, not
  just a coincidence to preserve.
- `ensure_repeated_positions_cache`/`ensure_repertoire_holes_cache` run
  inline in their own endpoints on every call rather than behind
  Streamlit's `session_state["openings_caches_ready"]` one-shot gate —
  both are already idempotent no-ops when nothing new has been analyzed
  since the last build, so the stateless request/response model gets
  this simplification for free.
- No endpoint for "export as drill positions" (decision 7).
- `get_headline_stats` is called directly (not behind a new `_TTLCache`)
  since it only runs on a manual "Generate commentary" click, not a
  page-load path.

## Frontend

### Hooks (`frontend/src/hooks/`)

One hook per endpoint, matching the established `loading`/`error`/data
shape with `cancelled`-on-unmount cleanup:

- `useOpeningsTable()` — `OpeningRow[]`
- `useOpeningNarrative(family, color)` — `{ narrative, generatedAt, loading, error, generating, generateError, generate() }`
- `useRepeatedPositions(topN)` — `RepeatedPositionRow[]`
- `usePositionFen(ply, zobristHash)` — `{ fen, loading, error }`, fetched
  only once a row is selected in the Repeated Positions tab
- `useRepertoireHoles(minAppearances, topN)` — `RepertoireHoleRow[]`
  (rows already carry `fen_before`, so this tab needs no separate
  position-fen lookup)
- `useOpeningPlyAccuracy(family, color, minAppearances)` — used twice per
  page (primary selection + optional compare selection)

### Shared components

- **`components/ui/tabs.tsx`** — thin wrapper over `@base-ui/react/tabs`
  (see decision 1), styled to match the existing `button.tsx`/`dialog.tsx`
  token usage.
- **`components/ui/Slider.tsx`** — range-input primitive; first page to
  need it (four sliders across the tabs: min-games, top-N ×2,
  min-appearances). Repertoire Evolution and Patterns & Tendencies will
  also want this once ported.
- **`components/PositionInspector.tsx`** — the shared board+eval panel
  used by both the Repeated Positions and Repertoire Holes tabs. Props:
  `fen: string | null`, `playerSan?: string` (gold arrow), `flip`,
  `onFlipToggle`. Internally calls `useAnalysePosition(fen)` (existing
  hook, unchanged) and renders `<Chessboard interactive={false} arrows={...} />`
  plus the eval/best-move/PV/source-caption block, ported directly from
  `_board_svg`'s and the two Streamlit sections' info-panel markdown.
  Arrows: engine's best move (green) always if `analysisStatus === 'ok'`;
  player's usual move (gold) only when `playerSan` is passed (Repertoire
  Holes only — Repeated Positions has no "usual move" concept, matching
  the Streamlit source exactly).

### Section components

- **`OpeningsTableSection.tsx`** — sortable table (click header,
  ascending/descending — new client-side logic; `st.dataframe` sorted for
  free), win/draw/loss stacked bar per row (decision 4), opening-name
  search input, min-games `Slider`. Row click sets the selected
  `(family, color)`; the right-hand detail panel shows headline
  stats for that opening plus `useOpeningNarrative`'s
  generate/regenerate button and cached commentary — ported verbatim
  from the Streamlit section's copy and gating
  (`claude_narrative.api_key_available()` → same "Add your own
  Anthropic API key..." info text). The "ACPL blank for N of M openings"
  caption is ported as-is (computed client-side from the fetched rows).
- **`RepeatedPositionsSection.tsx`** — master-detail: table (top-N
  `Slider`, Up/Down arrow-key row navigation) + `PositionInspector` on
  the right, fed via `usePositionFen` once a row is selected.
- **`RepertoireHolesSection.tsx`** — same master-detail + arrow-key nav;
  `hole_score` as an intensity bar (decision 4); "Biggest hole" summary
  caption ported; feeds `PositionInspector` directly from the row's own
  `fen_before` (no extra fetch) with `playerSan={row.most_played_san}`.
- **`PlyAccuracySection.tsx`** — opening selector + min-appearances
  `Slider` + single-opening bar chart (`lineChart`/`barChart`-style
  helper, see below) always visible; "Compare against another opening"
  toggle (decision 6) reveals a second selector plus the overlay and
  difference charts, sharing one synced hover group (Plotly's native
  same-`xaxis` hover behavior — no new plumbing).

### `lib/charts.ts` additions

Two new helpers alongside the existing single-series `lineChart`/
`barChart`, same signature shape and `THEME` token usage:
- `overlayBarChart(seriesA, seriesB, ...)` — two traces on shared axes.
- `differenceBarChart(seriesA, seriesB, ...)` — single trace of
  `seriesB - seriesA` over the intersecting `move_number` values,
  ported from `theme.render_comparison_panel(mode="difference")`'s exact
  math.

### Page composition (`OpeningsPage.tsx`)

Four `Tab.Panel`s, one per section component above, wired into `App.tsx`
via one new `PAGE_COMPONENTS` entry: `openings: OpeningsPage` (currently
falls back to `PageStub` — `navCandidates.ts` already has the
`{ title: 'Openings & Repertoire', url_path: 'openings' }` entry, no
routing changes needed beyond the lookup-table addition).

## Non-goals

- Drill-export button/route (decision 7).
- Global Search per-opening deep link (decision 8).
- Any change to `dashboard/openings_view.py` itself — left exactly as-is,
  same posture as every other slice's Streamlit source.
- Streaming or progressive rendering of the Claude commentary — matches
  every other Claude-backed feature in this codebase (blocking POST,
  FastAPI's threadpool keeps it from blocking the rest of the app).

## Testing

- `tests/integration/test_api_openings.py` (new, one file for all seven
  endpoints): `TestClient` + `migrated_db_path` fixture;
  `openings_table` cache behavior verified via `reset_caches()` between
  tests; narrative get (empty/populated) + generate (happy path, 404
  unknown opening, `MissingApiKeyError` → 503, generic exception → 502);
  repeated-positions/repertoire-holes empty-DB and populated cases;
  position-fen 404 on unknown `(ply, zobrist_hash)`; ply-accuracy
  empty/populated.
- Hook tests (`use*.test.ts` ×6): loading → success/error transitions,
  mocked `fetch`.
- Component tests: `Slider.test.tsx`, `PositionInspector.test.tsx`
  (engine-only arrows vs. engine+player arrows, `null` render with no
  `fen`), one `.test.tsx` per section component (sort toggling, search
  filtering, stacked-bar/intensity-bar rendering, arrow-key row
  navigation, compare-toggle reveal/hide), `OpeningsPage.test.tsx`
  (tab switching, lazy hook activation — a tab's hook doesn't fire until
  its `Tab.Panel` first mounts).
- Live verification (`verify` skill): both dev servers against the
  worktree's real `chess.db`; screenshot all four tabs, the commentary
  generate flow, arrow-key navigation in tabs 2-3, and the compare-toggle
  reveal in tab 4.

## Open items for the implementation plan to resolve

- Exact sort-indicator styling and default sort column/direction for
  "Your openings" (Streamlit's `st.dataframe` default sort is insertion
  order, i.e. `n` descending per `get_openings_table`'s own
  `.sort_values("n", ascending=False)` — likely the sensible React
  default too, confirm at implementation time).
- Whether `PositionInspector`'s "Flip board" toggle state should reset
  per row selection or persist across selections within a tab — decide
  by checking user expectation once the component is live, not
  speculatively now.
- Exact Base UI `Tabs` API surface (uncontrolled vs. controlled,
  `keepMounted` options for lazy-activation semantics) — resolve by
  reading `@base-ui/react/tabs`'s actual types at implementation time
  rather than assuming Radix-equivalent prop names.
