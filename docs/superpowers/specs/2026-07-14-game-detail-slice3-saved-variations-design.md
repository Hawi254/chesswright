# Game Detail Slice 3 — Saved Variations

Status: approved by user 2026-07-14
Branch: worktree-frontend-spike

## Context

`docs/superpowers/specs/2026-07-13-game-detail-completion-design.md` sequenced
the remaining Game Detail work into six slices. Slice 1 (board-interaction
infra) and Slice 2 (interactive board + variation mode) are shipped —
`api/main.py` already has `POST /api/games/{game_id}/variations`,
`PUT /api/variations/{variation_id}`, and `DELETE /api/variations/{variation_id}`,
and `useVariation.ts` auto-persists a variation on every move made while in
variation mode: `POST` on the first move, `PUT` on each subsequent move, no
explicit "Save" gesture. This slice is next in that sequence: **Saved
variations** — list, load, delete, and export the variations that mode has
been quietly accumulating.

The Streamlit reference (`dashboard/game_detail_view.py`'s
`_render_saved_variations`, `dashboard/data/variations.py`,
`dashboard/chess_display.py`'s `variation_to_pgn`) is a source for
business logic and requirements only, per the standing directive — its
`st.session_state`/`st.rerun()` control flow does not carry over.

## Goals

- Show the user every variation saved against the current game (title,
  move count, branch point).
- Let them re-enter one (`Load`), jumping to the end of the saved line,
  matching the Streamlit original.
- Let them delete one, including tidying up if it's the currently active
  variation.
- Let them export one as a PGN file.
- Keep the list live during the session: refetch after any
  create/update/discard/delete, not just on page load.

## Non-goals

- Renaming/titling variations — no such UI exists in the Streamlit
  original either (title is always server-derived: `null` → "From move N"
  display fallback). Not invented here.
- Annotations (Slice 4) — `variation_to_pgn` already accepts an
  `annotations` dict and the PGN endpoint will pass through whatever
  `get_variation_annotations` returns, but until Slice 4 ships that's
  always `{}`. No annotation UI in this slice.
- Any change to the auto-persist-on-every-move behavior established in
  Slice 2 — that's already a settled redesign decision, not reopened here.

## Backend

### `GET /api/games/{game_id}/variations`

Thin wrapper around the existing, unmodified `data.list_variations`.
Returns:
```json
[
  {
    "id": "uuid",
    "game_id": "uuid",
    "branch_ply": int,
    "branch_fen": "string",
    "moves": ["e2e4", "..."],
    "title": "string | null",
    "created_at": "string",
    "updated_at": "string"
  }
]
```
Ordered newest-first (`list_variations`'s existing `ORDER BY created_at
DESC`).

### `GET /api/variations/{variation_id}/pgn`

Wraps existing `data.get_variation_annotations` +
`chess_display.variation_to_pgn` (both already Streamlit-free, reused
as-is). Looks up the variation's `branch_fen`/`moves`/`title` via a new
`data.get_variation(sqlite_conn, variation_id)` helper (list_variations
returns a list scoped to a game; a single-row lookup by id doesn't exist
yet and is added alongside the endpoint). Returns the PGN text with:
```
Content-Type: application/x-chess-pgn
Content-Disposition: attachment; filename="{safe_title}.pgn"
```
`safe_title` derived the same way as the Streamlit version
(`var.title or f"var_{var.id[:8]}"`, spaces replaced with underscores).
404 if the variation id doesn't exist.

## Frontend

### `useSavedVariations(gameId)` hook

`frontend/src/hooks/useSavedVariations.ts`:
```ts
{ variations: SavedVariation[]; loading: boolean; refetch: () => void }
```
Fetches on mount and whenever `refetch()` is called. No polling.

### `SavedVariationsPanel` component

`frontend/src/components/SavedVariationsPanel.tsx`. Renders `null` if
`variations` is empty (matches the Streamlit early-return). Each row:
title (falls back to `From move {branchMoveNumber}`, computed the same
way as the Streamlit version's `(branch_ply + 1) // 2`, i.e.
`Math.floor((branchPly + 1) / 2)` in JS), move count, branch move number,
and three actions:
- **Load** — calls `onLoad(variation)`.
- **PGN ↓** — a plain `<a href="${API_BASE}/api/variations/${id}/pgn" download>`
  link; the browser handles the download via the endpoint's
  `Content-Disposition` header, no frontend blob handling needed.
- **Delete** — calls `onDelete(variation.id)`.

### `useVariation` additions

New `load(variation: SavedVariation)` method:
1. Replays `variation.moves` (UCI) onto a `Chess(variation.branch_fen)`
   instance move-by-move, collecting `sans` and `fens` as it goes —
   mirrors the backend's own defensive `compute_variation_fen`: if a
   move in the stored sequence is illegal, replay stops at that point
   (uses the fens/sans collected so far) rather than throwing.
2. Sets state: `active: true`, `variationId: variation.id`,
   `branchPly: variation.branch_ply`, the replayed `moves`/`sans`/`fens`,
   `step: moves.length` — jumps straight to the end of the line, same as
   the Streamlit original's `Load` behavior (`var_step__{gid} =
   len(var.moves)`).

### `GameDetailPage` wiring

- Mounts `useSavedVariations(gameId)` alongside the existing
  `useVariation(gameId)`.
- Passes `variation.load` as `SavedVariationsPanel`'s `onLoad` — switches
  immediately with no confirmation, since the previously-active variation
  (if any) is already auto-persisted and nothing is lost.
- Delete calls `DELETE /api/variations/{id}`, then `refetch()`s the list;
  if the deleted variation was the currently active one, also resets
  `useVariation`'s state (its DB row no longer exists — mirrors the
  Streamlit original's session-state cleanup on delete-of-active).
- After any action that mutates the variation set — first move of a new
  branch (create), discard, or delete — calls the saved-variations hook's
  `refetch()` so the panel reflects the current DB state without a page
  reload.
- Panel renders below `VariationPanel` in the layout (the two form one
  variation-management cluster; Streamlit's literal render-call ordering
  elsewhere in `game_detail_view.py` is a fragment-execution artifact, not
  a deliberate layout decision worth replicating).

## Error handling

- List-fetch failure: `SavedVariationsPanel` renders nothing (same
  fail-safe as an empty list — this is a non-blocking panel, not core
  page functionality).
- PGN-download failure: ordinary failed browser download; no special
  frontend handling.
- `load()` replay hitting an illegal move: stops at the last good
  position rather than throwing, matching the backend's own
  `compute_variation_fen` behavior.

## Testing

- `tests/integration/test_api_variations.py`: add cases for the list
  endpoint (empty, multiple variations, ordering) and the PGN endpoint
  (happy path, 404 on unknown id, filename derivation).
- `frontend/src/hooks/useSavedVariations.test.ts`: fetch-on-mount,
  refetch, empty-list.
- `frontend/src/components/SavedVariationsPanel.test.tsx`: empty renders
  nothing, title fallback, Load/Delete/PGN-link wiring.
- `frontend/src/hooks/useVariation.test.ts`: add cases for `load()` —
  full replay, and the illegal-move-stops-early defensive path.
- `frontend/src/pages/GameDetailPage.test.tsx`: add a case asserting
  `refetch()` fires after a create/discard/delete action.

## Open items for the implementation plan to resolve

- Exact shape of the new `data.get_variation(sqlite_conn, variation_id)`
  single-row lookup helper (needed by the PGN endpoint) — straightforward
  given `list_variations`' existing query, but not yet written.
- Whether `SavedVariationsPanel`'s Delete needs any inline confirmation
  (Streamlit's original has none — a plain button, no `st.confirm`
  equivalent) — default to no confirmation, matching the reference,
  unless the implementation plan finds a reason to diverge.
