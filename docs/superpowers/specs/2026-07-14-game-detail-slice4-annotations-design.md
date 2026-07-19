# Game Detail Slice 4 — Annotations

Status: approved by user 2026-07-14
Branch: worktree-frontend-spike

## Context

`docs/superpowers/specs/2026-07-13-game-detail-completion-design.md` sequenced
the remaining Game Detail work into six slices. Slices 1-3
(board-interaction infra, interactive board + variation mode, saved
variations) are shipped. This slice is next: **Annotations** — a glyph
(`!`, `??`, etc.), a free-text comment, and an optional Claude-generated
comment attached to a position.

The Streamlit reference (`dashboard/game_detail_view.py`'s
`_render_annotation_panel`, `dashboard/data/variations.py`'s
`get_variation_annotations`/`upsert_annotation`,
`dashboard/claude_narrative.py`'s `annotate_position`/`api_key_available`)
is a source for business logic and requirements only, per the standing
directive — its `st.session_state`/`st.rerun()`/`st.expander` control flow
does not carry over.

**Scope decision made this session, expanding beyond the original
roadmap doc's framing:** the roadmap described this slice as
variation-only, mirroring the Streamlit original's hard schema
constraint (`variation_annotations` requires a non-null `variation_id`
FK — there's no mainline-move annotation path in Streamlit at all). This
session's brainstorm extended scope to **also** support annotating
mainline (non-variation) positions, via new, separate storage — see
"Backend: mainline annotations" below.

## Goals

- Let the user attach a glyph + comment to any position inside an active
  variation (matches Streamlit).
- Let the user do the same for any mainline position, at any ply, without
  needing to enter variation mode first (new — not in the Streamlit
  original).
- Let the user request a Claude-generated comment for either kind of
  position, gated on whether a Claude API key is configured — with the
  gate itself surfaced via a new minimal endpoint, since the React
  Settings page (where the key would actually be configured) isn't built
  yet.
- Keep the AI-assist call honest about which position's engine
  evaluation it's using: only pass `eval_cp`/`best_move_san` into the
  Claude prompt when the already-fetched analysis result actually
  corresponds to the position being annotated, never a stale one left
  over from navigating away.

## Non-goals

- Renaming/editing the glyph vocabulary — same 7 values as Streamlit:
  `"", "!", "!!", "?", "??", "!?", "?!"`.
- Any change to `variation_to_pgn`'s existing variation-scoped annotation
  embedding, or a mainline PGN export — no mainline PGN export exists at
  all yet, in Streamlit or React.
- A real Settings/API-key-management page — `claude-key-status` is a
  narrow, single-purpose read endpoint for this slice's gating need, not
  a first step toward porting Settings (still Slice 6 in the open-items
  list, unscheduled).
- Slices 5-6 (Game Report, Board Chat) — untouched, still blocked on a
  non-Streamlit entry point in the private `chesswright-pro` repo.

## Backend: variation annotations

Existing schema and data functions (`variation_annotations` table,
`data.get_variation_annotations`, `data.upsert_annotation`) are reused
unmodified. One new data helper is added because it doesn't exist yet:

```python
def get_variation_annotation(sqlite_conn, variation_id: str, move_index: int) -> Annotation | None:
    """Single-row lookup; None if unannotated. Existing get_variation_annotations()
    returns the whole-variation dict, which the per-position endpoint below
    doesn't need."""
```

New endpoints in `api/main.py`:

```
GET  /api/variations/{variation_id}/annotations/{move_index}
     -> Annotation | null

PUT  /api/variations/{variation_id}/annotations/{move_index}
     body: { glyph: string | null, comment: string | null }
     -> upserts via data.upsert_annotation(glyph=..., comment=...)

POST /api/variations/{variation_id}/annotations/{move_index}/ai-comment
     body: { fen: string, eval_cp: int | null, best_move_san: string | null, user_comment: string | null }
     -> calls claude_narrative.annotate_position(...), stores via
        data.upsert_annotation(ai_comment=..., ai_model=claude_narrative.MODEL),
        returns the updated Annotation
```

## Backend: mainline annotations

New migration `migrations/00XX_add_game_annotations.sql`:

```sql
CREATE TABLE IF NOT EXISTS game_annotations (
    id           TEXT    PRIMARY KEY,
    game_id      TEXT    NOT NULL,
    ply          INTEGER NOT NULL,
    glyph        TEXT,
    comment      TEXT,
    ai_comment   TEXT,
    ai_model     TEXT,
    generated_at TEXT,
    UNIQUE (game_id, ply),
    FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE CASCADE
);
```

A separate table rather than extending `variation_annotations` with
nullable dual-key columns: keeps `variation_annotations`' semantics (and
`variation_to_pgn`'s move-index-scoped annotation dict) unambiguous —
every reader of that table can keep assuming a row always belongs to
exactly one variation. The alternative (nullable `variation_id`, added
`game_id`/`ply` columns, a CHECK constraint enforcing exactly one key
scheme) was considered and rejected as a schema-level workaround for
what is, conceptually, a different kind of annotation.

New module `dashboard/data/annotations.py` (mainline annotations aren't
variation-scoped, so this logic doesn't belong in `variations.py`):

```python
def get_game_annotations(sqlite_conn, game_id: str) -> dict[int, Annotation]
def get_game_annotation(sqlite_conn, game_id: str, ply: int) -> Annotation | None
def upsert_game_annotation(sqlite_conn, game_id: str, ply: int, *,
                            glyph=None, comment=None, ai_comment=None, ai_model=None) -> None
```

Copied 1:1 from `variations.py`'s existing `get_variation_annotations`/
`upsert_annotation` SQL shape (same `ON CONFLICT ... DO UPDATE SET
... COALESCE(...)` upsert pattern), just re-keyed on `(game_id, ply)`
instead of `(variation_id, move_index)`. The shared `Annotation`
dataclass (currently has a `variation_id` field) gets that field made
optional so both paths can construct it — no fork of the dataclass.

New endpoints in `api/main.py`, mirroring the variation-scoped ones
exactly:

```
GET  /api/games/{game_id}/annotations/{ply}
PUT  /api/games/{game_id}/annotations/{ply}
POST /api/games/{game_id}/annotations/{ply}/ai-comment
```

## Backend: Claude key status

```
GET /api/settings/claude-key-status
    -> { "available": bool }
```

Thin wrapper around `claude_narrative.api_key_available()`. Exists only
so the React AnnotationPanel can hide/show the AI-assist button the way
the Streamlit `ai_col.caption(...)` fallback does, without a real
Settings page existing yet.

## Backend: error handling

Both `.../ai-comment` endpoints:

| Condition | Response |
|---|---|
| `claude_narrative.MissingApiKeyError` | `503 {"detail": str(e)}` — defensive; the endpoint must not trust that `claude-key-status` already hid the button client-side |
| any other exception | `502 {"detail": f"Claude API call failed: {e}"}` |
| success | `200`, updated `Annotation` |

Matches the Streamlit original's two `st.error(...)` branches
(`MissingApiKeyError` vs. generic `Exception`).

## Frontend

### `useClaudeKeyStatus()`

`frontend/src/hooks/useClaudeKeyStatus.ts`: `{ available: boolean }`.
Fetches once on mount, mounted once in `GameDetailPage`, passed down to
both `AnnotationPanel` instances. Fails closed (`available: false`) on
fetch failure — the safer default for a client-side gate that isn't
protecting anything security-sensitive on its own (the backend's own
`MissingApiKeyError` check is the real gate).

### `useVariationAnnotation(variationId, step)` / `useGameAnnotation(gameId, ply)`

`frontend/src/hooks/useVariationAnnotation.ts` and
`frontend/src/hooks/useGameAnnotation.ts`. Identical return shape so one
presentational component can consume either:

```ts
{
  annotation: Annotation | null
  loading: boolean
  save: (glyph: string | null, comment: string | null) => void
  askClaude: (evalCp: number | null, bestMoveSan: string | null, userComment: string | null) => void
  aiLoading: boolean
  aiError: string | null
}
```

Each hook refetches when its key changes (`variationId`+`step`, or
`gameId`+`ply`). `save`/`askClaude` optimistically merge the endpoint's
response into local state on success — no extra refetch round-trip,
matching the optimistic-update pattern already established in
`useVariation`. `useVariationAnnotation` treats a `null` `variationId`
(no variation created yet — first move not yet made) as "nothing to
annotate" and skips fetching.

### `useAnalysePosition` addition

Add `resultFen: string | null` to its returned shape — the FEN that
produced the current `result`, distinct from `result` itself. Needed so
callers (both `AnnotationPanel` mounts) can confirm the cached analysis
actually corresponds to the position they're annotating before using its
`eval_cp`/`best_move_san` in an AI-comment request, rather than silently
reusing a stale analysis left over from a different ply/step. No other
change to the hook's existing behavior.

### `AnnotationPanel` (shared, presentational)

`frontend/src/components/AnnotationPanel.tsx`:

```ts
interface AnnotationPanelProps {
  annotation: Annotation | null
  loading: boolean
  onSave: (glyph: string | null, comment: string | null) => void
  onAskClaude: (userComment: string | null) => void
  aiLoading: boolean
  aiError: string | null
  claudeKeyAvailable: boolean
}
```

- Glyph selector: 7-button toggle group (replaces Streamlit's
  `st.radio(horizontal=True)`), same 7 values.
- Comment `<textarea>`, local state seeded from `annotation?.comment`.
- "Save annotation" button calls `onSave(glyph, comment)`.
- AI-assist button: label is "Ask Claude to comment" or "Regenerate
  Claude comment" depending on whether `annotation?.ai_comment` is
  already set (matches Streamlit's `ai_label` logic exactly). Hidden
  behind a `claudeKeyAvailable` check; when false, renders the same
  "Add API key in Settings to enable AI annotation." caption text
  in its place.
- Renders `annotation.ai_comment` + `annotation.generated_at` below the
  buttons when present.
- Wrapped in a `<details>` disclosure, `open` by default only when
  `annotation` has any content (glyph, comment, or ai_comment) —
  matches `st.expander(expanded=bool(existing))`.

### `GameDetailPage` wiring

Two mount points:

- **Mainline**: always rendered below the existing eval graph, driven by
  `useGameAnnotation(gameId, ply)`.
- **Variation**: rendered inside the existing `variation.active` block,
  alongside `VariationPanel`/`SavedVariationsPanel`, driven by
  `useVariationAnnotation(variation.variationId, variation.step)`.
  Renders nothing while `variation.variationId` is still `null` (before
  the first move of a new branch creates the row).

Both mounts pass `onAskClaude` wired so that `evalCp`/`bestMoveSan` are
taken from the shared `useAnalysePosition()` instance only when its
`resultFen` matches the position currently being annotated (mainline
`mainlineFen`-at-`ply`, or `variation.currentFen`) — otherwise `null`,
matching Streamlit's own precise per-position session-state keying
(`live_detail__{gid}__{ply}`), which never leaks a stale analysis across
positions either.

## Frontend error handling

- Save failure: inline error text below the textarea; form stays
  editable. No toast-equivalent needed — low-stakes, matches the
  fire-and-forget nature of the Streamlit original's `st.toast`.
- Ask-Claude failure (`503`/`502`/network error): `aiError` renders
  inline where Streamlit used `st.error(...)`; button stays enabled for
  retry.
- `claude-key-status` fetch failure: fails closed (button hidden), per
  the "Frontend: useClaudeKeyStatus" section above.

## Testing

- `tests/unit/test_data_annotations.py` (new): `get_game_annotations`/
  `get_game_annotation`/`upsert_game_annotation`, plus `variations.py`'s
  new `get_variation_annotation` single-lookup.
- Migration test: `game_annotations` table shape (columns, unique
  constraint, FK-cascade-on-game-delete).
- `tests/integration/test_api_annotations.py` (new): get/put happy path
  for both variation- and game-scoped endpoints; `ai-comment` success +
  `MissingApiKeyError` (503) + generic exception (502) for both;
  `claude-key-status` true/false.
- `frontend/src/hooks/useVariationAnnotation.test.ts`,
  `useGameAnnotation.test.ts`, `useClaudeKeyStatus.test.ts`: fetch,
  refetch-on-key-change, save, askClaude transitions.
- `frontend/src/hooks/useAnalysePosition.test.ts`: add a case asserting
  `resultFen` tracks the FEN that produced `result`.
- `frontend/src/components/AnnotationPanel.test.tsx`: glyph select,
  comment save, AI button label swap (ask vs. regenerate), gated on
  `claudeKeyAvailable`, expanded-by-default only when existing content.
- `frontend/src/pages/GameDetailPage.test.tsx`: both mounts render;
  mainline mount always present; variation mount only while
  `variation.active` and only once `variationId` is non-null; each wired
  to its own hook instance and its own `resultFen`-gated eval context.

## Open items for the implementation plan to resolve

- Exact shared `Annotation` dataclass shape once `variation_id` is made
  optional (straightforward — add `| None`, update the two constructors
  — but not yet written).
- Whether the mainline `game_annotations` migration number continues the
  existing sequence or needs to account for any migrations landed on
  `main` since this worktree's `chess.db` was last refreshed — check the
  current head migration number at implementation time, not assumed
  here.
- Toggle-group visual treatment for the 7 glyphs (button row vs. a
  compact select) — default to a button row matching `VariationPanel`'s
  existing button styling, unless the implementation plan finds a reason
  to diverge.
