# Matchups & Opponents Page — Design

Status: pending user review
Branch: worktree-frontend-spike

## Context

`docs/frontend_migration_status.md` lists `matchups_view.py` ("Matchups &
Opponents") as ⛔ not started. This spec covers porting it in full as a
single "production grade" page, following the `port-view-slice` skill's
core rule: the FastAPI layer adds **zero new business logic**, every
endpoint is a thin wrapper over an existing `dashboard/data/matchups.py`
(and `dashboard/data/points.py`, `dashboard/claude_narrative.py`)
function.

The Streamlit source (`dashboard/matchups_view.py`, 436 lines, plus
`dashboard/data/matchups.py`, 485 lines) is a source for business logic
and requirements only, per the standing "Streamlit is reference not
blueprint" directive. Per this session's explicit direction its
*interaction and visual design* are also not copied 1:1: wherever
React's component model enables a real improvement over Streamlit's
widget-per-rerun constraints, this spec takes it, grounded in patterns
this codebase has already proven out (Openings & Repertoire's Tabs +
master-detail conventions, Game Explorer's intensity-bar idiom,
Insights' confidence-tier bar, Game Explorer's hidden drill-down route)
rather than inventing novel interactions.

The page has 7 sections. Six are simple, argument-less, independent
charts/tables (win rate vs. rating differential, color-by-rating,
giant-killing counts, collapse-cause breakdown, giant-killing rate
trend, eval-based comeback/collapse game lists). The seventh, "Nemesis
and favorite opponents," is a `@st.fragment` in Streamlit because it
alone has real interactive state: a min-games slider, four ranking
tables, a full opponent-profile deep-dive (5 more tables), Claude
commentary, and a swindle-rate caption.

## Goals

- Full parity with all 7 Streamlit sections and their
  chart/table/drill-down/Claude-commentary capabilities.
- Reuse already-built infrastructure instead of re-deriving it: the
  `Tabs` primitive, `Slider`, the `_TTLCache` pattern, the narrative
  get/generate pattern (Openings/Insights), `GameExplorerTable`'s
  intensity-bar idiom, `InsightCard`'s confidence-tier bar, the
  cmdk-based `command.tsx`, and the `game-explorer/:gameId`-style hidden
  drill-down route.
- Apply the "don't copy Streamlit 1:1" directive concretely: one
  consistent opponent-selection mechanism across all four nemesis
  tables and the full-list picker, not a redundant standalone selectbox
  duplicating rows already shown.

## Key decisions (from this session's brainstorm + web research)

1. **Two tabs: "Rating & Form" (sections 1-6) and "Named Opponents"
   (section 7).** Restores the pre-6c.4 Matchups/Opponents split at the
   UI level (the 6c.4 merge itself — one page, not two — stays; only the
   two sub-questions get separated again) while keeping the routing-level
   merge. Justified against NN/G's tabs-vs-scrolling guidance: tabs are
   appropriate specifically when users don't need simultaneous
   side-by-side viewing of both sections, which holds here — nobody
   reading giant-killing stats needs the nemesis tables visible at the
   same time. Only the active tab's hooks fire, matching Openings'
   lazy-mount behavior.
2. **No Opponent Prep deep link this pass.** Opponent Prep
   (`prep_view.py`) is itself still ⛔ unported — nothing to link to.
   Row click / picker selection only sets the opponent for the profile
   panel below. Same precedent as the Openings spec's drill-export
   omission (decision 7 there); re-added once Opponent Prep has a real
   route.
3. **Confidence-tier badges on all 4 nemesis tables.** The nemesis query
   already computes `confidence_tier` (low/medium/high, from sample
   size) but Streamlit never surfaces it, so a 17.1% score over 3 games
   and over 40 games render identically. Uncertainty-visualization
   literature specifically recommends surfacing sample-size confidence
   alongside a point estimate for exactly this reason. Implemented by
   extracting a shared `ConfidenceBadge` component out of `InsightCard`'s
   existing 3-tier width/label bar (`CONFIDENCE_WIDTH`/`CONFIDENCE_LABEL`)
   rather than duplicating those constants.
4. **Opponent selection = row-click in any of the 4 nemesis tables, plus
   a searchable fallback picker.** The 4 tables are only top-10 subsets;
   Streamlit's separate full-list selectbox covers opponents outside
   them. The W3C ARIA APG combobox pattern is the standard accessible
   idiom for exactly this "list too long to show all of, with
   type-to-filter" case — built on the existing cmdk-based `command.tsx`
   (already used by `CommandPalette`), rendered inline (no dialog), not
   a bespoke picker.
5. **Comeback/collapse game lists link to Game Detail via a new hidden
   route `matchups/:gameId`**, following the exact `game-explorer/:gameId`
   precedent already in `App.tsx` (own hidden route per source page —
   React Router's own nested-routing guidance frames this as the
   standard "drill down without losing your way" pattern).
6. **New `multiLineChart` chart helper** for the giant-killing rate
   trend (2 series: `pct_upset`, `pct_collapse`, shared x-axis and
   y-axis unit — same-axis multi-line, not dual-axis, which
   data-visualization sources specifically warn against as misleading).
   No existing helper in `lib/charts.ts` covers multi-series lines.
7. **`/api/matchups/rating-form` is one bundled endpoint, not six.**
   Deliberate deviation from Openings' one-endpoint-per-query style,
   justified because all six Rating & Form queries are always needed
   together on first mount of that tab, with no per-section filter
   state — bundling means one `_TTLCache` entry and one hook instead of
   six.
8. **Piece-name mapping/ordering (`PIECE_NAME`/`PIECE_ORDER`) is done
   server-side**, in the `rating-form` endpoint, so the frontend doesn't
   need its own copy of those two Python constants.

## Backend: FastAPI endpoints (`api/main.py`)

```python
_matchups_static_cache = _TTLCache(60)   # the 6 argument-less "Rating & Form" queries, bundled
_points_ledger_cache = _TTLCache(60)     # new; whole-DB, shared across opponents

# add both to reset_caches()

_PIECE_ORDER = ["Q", "R", "B", "N", "P", "K"]
_PIECE_NAME = {"Q": "queen", "R": "rook", "B": "bishop", "N": "knight", "P": "pawn", "K": "king"}


@app.get("/api/matchups/rating-form")
def matchups_rating_form():
    """One endpoint for all 6 argument-less Rating & Form queries -- always
    fetched together (one tab, no independent loading states), so one
    fetch + one _TTLCache entry beats six."""
    def compute():
        _, duck_conn = get_db_connections()
        reason_df, piece_df, mate_df = data.get_giant_killing_collapse_causes(duck_conn)
        piece_records = piece_df.to_dict(orient="records")
        order = {p: i for i, p in enumerate(_PIECE_ORDER)}
        piece_records.sort(key=lambda r: order.get(r["hung_piece"], len(_PIECE_ORDER)))
        for r in piece_records:
            r["piece_name"] = _PIECE_NAME.get(r["hung_piece"], r["hung_piece"]).title()
        color_perf = data.get_color_performance_by_rating(duck_conn).reset_index()
        return {
            "win_rate_by_rating_diff": data.get_win_rate_by_rating_diff(duck_conn).to_dict(orient="records"),
            "color_performance_by_rating": color_perf.to_dict(orient="records"),
            "giant_killing_counts": data.get_giant_killing_counts(duck_conn),
            "collapse_causes": {
                "reason": reason_df.to_dict(orient="records"),
                "piece": piece_records,
                "mate": mate_df.to_dict(orient="records"),
            },
            "giant_killing_rate_trend": data.get_giant_killing_rate_trend(duck_conn).to_dict(orient="records"),
            "comeback_collapse": data.get_comeback_collapse_counts(duck_conn),
        }
    return _matchups_static_cache.get(compute)


@app.get("/api/matchups/nemesis")
def matchups_nemesis(min_games: int | None = None):
    _, duck_conn = get_db_connections()
    return data.get_nemesis_opponents(duck_conn, min_games=min_games).to_dict(orient="records")


@app.get("/api/matchups/opponent-profile")
def opponent_profile(opponent_name: str):
    _, duck_conn = get_db_connections()
    profile = data.get_opponent_profile(duck_conn, opponent_name)
    return {
        "n_games": profile["n_games"],
        "openings": profile["openings"].to_dict(orient="records"),
        "position": profile["position"].to_dict(orient="records"),
        "castling": profile["castling"].to_dict(orient="records"),
        "action_side": profile["action_side"].to_dict(orient="records"),
        "clock": profile["clock"].to_dict(orient="records"),
    }


@app.get("/api/matchups/opponent-swindle-rate")
def opponent_swindle_rate(opponent_name: str):
    _, duck_conn = get_db_connections()
    ledger = _points_ledger_cache.get(
        lambda: data.classify_points_ledger(data.get_points_ledger(duck_conn)))
    return data.get_opponent_swindle_rate(ledger, opponent_name)


@app.get("/api/matchups/opponent-narrative")
def get_opponent_narrative(opponent_name: str):
    sqlite_conn, _ = get_db_connections()
    cached = data.get_cached_narrative(sqlite_conn, "opponent", opponent_name)
    if cached is None:
        return {"narrative": None, "generated_at": None}
    response_text, generated_at = cached
    return {"narrative": response_text, "generated_at": generated_at}


@app.post("/api/matchups/opponent-narrative/generate")
def generate_opponent_narrative(opponent_name: str):
    sqlite_conn, duck_conn = get_db_connections()
    nem_rows = data.get_nemesis_opponents(duck_conn, min_games=None)
    row = nem_rows.loc[nem_rows.opponent_name == opponent_name]
    if row.empty:
        raise HTTPException(status_code=404, detail="Unknown opponent")
    stats = data.get_headline_stats(duck_conn, sqlite_conn)
    try:
        response_text = claude_narrative.generate_opponent_commentary(
            row.iloc[0], stats["win_pct"], stats["analyzed_games"], stats["total_games"])
    except claude_narrative.MissingApiKeyError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Claude API call failed: {e}")
    data.save_narrative(sqlite_conn, "opponent", opponent_name, response_text, claude_narrative.MODEL)
    return {"narrative": response_text}
```

Notes:
- `min_games=None` on `/api/matchups/nemesis` reproduces
  `get_nemesis_opponents`'s own `config["analytics"]["min_sample_size"]`
  fallback — the frontend only passes an explicit value once the user
  moves the slider.
- `opponent-profile` and `opponent-swindle-rate` are uncached
  (per-opponent, argument-varying), matching
  `/api/openings/position-fen`'s precedent — `get_opponent_profile`'s own
  docstring notes its per-opponent queries are cheap.
- `subject_key` for narratives is the bare `opponent_name`, matching
  `matchups_view.py`'s own `data.get_cached_narrative(sqlite_conn,
  "opponent", chosen_name)` call exactly, so narratives generated from
  either frontend against the same `chess.db` land in the same
  `narratives` row.
- `generate_opponent_narrative` re-derives the row server-side
  (uncached, whole-DB `min_games=None`) rather than trusting a
  client-supplied row, mirroring Openings' generate endpoint.
- `chesswright_pro/tournament_prep.py`'s own use of the Streamlit-side
  `cached_opponent_profile` wrapper is untouched — `opponent-profile`
  calls `data.get_opponent_profile` directly, a separate code path.

## Frontend

### Shared refactor

Extract `components/ConfidenceBadge.tsx` (`{ tier: 'low' | 'medium' |
'high', sampleSize?: number }` → the tier bar + label) out of
`InsightCard.tsx`'s existing inline `CONFIDENCE_WIDTH`/`CONFIDENCE_LABEL`
constants and markup. Both `InsightCard` and the new `NemesisTable`
consume it.

### Hooks (`frontend/src/hooks/`)

- `useMatchupsRatingForm()` — one fetch, the bundled payload.
- `useNemesisOpponents(minGames)` — refetches on slider change.
- `useOpponentProfile(opponentName)` — `null` until an opponent is
  selected.
- `useOpponentSwindleRate(opponentName)` — fetched alongside the
  profile.
- `useOpponentNarrative(opponentName)` —
  `{ narrative, generatedAt, loading, error, generating, generateError, generate() }`,
  same shape as `useOpeningNarrative`.

All five follow the established `loading`/`error`/data shape with
`cancelled`-on-unmount cleanup.

### Components

- **`ClickableGameList.tsx`** — new, small, reusable: a bare
  `game_id[]` → list of links to `matchups/:gameId`. Simpler than
  reusing `GameExplorerTable`'s row-click machinery for a bare ID list.
- **`RatingFormTab.tsx`** — composes all 6 sections from
  `useMatchupsRatingForm()`: `barChart` for rating-diff win rate, a
  plain 3-row table for color-by-rating, a two-metric comparison panel
  (`grid grid-cols-2`) for giant-killing counts, `barChart` + two
  sub-`barChart`s for collapse causes, the new `multiLineChart` for the
  giant-killing trend, and two `ClickableGameList`s for comeback/
  collapse.
- **`NemesisTable.tsx`** — the 4 ranking tables (toughest/favorite/
  most-played/surprise) share this one component, parameterized by
  sort key and column set (mirrors `_nem_table`'s `col_order`/
  `col_config` parameterization). W-D-L collapses into one `record`
  string column. Row click calls `onSelect(opponentName)`. Renders
  `ConfidenceBadge` per row.
- **`OpponentPicker.tsx`** — inline (non-dialog) `Command` list (same
  primitive as `CommandPalette`), filtering the full nemesis-qualifying
  opponent list by typed text; selecting calls the same
  `onSelect(opponentName)` as table rows.
- **`OpponentProfilePanel.tsx`** — the 5 profile tables (openings/
  position/castling/action_side/clock) in a `grid-cols-2` layout
  matching Streamlit's `prof_col1..4` pairing, the swindle-rate
  caption, and the narrative generate/regenerate block (ported from
  Openings' equivalent panel, including the
  `claude_narrative.api_key_available()` gating text).
- **`NamedOpponentsTab.tsx`** — composes the min-games `Slider`, the 4
  `NemesisTable`s (toughest/favorite side-by-side, then most-played,
  then surprise), `OpponentPicker`, and `OpponentProfilePanel` for
  whichever opponent is currently selected from either source.

### `lib/charts.ts` addition

`multiLineChart(rows, x, series: [{y, label, color}], options)` —
same-axis multi-series line chart. Used once, for the giant-killing
trend's `pct_upset`/`pct_collapse` pair.

### Page composition (`MatchupsPage.tsx`)

`Tabs` with two `Tab.Panel`s (`RatingFormTab`, `NamedOpponentsTab`) —
only the active tab's hooks fire. Wired into `App.tsx`:
`PAGE_COMPONENTS.matchups = MatchupsPage` (currently falls back to
`PageStub` — `navCandidates.ts` already has the `{ title: 'Matchups &
Opponents', url_path: 'matchups' }` entry). One new hidden route:

```tsx
<Route path="matchups/:gameId" element={<GameDetailPage />} />
```

## Non-goals

- Opponent Prep deep link (decision 2) — re-add once Opponent Prep is
  ported.
- Any change to `dashboard/matchups_view.py` or
  `dashboard/data/matchups.py` — left exactly as-is.
- `chesswright_pro/tournament_prep.py`'s own use of `cached_opponent_profile`
  — untouched, separate code path.
- Streaming/progressive narrative rendering — matches every other
  Claude-backed feature (blocking POST).
- Drill Export / Global Search deep-linking — no such links exist on
  this page in Streamlit either.

## Testing

- `tests/integration/test_api_matchups.py` (new): `TestClient` +
  `migrated_db_path` fixture. `rating-form` cache behavior via
  `reset_caches()`; `nemesis` default vs. explicit `min_games`;
  `opponent-profile`/`opponent-swindle-rate` for a known opponent and an
  empty-opponent case; narrative get (empty/populated) + generate
  (happy path, 404 unknown opponent, `MissingApiKeyError` → 503, generic
  exception → 502).
- Hook tests (`use*.test.ts` ×5): loading → success/error transitions,
  mocked `fetch`.
- Component tests: `ConfidenceBadge.test.tsx` (3 tiers),
  `ClickableGameList.test.tsx` (empty vs. populated, link `href`s),
  `NemesisTable.test.tsx` (sort/column-set variants, row click),
  `OpponentPicker.test.tsx` (filter-by-typing, select),
  `OpponentProfilePanel.test.tsx` (empty vs. populated per sub-table,
  narrative generate/regenerate), `RatingFormTab.test.tsx`,
  `NamedOpponentsTab.test.tsx` (slider refetch, table-click and
  picker-click both drive the same selected opponent),
  `MatchupsPage.test.tsx` (tab switching, lazy hook activation).
- Live verification (`verify` skill): both tabs, the min-games slider, a
  table-row opponent selection and a picker-search selection landing on
  the same profile panel, the commentary generate flow, and a
  comeback/collapse game-list click landing on `matchups/:gameId`.

## Open items for the implementation plan to resolve

- Exact `NemesisTable` column-set typing (4 variants share ~80% of
  columns but the "surprise" variant adds two) — decide at
  implementation time whether that's one component with an optional
  prop or genuinely two thin wrapper components over a shared table
  renderer.
- Whether `OpponentProfilePanel`'s narrative section re-renders in place
  or the panel scrolls into view when a new opponent is selected from
  the picker (vs. a table row, which is already visible) — decide by
  checking user expectation once the component is live.
- Exact Base UI `Command`/`cmdk` API surface for a non-dialog, inline
  render — resolve by reading `command.tsx`'s actual exports at
  implementation time rather than assuming the `CommandPalette` usage
  is directly reusable without a dialog wrapper.
