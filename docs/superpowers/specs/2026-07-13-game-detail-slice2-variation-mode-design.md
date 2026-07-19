# Game Detail Slice 2 — Interactive Board + Variation Mode

Status: approved by user 2026-07-13
Branch: worktree-frontend-spike

## Context

Slice 1 (`docs/superpowers/specs/2026-07-13-game-detail-completion-design.md`,
plan at `docs/superpowers/plans/2026-07-13-game-detail-board-interaction-infra.md`,
**not yet implemented**) adds `POST /api/analyse-position` and
`Chessboard.tsx`'s `arrows`/`highlightedSquares` display props. This slice
is "the trunk" of the roadmap's remaining 5 pieces: it makes the board
interactive and adds variation mode (move input, branching from any
mainline position, persisted saved variations). It depends on Slice 1
landing first — see Global Constraints below.

**Standing directive** (unchanged from the roadmap doc): the Streamlit
source (`dashboard/game_detail_view.py`'s `_render_board_and_chat`, and
`dashboard/components/chessboard/frontend/src/index.jsx`, the old
vanilla-JS board) is a reference for business logic only. Its
`st.session_state`/`st.rerun()`/nonce-staleness/`_load_ply_key` control
flow is a workaround for Streamlit's rerun model and does not port.

One useful finding from reading the old vanilla-JS board: its drag/drop,
click-to-move, promotion picker, and legal-move-square highlighting were
**already pure chess.js logic running client-side** — only the final move
result crossed the Streamlit bridge via `Streamlit.setComponentValue`.
That logic ports directly; only what came after it (the bridge) is
dropped.

## Goals

Let a user drag/click a legal move on any mainline position, branching
into a persisted variation; play on within it; navigate its steps;
exit back to mainline or discard it. Reuse Slice 1's engine-analysis
hook and arrow display inside variation mode too.

## Non-goals for this slice

- Per-position annotations (Slice 4).
- Browsing/reopening previously saved variations — a "Saved variations"
  list UI (Slice 3). This slice creates and persists variations as a side
  effect of play; Slice 3 is the separate list/load UI.
- Board Chat (Slice 6), Game Report (Slice 5).
- Multiple simultaneous variations or a branching tree UI — one active
  variation at a time per game, matching the Streamlit original's single
  set of `var_*` session keys per game.

## Architecture

**Chessboard becomes a controlled component.** It receives `fen` as
before; on a drag/drop or click-to-move it validates against a throwaway
`new Chess(fen)` copy and calls `onMove({ uci, fen, san })` up to the
parent — it does not keep the resulting position in its own state. The
parent (via `useVariation`, below) owns position truth and passes the new
`fen` back down, causing a re-render. The only internal state Chessboard
keeps is ephemeral, presentational UI state: `selectedSquare` (click-to-
move) and `pendingPromotion` (the promotion picker, shown before a
promoting move is finalized).

This is simpler than the Streamlit version, which kept an internal `game`
mirror only to paper over bridge round-trip latency — with no bridge,
there's nothing to mirror.

**Two alternatives considered and rejected:**
- A server-side "make move" endpoint validating each move via
  python-chess, mirroring Streamlit's per-move round trip onto real REST.
  Rejected: chess.js already proves client-side validation works with
  zero server dependency; a network round trip per move adds latency for
  no gain, and is exactly the kind of literal port the standing directive
  warns against.
- A proper variation-tree structure supporting branching sub-lines.
  Rejected: `migrations/0022_add_variations.sql`'s `variations` table
  stores one flat `moves_json` list per row, and the Streamlit business
  logic itself is a single line. Overkill; YAGNI.

## Data flow

### New endpoints (`api/main.py`)

Thin wrappers over the already-Streamlit-free
`dashboard/data/variations.py` (`save_variation`, `update_variation_moves`,
`delete_variation` — all confirmed pure functions taking `sqlite_conn`).

```
POST /api/games/{game_id}/variations
  body: { "branch_ply": int, "branch_fen": string, "moves": string[] }
  -> { "id": string }
  Calls data.save_variation(sqlite_conn, game_id, branch_ply, branch_fen, moves).
  Called once, when the first off-mainline move is made (no explicit
  "save" action -- matches Streamlit: a variation is always persisted
  from its first move).

PUT /api/variations/{variation_id}
  body: { "moves": string[] }
  -> { "ok": true }
  Calls data.update_variation_moves(sqlite_conn, variation_id, moves).
  Called on every subsequent move while the variation is active.

DELETE /api/variations/{variation_id}
  -> { "ok": true }
  Calls data.delete_variation(sqlite_conn, variation_id).
  Called by "Discard variation".
```

No 404 handling for unknown/stale `variation_id` on PUT/DELETE — these
ids are never user-navigable via URL (unlike `game_id`), only ever
produced by this session's own POST call, and `data.py`'s own functions
are silent no-ops on an unknown id. Deliberate simplification, not an
oversight.

**CORS**: Slice 1 widens `allow_methods` to `["GET", "POST"]`. This slice
needs `PUT` and `DELETE` added too — `["GET", "POST", "PUT", "DELETE"]`.
Direct dependency on Slice 1 landing first.

### `useVariation(gameId: string)` hook (`frontend/src/hooks/useVariation.ts`)

```ts
interface MoveResult { uci: string; fen: string; san: string }

interface UseVariationResult {
  active: boolean
  variationId: string | null
  branchPly: number | null
  moves: string[]          // UCI, one per ply played in the variation
  sans: string[]            // SAN, parallel to moves
  step: number               // 0..moves.length
  currentFen: string | null  // fens[step]; null when !active
  lastMoveSquares: { from: string; to: string } | null
  applyMove: (currentPly: number, currentMainlineFen: string, move: MoveResult) => void
  stepTo: (n: number) => void
  exit: () => void
  discard: () => void
}
```

Internal state keeps `fens: string[]` parallel to `moves` (`fens[0]` is
`branchFen`, `fens[i]` is the position after `moves[i-1]`) — each fen is
already known from the chess.js move result at the moment it was played,
so stepping through the variation is a plain array index, not a
re-derivation from scratch the way Streamlit's `compute_variation_fen`
had to replay moves every rerun. `compute_variation_fen` itself is not
needed by this slice (only by Slice 3's "load a saved variation" flow,
which starts from a stored `moves_json` with no in-memory fens yet).

`applyMove` behavior: if not `active`, this is the branch move — sets
`active=true`, `branchPly=currentPly`, `moves=[move.uci]`,
`fens=[currentMainlineFen, move.fen]`, `sans=[move.san]`, `step=1`, fires
`POST .../variations`, stores the returned id as `variationId`. If
already `active`, truncates at `step` before appending (matches
Streamlit's `var_moves[:var_step] + [uci]` — replacing a line when
playing from a earlier step) and fires `PUT`.

`stepTo(n)` just re-indexes `fens`/`sans` — no network call (matches
Streamlit's Prev/Next, which never persist).

`exit()` clears all local state (`active=false`, `moves=[]`, etc.) but
issues no DELETE — the variation stays saved (Slice 3 will list it).

`discard()` fires `DELETE` (if `variationId` is set) then clears local
state identically to `exit()`.

Hook-scoped (not lifted), matching Slice 1's `useAnalysePosition`
precedent — resets naturally on `GameDetailPage` unmount.

### `Chessboard.tsx` additions

```ts
interactive?: boolean       // default false; existing read-only call sites unaffected
onMove?: (move: MoveResult) => void   // required in practice when interactive=true
```

Ported from the old vanilla board's chess.js logic (drag/drop via
`onPieceDrop`, click-to-move via `onSquareClick` + `selectedSquare`,
legal-move-square highlighting via `game.moves({square, verbose: true})`,
promotion detection + a picker overlay for the 4 promotion pieces). All
of it operates on a throwaway `new Chess(fen)` copy per attempt — no
internal position state survives between renders.

### `VariationPanel.tsx` (new component, `frontend/src/components/`)

Sibling to the existing `MoveList`/`EvalGraph` components.

```ts
{
  active: boolean
  branchPly: number | null
  sans: string[]
  step: number
  onStepTo: (n: number) => void
  onExit: () => void
  onDiscard: () => void
}
```

Renders "Variation from move N — step of total" header, the SAN line
("12. Nf3 Nc6 13. Bb5", with a "12…" lead-in when the branch starts on
Black's move — computed from `branchPly`'s parity), Prev/Next buttons
(disabled at the ends), Exit and Discard buttons. Returns `null` when
`!active`.

### `GameDetailPage.tsx` wiring

- `const variation = useVariation(gameId)`.
- `currentFen` (introduced in Slice 1) becomes:
  `variation.active ? variation.currentFen : (currentMove?.fen_after ?? moves?.[0]?.fen_before)`.
- `lastMoveSquares` becomes `variation.active ? variation.lastMoveSquares : <existing mainline calc>`.
- `<Chessboard interactive onMove={(m) => variation.applyMove(ply!, currentFen, m)} .../>`.
- `<VariationPanel active={variation.active} branchPly={variation.branchPly} sans={variation.sans} step={variation.step} onStepTo={variation.stepTo} onExit={variation.exit} onDiscard={variation.discard} />` rendered below the board.
- `MoveList`'s and `EvalGraph`'s `onSelectPly` both wrap the existing
  `setPly` call: `(newPly) => { variation.exit(); setPly(newPly) }` — a
  mainline-ply click always exits variation mode first (per the approved
  answer above).
- The existing page-level `keydown` handler branches on `variation.active`:
  when active, `ArrowLeft`/`ArrowRight` call `variation.stepTo(step - 1)`/
  `stepTo(step + 1)` instead of the existing mainline `setPly` logic.
- Slice 1's "Analyse position" button/hook call site switches its target
  fen from the mainline-only `currentFen` to the same `currentFen`
  (already variation-aware per the bullet above) — no other change needed
  since `useAnalysePosition` is already fen-keyed and stateless per call.

## Error handling

| Case | Behavior |
|---|---|
| `POST`/`PUT`/`DELETE` network failure | Move is still shown locally (chess.js already validated it); persistence silently retried on the *next* move's call rather than blocking play — matches Streamlit's own lack of any error UI here (its `st.rerun()`-per-move model has no failure path to design for; the closest real-world risk, a dropped write, is equally unhandled today). Not introducing new error UI beyond what the reference behavior has. |
| Illegal drag/drop or click | `onPieceDrop`/`onSquareClick` just return `false`/no-op — piece snaps back, exactly like the ported chess.js logic already does. |
| Promotion-shaped drop that's actually illegal (wrong pawn, blocked, still in check) | Verified before opening the picker (`probe.move({from, to, promotion: 'q'})`); picker never opens for an impossible move — ported as-is from the vanilla board. |

## Testing

- `tests/integration/test_api_variations.py` (new): create, update
  (including step-truncation semantics are a frontend concern, not
  tested server-side since the server just stores whatever list it's
  given), delete, and unknown-id no-op behavior for PUT/DELETE.
- `frontend/src/hooks/useVariation.test.ts`: `applyMove` from inactive
  (creates + POSTs), `applyMove` while active (appends + PUTs),
  truncate-on-replay-from-earlier-step, `stepTo` (no network call),
  `exit` (clears state, no DELETE), `discard` (DELETEs + clears state).
- `frontend/src/components/Chessboard.test.tsx` additions: legal
  drag/drop calls `onMove` with the right `{uci, fen, san}`; illegal
  drop is a no-op; promotion-shaped drop opens the picker and
  `onMove` fires only after a piece is chosen; `interactive=false`
  (default) never wires up `onPieceDrop`.
- `frontend/src/components/VariationPanel.test.tsx` (new): renders
  `null` when inactive; header text and SAN line formatting (including
  the Black-starts "12…" case); Prev/Next disabled at bounds; Exit/
  Discard call their handlers.
- `GameDetailPage.test.tsx` additions: dragging a legal move on the
  mainline board enters variation mode and shows `VariationPanel`;
  clicking a `MoveList` entry while a variation is active exits it;
  arrow keys step the variation instead of mainline `ply` while active.

## Open items for the implementation plan to resolve

- Exact promotion-picker markup/positioning to port from the vanilla
  board's inline JSX (read in full during design; straightforward
  copy of structure, not logic).
- Confirm `chess.js`'s `Chess.moves({ square, verbose: true })` API
  shape matches what the vanilla board used (same `chess.js` version
  already a frontend dependency — check `package.json` during
  implementation, not assumed here).
- Whether `applyMove`'s two positional args (`currentPly`,
  `currentMainlineFen`) should instead be threaded through as one
  object param for readability — a naming/ergonomics call for the
  plan, not an architectural one.
