# Opening Tree Pro — design spec

**Date:** 2026-07-16
**Status:** approved design, not yet implemented
**Route:** `opening-tree` (already reserved in `navConfig.ts` / `navCandidates.ts` as
"Opening Tree ✦", Explore group; currently falls through to `PageStub`)

## Summary

A fresh React/FastAPI design for the Pro-only Opening Tree feature — full
functional parity with the Streamlit version (`dashboard/opening_tree_view.py`
+ the private `chesswright_pro/opening_tree.py`) but redesigned as one linked,
cohesive canvas instead of three disconnected tabs (Explorer / What Changed /
Tree Overview). The Streamlit implementation is used here only as a
**functional** reference (what data and capabilities exist), never as a UI
template, per standing project directive.

## Research grounding

- Lichess's Opening Explorer: board + frequency/win-draw-loss move table,
  click-to-drill — validates keeping a board+table explorer as the anchor
  interaction.
- Chesstrie / Repertree: whole-repertoire node-link trees with hover-preview
  boards — validates a persistent, always-visible overview alongside the
  explorer rather than a separate mode.
- Nate Solon's repertoire tool: Sankey diagram framed as "where to prioritize
  study" — considered and set aside in favor of icicle (below), but the
  underlying idea (surfacing *where attention should go*, not just raw
  structure) shows up here as the flip-badge + changes-list design.
- Controlled study (arxiv 1908.01277): icicle and sunburst score similarly,
  with a slight user preference for icicle; treemap clearly worst for
  hierarchy-comprehension tasks. Combined with this codebase already having
  icicle infrastructure (`EndingTreeIcicle.tsx` + `lib/charts.ts`, built for
  the Game Endings page) and no sunburst infrastructure, icicle is the clear
  choice over porting Streamlit's sunburst.

## Layout — linked single canvas

```
+------------------------------------------------------------------+
| [White/Black]  [Min games: slider]  [Jump to opening search box] |
+---------------------------+----------------------------------------+
|      Chessboard           |         Icicle Overview                |
|  (drag/click; engine-     |  (fixed 4-ply BFS; click a segment     |
|   confirm via existing    |   to move the board/table there;       |
|   PositionInspector)      |   [!] badge = repertoire changed here) |
+---------------------------+----------------------------------------+
|  Move table — this position's branches (click row to play move)   |
|  Move | Games | Win% | Draw% | Loss% | Avg CPL                    |
+----------------------------------------------------------------------+
|  ▸ How this position changed over time (expandable, per-position)   |
|  + Add to SRS deck (target: <top move>)                             |
+----------------------------------------------------------------------+
|  Recent repertoire changes (all depths, not just the icicle's       |
|  4-ply window — each row jumps the whole canvas to that position)   |
+----------------------------------------------------------------------+
```

One `currentFen`/`path` state (owned by `OpeningTreePage.tsx`) drives the
board, the move table, and the highlighted icicle segment. Clicking the
board, a table row, an icicle segment, a changes-list row, or a jump-search
result all update the same shared state — no tab/mode switch anywhere on
this page.

**Why the icicle stays capped at 4 plies but the changes list doesn't:** the
icicle's badges only cover its own 4-ply render window (same bound the
Streamlit sunburst used, for the same reason — branches thin out to
n_games=1 past that depth for nearly all players). `compute_dominant_move_flips`
itself scans to ply 40. The changes list is the discovery surface for deeper
flips (mirrors Streamlit's "Open in Explorer" jump); the icicle badges are
the at-a-glance surface for shallow ones.

## Components

New, under `frontend/src/components/` (colocated `.test.tsx` per existing
convention):

- `OpeningTreePage.tsx` (in `pages/`) — owns `currentFen`/`path`/`color`/
  `minGames` state; renders the full-page `ProUpsell` when
  `!useProStatus().active`, otherwise the canvas.
- `OpeningTreeControls.tsx` — header bar: color toggle, min-games slider,
  jump search box (fuzzy-matches the ~81 known opening family names
  client-side using `cmdk`'s built-in filter — the same library already
  powering `CommandPalette.tsx` — not `rapidfuzz`, which is a Python-only
  dependency used server-side by the Streamlit-era `dashboard/data/search.py`).
- `OpeningTreeIcicle.tsx` — wraps a new icicle-chart variant in `lib/charts.ts`
  that accepts win-rate coloring + a flip-badge mask; same `{tree,
  onNodeClick}` shape as `EndingTreeIcicle.tsx`.
- `OpeningMoveTable.tsx` — branches table; row click plays that move (replaces
  Streamlit's checkbox-selection quirk with a plain row click — a real
  interaction simplification, not a re-template).
- `PositionTimelinePanel.tsx` — expandable per-position "changed over time"
  chart, reusing the existing stacked-bar chart helper.
- `RepertoireChangesList.tsx` — scrollable all-depth flips list, "Jump here"
  per row.
- `OpeningTreeFlipDrawer.tsx` — detail drawer opened from an icicle badge:
  old/new move, era win%, board preview, jump action.

Reused as-is: `Chessboard.tsx`, `PositionInspector.tsx` +
`useAnalysePosition.ts` (engine confirm), `useProStatus.ts`.

New hooks under `frontend/src/hooks/`, matching the existing loading/error/
data hook shape: `useOpeningTreeMoves.ts`, `useOpeningTreeMap.ts`,
`useOpeningTreeChanges.ts`, `useOpeningPositionTimeline.ts`,
`useOpeningJump.ts`, `useAddSrsCard.ts`.

## Cross-repo API surface

**Hard constraint, not a preference:** the public core repo must never ship
this feature's actual source — only the gate check and the fact that it
exists (this is `opening_tree_view.py`'s own documented reason for existing
as a thin wrapper around the private `chesswright_pro` package). The React
port must preserve that split:

- **This repo (public, MIT):** thin, Pro-gated FastAPI routes in
  `api/main.py` — same `if not pro_gate.is_pro_active(): raise 403` /
  `try: from chesswright_pro import ... except ImportError: raise 501`
  pattern already used by `/api/games/{id}/report/generate` — plus one new
  **core** data function (below), because it's a data lookup, not feature
  orchestration.
- **Private `chesswright-pro` repo:** all actual orchestration — BFS
  map-building (port of `_build_sunburst_nodes`, restructured for the
  icicle's ids/parents/values shape, which Plotly's icicle trace consumes
  identically to sunburst), flip formatting, per-position move/timeline
  formatting. **Implementing this design touches two repos** — the
  implementation plan needs to sequence work in both.

| Endpoint | Gated? | Wraps |
|---|---|---|
| `GET /api/opening-tree/moves` | Yes | `chesswright_pro.opening_tree_api.moves(fen, ply, color, min_games)` → core `get_opening_moves_from_fen` |
| `GET /api/opening-tree/map` | Yes | `chesswright_pro.opening_tree_api.map(color, min_games)` → BFS nodes, fixed 4-ply |
| `GET /api/opening-tree/timeline` | Yes | `chesswright_pro.opening_tree_api.timeline(fen, color)` → `get_opening_moves_by_year` + `summarize_position_timeline` |
| `GET /api/opening-tree/changes` | Yes | `chesswright_pro.opening_tree_api.changes(color, split_year, min_games)` → `compute_dominant_move_flips` + `get_path_to_position` |
| `GET /api/opening-tree/jump` | No | core `get_representative_path_for_family` (new) |
| `POST /api/opening-tree/srs` | No | core `data.srs.add_cards` (already reachable from Board Chat today) |

The last two aren't Pro-gated because they call core primitives directly —
the page itself stays inaccessible to non-Pro users (full-page upsell,
below), so this doesn't leak the feature.

### Jump-to-opening resolution (new core logic)

A free-text query like "Najdorf" can't be reverse-mapped to a move sequence
— ECO classification works forward, from moves to name, via each game's
already-computed `opening_family` column (confirmed live in
`opening_explorer.py`'s `branch_stats`). New core function
`get_representative_path_for_family(conn, opening_family, player_color)` in
`dashboard/data/openings.py`: finds the player's most-frequently-played move
path among their own games tagged with that family, returned as a SAN list
(same shape `get_path_to_position` already returns).

## Non-Pro state

Full-page static upsell, no data fetched, matching the existing
`GameReportPanel`/`ProUpsell` pattern:

> **Opening Tree** is a Chesswright Pro feature. Explore your repertoire as
> a live, linked map: jump straight to any opening, drill through your
> actual games move by move with win rates and accuracy at every branch,
> spot exactly where your repertoire has changed over time, and push weak
> positions straight into your SRS queue. Upgrade to Pro to unlock this
> feature. → chesswright.gumroad.com

## Edge cases (content decisions carried over from the Streamlit reference —
these are chess/data facts, not UI template)

- Player-to-move vs. opponent-to-move empty captions differ ("explore
  freely on the board" vs. "play a move to continue").
- Transposition-only flip rows (no single verified move order): board-only
  preview, "Jump here" disabled, explanatory caption.
- Single-year data: timeline panel and changes list both go empty-state
  rather than rendering a degenerate one-bar chart.
- Jump search with no fuzzy match, or a match with zero games in the
  selected color: empty state in the jump box, not a silent no-op.

**Genuinely simplified vs. Streamlit:** no manual session-state cache
invalidation on color/threshold change — the React hooks just refetch on
dependency change (color/minGames/path), removing a whole class of
staleness bugs the Streamlit version had to hand-manage. The cache-warm
check (`ensure_opening_position_stats`) stays server-side and idempotent
(count-sentinel gated); the frontend just shows a loading state on
`/map`/`/moves` that's usually instant but occasionally takes a few seconds
right after a new analysis batch, with copy explaining why.

## Testing

- Colocated Vitest `.test.tsx`/`.test.ts` for every new component and hook
  (mocked fetch/hooks, matching `EndingTreeIcicle.test.tsx`/
  `useEndingTree.test.ts`).
- New core function `get_representative_path_for_family` gets a pytest unit
  test alongside `openings.py`'s existing tests, in this repo.
- New orchestration logic in `chesswright-pro` gets its own tests in that
  repo's suite (separate test run, separate repo).
- Before calling it done: a live-verify pass (the `verify` skill) against
  the real dev `chess.db`, Pro-licensed — jump to a known opening, drill a
  few plies, click an icicle segment, open a flip drawer, add a card to SRS.

## Decisions log (from brainstorming Q&A)

1. Full functional parity with Streamlit's 3 capabilities, redesigned as one
   cohesive surface, not silo tabs.
2. Overview visualization: icicle chart, reusing existing infra — not
   sunburst, not Sankey.
3. Layout: linked single canvas, not tabs and not two independently-scrolling
   panes.
4. Global controls (color, min-games) live in one persistent header bar
   shared by both panes.
5. Both "change over time" surfaces kept: per-position timeline (depth) and
   icicle badges + changes list (discovery) answer different questions.
6. New jump-to-opening search added — a real usability gap in the Streamlit
   version, not present there.
7. Non-Pro state: full-page static upsell, no illustrative screenshot.
8. Icicle depth fixed at 4 plies, not configurable.
9. Add-to-SRS button included now, even though the SRS Drills page itself is
   unbuilt — the backend primitive already works headless.
