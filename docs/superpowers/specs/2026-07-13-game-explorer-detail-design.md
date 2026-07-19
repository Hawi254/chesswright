# Game Explorer + Game Detail — React Port — Design

Status: pending user review of this doc
Date: 2026-07-13
Branch: worktree-frontend-spike

## Context

Slices 1-2 of the next-five port-view-slice roadmap (brainstormed this
session; Openings & Repertoire, Insights, Matchups & Opponents follow as
slices 3-5). Overview is the only page fully ported so far
(`docs/frontend_migration_status.md`); every other page is still a
`PageStub`. Game Explorer and Game Detail are ported together, not
separately: `game_explorer_view.py`'s own docstring calls out "drill-down
navigation (click a row -> Game Detail)" as the point of the page, so a
ported list nobody can click into would be a dead end.

Game Detail is the bigger of the two by far. Its own docstring calls it
"the highest-stakes single screen in the dashboard, used as the
validation case for the broader Phase 6c redesign." The full Streamlit
page carries board + eval graph, variation mode (branch and replay
your own lines), per-position annotations (glyph/comment/Claude),
saved-variations management, Board Chat, and a Pro-gated Game Report.
Scoped down for this pass to **core viewing only** — header, board
synced to the move list, eval graph, badge chips — with variation mode,
annotations, Board Chat, and Game Report deferred to later slices, the
same way Overview shipped zone-by-zone rather than in one pass.

A real technical constraint shapes this design: the existing chessboard
component (`dashboard/components/chessboard/frontend/src/index.jsx`) is
a Streamlit custom component wired to `withStreamlitConnection` /
`Streamlit.setComponentValue` — it communicates over Streamlit's iframe
postMessage bridge and cannot run standalone inside the plain React/Vite
app. It is not reusable as-is. See Technical approach.

Web research (chess.com/Lichess conventions, data-table UX practices,
board-color accessibility guidance) informed several concrete choices
below rather than being taken on aesthetic instinct alone; each is
called out inline.

## Goals

- Port Game Explorer: filter (badge pills, opponent search, analyzed-only
  checkbox), a real semantic data table (200 games, sorted by drama
  score), row click navigates to Game Detail.
- Port Game Detail (core viewing): header (opponent/date/result/opening/
  platform link/badge chips), board synced to a move list, a
  win-probability eval graph, all three sharing one `ply` state so
  clicking a move or an eval-graph point moves the board, and vice
  versa. Left/right arrow keys also step `ply`.
- Extract a read-only, plain-React chessboard component (position
  display + last-move highlight only — no drag/drop, no arrows) for this
  slice, reusing the existing component's chess.js position logic
  without its Streamlit bridge or its interactive/promotion-picker code
  (unneeded until variation mode ships).
- Recolor board squares away from react-chessboard's default cream/green
  to a copper-brown/parchment pair pulled from the existing palette —
  research-backed (see below), not a green board dropped into a
  near-black theme.
- Extract `CareerHighlight.tsx`'s badge-chip logic (`BADGE_CHIPS`,
  `TONE_CLASSES`, `activeChipsFor`, the hand-transcribed `BADGE_LEGEND`
  text) into a shared `frontend/src/lib/badges.ts` so Game Explorer's
  filter pills and table badge column don't become a third hand-copy of
  the same thing.
- Represent "drama score" as a small inline copper intensity bar per
  table row instead of a bare integer — the same rail grammar as
  Overview's eval rail and this page's own eval graph, reused a third
  time rather than invented fresh.

## Non-goals (explicit)

- **Variation mode, annotations (incl. Claude), saved variations, Board
  Chat, Game Report.** All deferred to later slices once this core page
  is live and proven. This also means the chessboard extraction only
  needs the read-only display subset of the existing component's logic
  — no piece dragging, no promotion picker, no `Streamlit`-bridge
  equivalent event channel — since nothing in this slice lets the user
  make a move on the board.
- **User-facing column sorting on the Game Explorer table.** The
  Streamlit version has no sort control (fixed drama-score-descending
  order) — matching that is parity, not a cut corner. Sortable columns
  are a real, named data-table best practice (see Research) but adding
  one now would be new scope beyond the port, not a design requirement
  of it.
- **Zebra striping on the table.** Recommended practice for long tables,
  but this table is capped at 200 rows (matches Streamlit's
  `.head(200)`) — hairline row dividers only, matching the existing
  "ledger" panel language used elsewhere in the app.
- **Promoting `--cw-panel-2`/`--cw-cyan` beyond app-wide `:root`.** They
  move from Overview-only (`.cw-overview` scope) to `:root` because Game
  Detail genuinely needs both; no other new tokens are introduced.
- **A live-polling or streaming variant of anything on this page.** Both
  pages are point-in-time data fetches, same as every slice shipped so
  far.

## Design

### Visual tokens (extending the existing system, not a new one)

No new hex values. Reused from `theme.ts`/`index.css`:

| Token | Value | Role here |
|---|---|---|
| `--cw-canvas` | `#0B0F14` | page background |
| `--cw-panel` / `--cw-panel-2` | `#131A22` / `#0F141B` | table row / filter-bar surfaces, two elevation tiers |
| `--cw-copper` | `#E08A3C` | primary accent — drama bar, eval-graph fill, active-row state |
| `--cw-cyan` | `#4FB8C4` | secondary accent — eval-graph 50% reference line, "live data" role already established by Overview |
| `--cw-text` / `--cw-muted` | `#ECEEF0` / 60% | text hierarchy |
| `--cw-line` | `#232B37` | hairline row/section dividers |

**Change**: `--cw-panel-2` and `--cw-cyan` move from `.cw-overview`-scoped
to `:root` (app-wide) in `index.css`, since this page needs both and a
second near-duplicate token set under a different class name would be
pure duplication.

**Type**: `font-condensed` (labels, headers, buttons), `font-mono` (all
numerals — dates, drama scores, move numbers, the win-probability
readout). No serif — nothing on either page is narrative prose the way
Overview's one executive-summary line was.

**Board squares**: copper-brown dark squares / warm parchment light
squares, pulled from the existing palette family (not react-chessboard's
default cream/green). Research-backed: expert chess-equipment guidance
recommends high contrast between pieces and medium-to-low contrast
between squares, brown/cream specifically called out as the reference
combination, and green tones flagged as prone to blending and hurting
legibility. Also checked the existing highlight colors (yellow
last-move, near-black legal-move-dot gradients) — none pair red against
green, so the accessibility guidance against red/green pairing is
already satisfied and needs no further change.

### Signature elements

- **Eval graph as the rail, unrolled.** The app's one recurring visual
  idea is an evaluation rail (vertical bar, copper fill, center
  reference line) — Overview's signature element. Game Detail's eval
  graph is that same rail unrolled across time: copper fill-area line
  for the player's win probability, cyan dotted line at the 50%
  reference (cyan already owns "live data" duty from the Overview
  design), a vertical marker at the current `ply`. This is the second
  reuse of that grammar, not a new chart style. Framing the Y-axis as
  win probability (not raw centipawns) is also the more current
  approach among modern engines' WDL heads, per research — this app's
  existing `player_win_prob_series` data already matches that framing,
  so no data-layer change, just carrying the visual idea forward.
- **Drama bar.** Game Explorer's drama-score column becomes a small
  inline copper intensity bar (`▓▓▓░░`-style, scaled to the current
  filtered set's max) instead of a bare integer — third reuse of the
  same rail grammar (Overview's rail → eval graph → drama bar), giving
  the app one coherent "instrument-panel readout" motif across pages
  rather than three unrelated decorations.
- **Recolored board**, as above — small but real: it's the first time
  any board renders inside the Engine Room shell, so getting it to read
  as part of the app rather than a dropped-in widget matters
  disproportionately to its visual weight.

### Layout — Game Explorer

```
┌─────────────────────────────────────────────────────────────┐
│ GAME EXPLORER                                                │
│ 4,812 games total (1,203 with at least one badge)            │
│ 3,940 of 4,812 analyzed (81.9%) · badges need analysis ⓘ     │
├─────────────────────────────────────────────────────────────┤
│ FILTER  ⌗ Comeback ⌗ Giant-killing ⌗ Brilliant find …        │
│ Opponent contains [___________]   ☐ Only analyzed games      │
├─────────────────────────────────────────────────────────────┤
│ Showing 312 games, sorted by drama score (most dramatic first)│
├──────┬────────┬──────┬────────┬──────────┬────────┬────┬────┤
│ Date │Opponent│Color │ Result │ Opening  │ Badges │Drama│Game│
├──────┼────────┼──────┼────────┼──────────┼────────┼────┼────┤
│07-12 │kingsl.. │ ⚫  │ Won   │ Sicilian │[Comeback]│▓▓▓▓░│View↗│
│07-11 │rook_99  │ ⚪  │ Lost  │ Caro-Kann│         │▓▓░░░│View↗│
└──────┴────────┴──────┴────────┴──────────┴────────┴────┴────┘
```

Real semantic `<table>`/`<thead>`/`<tbody>`/`<th scope="col">` markup,
not a div-grid — research confirmed this gets keyboard and screen-reader
support "almost for free," and this is the first genuine data table in
the React app, cheap to get right now vs. retrofit later. Hairline row
dividers (`--cw-line`), no boxed borders, no zebra striping (see
Non-goals). Platform column inserted conditionally, same rule as
Streamlit (`two_platforms` check). Row click (whole row, not just the
link cell) navigates to Game Detail.

### Layout — Game Detail (core viewing)

```
┌─────────────────────────────────────────────────────────────┐
│ ← Back to Game Explorer                                      │
│ vs. kingslayer99 · 2026-07-12 · Won · Sicilian Defense  View↗│
│ [Comeback] [Nail-biter]                                      │
├───────────────────────┬───────────────────────────────────────┤
│                       │  1. e4      e5                        │
│                       │  2. Nf3     Nc6                       │
│      [ board ]        │  3. Bb5     a6      ← current ply     │
│    (copper/parchment  │  4. Ba4     Nf6                       │
│     squares, last-    │  ...                                  │
│     move highlight)   │  (monospace, scrollable, click a      │
│                       │   move to jump the board+graph to it) │
├───────────────────────┴───────────────────────────────────────┤
│  Your win probability                              ⌂ 50%      │
│  ╱\_╱‾╲___╱‾‾‾╲___________╱‾‾╲                                │
│  (copper fill-area line, cyan dotted 50% reference, click a   │
│   point to jump ply — same interaction as the move list)      │
└─────────────────────────────────────────────────────────────┘
```

Board, move list, and eval graph all read/write one shared `ply` state
(lifted in `GameDetailPage.tsx`) — clicking any of the three moves the
other two. Left/right arrow keys also step `ply` via a page-level
`keydown` listener; this is genuinely simpler than the Streamlit
version's `enable_keyboard_nav` prop, which existed only to route
keypresses through the Streamlit component bridge — with no bridge in
the way, it's just local state.

**Back navigation**: Streamlit's version threads `self_page`/
`detail_page` `st.Page` objects through so Game Detail's Back button
returns to wherever the user actually came from (Game Explorer today,
Tactical Highlights or others once those are ported). The React
equivalent is React Router's `navigate(-1)` (browser history back) —
achieves the same "return to wherever you came from" behavior without
threading page identity through props, and needs no changes as more
pages later link into Game Detail.

## Data requirements — what's ready vs. new work

Confirmed by direct inspection of `dashboard/data/` and the two
Streamlit view modules:

1. **Game Explorer table** — READY. `data.get_game_explorer_table(duck_conn)`
   already returns every column the design needs (`game_id`, `site`,
   `utc_date`, `opponent_name`, `player_color`, `outcome_for_player`,
   `time_control_category`, `opening_family`, badge boolean columns,
   `badge_count`, `drama_score`, `analysis_status`). The endpoint
   returns the full table as JSON, unfiltered and unsorted beyond
   whatever order the query already produces; filtering (badges/
   opponent-search/analyzed-only) and the `head(200)`-after-filter cap
   happen client-side in React, exactly mirroring where Streamlit does
   it today — zero new business logic either side.
2. **Game Detail header + moves** — READY. `data.get_game_detail(sqlite_conn, game_id)`
   already returns what `game_detail_view.py` renders the header and
   move list from.
3. **Win-probability series** — READY. `narrative.player_win_prob_series(moves)`
   is the existing function `_eval_graph()` already calls; the endpoint
   calls it and reshapes the result to JSON, same as every other
   ported chart so far. The existing "not enough annotated moves yet"
   empty-state message (`_eval_graph`'s `st.info(...)` branch) carries
   over as the hook's empty-data case, not silently dropped.
4. **Chessboard position display** — NEW, but small. No existing
   `data.py` function is involved; this is pure frontend work extracting
   the read-only subset (FEN → rendered position, last-move square
   highlight) of `dashboard/components/chessboard/frontend/src/index.jsx`'s
   logic into a new plain-React component with no Streamlit dependency.

## Technical approach

- **New routes** (`api/main.py`): `GET /api/games/explorer` (full table,
  per Data requirements #1) and `GET /api/games/{game_id}` (header +
  moves + win-probability series, #2-#3, one combined payload since
  Game Detail always needs all three together). Grouped in one
  `tests/integration/test_api_games.py`, matching the one-file-per-
  section convention.
- **New chessboard component** (`frontend/src/components/Chessboard.tsx`):
  plain React, `react-chessboard` + `chess.js`, read-only for this slice
  (no `onPieceDrop`/`onSquareClick` handlers, no promotion picker — none
  of that is reachable without interactivity). Takes `fen`, `orientation`,
  `lastmoveFrom`/`lastmoveTo` as props, sizes itself off a
  `ResizeObserver`'d container width the same way the existing component
  does (that sizing logic has no Streamlit dependency and carries over
  directly). This is the first port of chess-logic UI to the new stack —
  CLAUDE.md's rule against a second board implementation is honored by
  extracting the same underlying chess.js/react-chessboard usage pattern
  into the new component, not writing new chess-move logic from scratch.
- **New routing**: Game Explorer is a normal `STATIC_CANDIDATES` nav
  page (`url_path: 'game-explorer'`, already present in
  `navCandidates.ts`). Game Detail is a *hidden* route — added directly
  in `App.tsx`'s `<Routes>` as `/game-explorer/:gameId`, not added to
  `STATIC_CANDIDATES`/the sidebar, mirroring Streamlit's
  `st.Page(..., visibility="hidden")`.
- **Shared badge-chip lib** (`frontend/src/lib/badges.ts`): extracted
  from `CareerHighlight.tsx` (`BADGE_CHIPS`, `TONE_CLASSES`,
  `activeChipsFor`, `BADGE_LEGEND`), imported by both `CareerHighlight.tsx`
  (updated to use it) and the new Game Explorer filter/table code.
- **Drama bar**: computed client-side from the already-fetched table
  (`drama_score / max(drama_score in filtered set)`), rendered as a
  fixed-height div with a `width` percentage — no new backend field.

## Open items for the implementation plan to resolve

- Confirm whether `GET /api/games/{game_id}` should 404 or return a
  typed empty/error payload for an unknown `game_id` (e.g. a stale
  bookmark or a manually edited URL) — the Streamlit version can't hit
  this case the same way since navigation only ever passes a real row's
  `game_id`.
- Decide the exact drama-bar scaling rule when the filtered set has only
  one game (max = that game's own score → always full bar) — confirm
  that reads sensibly rather than needing a floor/normalization tweak.
- `docs/frontend_migration_status.md` gets updated to ✅ for both pages
  (or 🟡, given variation mode/annotations/Board Chat/Game Report remain
  for later slices — the table's legend already has a partial-status
  symbol for exactly this).
- Live-verify the arrow-key `ply` navigation doesn't conflict with
  browser-default behavior when focus is inside the move-list scroll
  container vs. elsewhere on the page.
