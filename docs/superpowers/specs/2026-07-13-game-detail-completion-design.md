# Game Detail Completion — Roadmap + Slice 1 Design

Status: approved by user 2026-07-13
Branch: worktree-frontend-spike

## Context

Game Detail's core viewing (header, badge chips, read-only board, move
list, win-probability eval graph, all synced on one shared `ply` state)
shipped and was live-verified this session — see
`docs/frontend_migration_status.md`'s 🟡 row and the design doc at
`docs/superpowers/specs/2026-07-13-game-explorer-detail-design.md`. That
doc's own Non-goals section deferred five pieces: variation mode,
per-position annotations, saved-variations management, Board Chat, and
the Pro-gated Game Report.

This doc does two things: (1) sequences those five pieces (plus a sixth,
previously-invisible piece — on-demand live engine analysis — surfaced
during this brainstorm) into dependency-ordered slices, and (2) designs
the first slice in full.

**Standing directive that shaped this design** (user, 2026-07-13): the
Streamlit source (`dashboard/game_detail_view.py`) is a reference for
*business logic and requirements only*, not an architecture to replicate.
Its `st.session_state`/`st.rerun()`/`@st.fragment` control flow, and its
custom-component postMessage bridge (nonce staleness comparisons, stable
widget keys to dodge iframe remounts, `_load_ply_key` indirection around
Streamlit's script-rerun ordering) are all workarounds for limitations
specific to Streamlit's execution model. None of them apply to React
(real component state, direct event handlers, no rerun/remount model) or
FastAPI (real REST endpoints, no page-script re-execution). Every slice
below extracts *what* the Streamlit code does and redesigns *how* freshly
for this stack.

## Goals

Produce a dependency-ordered build sequence for the remaining Game Detail
work, and a full design for the first slice.

## The dependency graph

Found by reading `_render_board_and_chat`, `_render_annotation_panel`,
`_render_saved_variations`, and `_render_game_report` in
`dashboard/game_detail_view.py`, plus `chesswright_pro/game_report.py` and
`chesswright_pro/board_chat.py` in the private repo:

- **Live engine analysis** (an "Analyse position" action + eval/PV
  display) — no dependencies. Not shipped at all yet, even for the
  already-live core-viewing mainline ply.
- **Chessboard arrow/highlight display** — a small, additive prop
  extension to the existing read-only `Chessboard.tsx`. No dependencies.
- **Interactive board + Variation mode** (move input, branching,
  persistence) — needs both of the above (the Streamlit version shows
  engine-best-move arrows and gates its "Analyse position" flow inline
  during variation play).
- **Saved variations list** — needs Variation mode (Load re-enters it).
- **Annotations** — needs Variation mode: in the current schema,
  annotations key off `variation_id` + `step`, not raw game moves — there
  is no mainline-move annotation path today. Its optional "Ask Claude to
  comment" button is gated only on Claude-API-key availability
  (`claude_narrative.annotate_position`, a **core-repo**, non-Pro
  function) — not on Pro license.
- **Board Chat** (Pro) — only needs the arrow/highlight display prop, not
  Variation mode or live engine analysis (`board_chat.render()`'s
  signature takes just `active_fen`). Discovered to be the most complex
  remaining piece: a full agentic tool-use loop (4 tools, multi-turn
  conversation state, `live_engine`/`ai_coach` integration), living
  entirely in the private `chesswright-pro` repo.
- **Game Report** (Pro) — zero dependencies structurally, but not the
  thin gate-and-container it first appeared to be: real generation logic
  (phase-stats query, notable-moments extraction, a Claude API call,
  Markdown + HTML export) lives entirely in
  `chesswright_pro/game_report.py`.

Both Pro features assume a working "add your Claude API key" flow
(Settings, still ⛔ unbuilt in React) and are cross-repo (their real logic
lives in the private repo, which has no FastAPI-shaped entry point yet —
only Streamlit-rendering functions). That pushes both later than their
zero-dependency status alone would suggest.

## The slice sequence (approved)

1. **Board-interaction infra**: live engine analysis + Chessboard
   arrow/highlight display, combined (both small, both standalone, both
   feed slice 2). Full design below.
2. **Interactive board + Variation mode** — the trunk. Biggest slice;
   single-repo (core), no Claude API dependency.
3. **Saved variations** — small, needs slice 2's `variation_id`s.
4. **Annotations** — small-medium, needs slice 2; its optional AI-assist
   button needs Claude-API-key availability (core-repo check) but is not
   Pro-gated.
5. **Game Report** (Pro) — cross-repo; needs a new, non-Streamlit-shaped
   entry point in `chesswright_pro/game_report.py` (the existing
   `render_game_report()` is Streamlit-coupled and not directly callable
   from FastAPI).
6. **Board Chat** (Pro) — cross-repo, most complex; same
   non-Streamlit-entry-point need in `chesswright_pro/board_chat.py`.

Rationale: free-tier, single-repo work first; both Claude/Pro-dependent
features pushed to the end, ordered by their own complexity (Game Report
before Board Chat) rather than forced by any hard dependency.

## Non-goals for this doc

- Designing slices 2-6 in detail — each gets its own design pass when its
  turn comes, per the `port-view-slice` skill's recipe.
- Any change to the private `chesswright-pro` repo. Slices 5-6 will need
  a new non-Streamlit entry point there; that's flagged as an open item,
  not designed here.
- A Settings/API-key entry page in React — real gap for slices 4-6, but
  out of scope for this doc.

## Slice 1 design — Board-interaction infra

### Part A: `POST /api/analyse-position`

New stateless endpoint in `api/main.py`. Body `{fen: string}`.

Resolution order (business logic carried over from
`live_engine.get_or_analyse_position`, control flow redesigned):
1. DB cache hit (`data.get_position_analysis`) → return immediately.
2. Miss, cloud eval enabled in config → try
   `lichess_cloud_eval.fetch_cloud_eval(fen)`; on a hit, store
   (`data.store_position_analysis`) and return.
3. Miss, no cloud result → local engine
   (`engine_status.get_engine_service()`), blocked if
   `joblock.status()` shows the batch worker alive, or if no engine is
   configured; on success, store and return.

All three of `engine_status.py`, `data.get_position_analysis`/
`store_position_analysis`, and `lichess_cloud_eval.fetch_cloud_eval` are
already Streamlit-free (confirmed by reading them) and get reused as-is,
unmodified — only the *caller* (a FastAPI endpoint instead of
`live_engine.py`'s `st.session_state`/`st.spinner`/`st.caption`-laced
wrapper) is new.

Response:
```json
{
  "status": "ok" | "no_engine" | "batch_running" | "analysis_failed",
  "result": {
    "eval_cp": int | null,
    "eval_mate": int | null,
    "best_move_san": string | null,
    "pv": string[],
    "depth": int,
    "source": "lichess_cloud" | "live"
  } | null
}
```
`status` is a real, machine-readable field — replaces Streamlit's ad-hoc
`st.caption("Stockfish not found…")`/`st.caption("Batch analysis
running…")` side-channel; the React side owns all copy for each status.

No server-side request-scoped caching — the DB tier is the persistence
layer (already exists), and per-call is genuinely stateless. No
`live_result__{fen}` session-key equivalent on the backend.

### Part B: `useAnalysePosition()` hook

`frontend/src/hooks/useAnalysePosition.ts`:
```ts
{ analyse(fen: string): void; result: AnalysisResult | null; status: AnalysisStatus; loading: boolean }
```
Internally memoizes results per-FEN in a plain in-memory `Record<string,
AnalysisResult>` (or `Map`) held in the hook's own state — the React-native
equivalent of "don't re-fetch a position already analysed this session,"
achieved with real state instead of a session-key naming convention.
`analyse(fen)` is called explicitly (e.g. on a button click); no polling.

### Part C: Chessboard arrow/highlight props

Extend `frontend/src/components/Chessboard.tsx`'s props (additive,
backward-compatible — existing core-viewing call sites pass neither and
are unaffected):
```ts
arrows?: Array<{ from: string; to: string; color?: string }>
highlightedSquares?: Record<string, React.CSSProperties>
```
`arrows` threads straight into `react-chessboard`'s own native
`customArrows` prop. `highlightedSquares` merges into the existing
`customSquareStyles` object alongside the current last-move highlighting.

No nonce/staleness handling is needed anywhere in this — that machinery
in the Streamlit version existed solely to detect a stale result crossing
the custom component's postMessage/iframe boundary. A React prop set from
local component state cannot go stale that way; whatever produces
arrows/highlights later (slice 2's engine-best-move suggestion, slice 6's
Board Chat tool calls) just sets normal state that flows straight down.

### A real, live-verifiable deliverable

Rather than shipping Parts A-C as inert plumbing, this slice adds an
"Analyse position" button to the **already-shipped** core Game Detail
page (`GameDetailPage.tsx`), below the eval graph: calls
`useAnalysePosition().analyse(currentFen)`, displays eval/PV/depth on
success, shows the right message per `status` on failure, and — using
Part C — draws the engine's suggested move as an arrow on the board via
`best_move_san` (parsed the same way `GameDetailPage.tsx` already parses
SAN for last-move highlighting: `new Chess(fen).move(san)` → `{from, to}`).

### Error handling

| `status` | React behavior |
|---|---|
| `no_engine` | "Stockfish not found — configure it in Settings." (references the page by name even though it isn't built yet, matching the Streamlit original's own copy) |
| `batch_running` | Button disabled, "Batch analysis running — live engine paused until it finishes." |
| `analysis_failed` | Generic retry-safe message; button stays enabled |
| `ok` | Render eval/PV/depth + arrow |

### Testing

- `tests/integration/test_api_analysis.py` (new): cache-hit, cloud-eval
  hit, local-engine success, no-engine, batch-running, and
  analysis-exception branches, mocking `engine_status`/
  `lichess_cloud_eval`/`joblock` — matches the one-file-per-section
  convention (`test_api_games.py`, `test_api_overview.py`).
- `frontend/src/hooks/useAnalysePosition.test.ts`: loading/result/status
  transitions, per-FEN memoization.
- `frontend/src/components/Chessboard.test.tsx` additions: `arrows` prop
  reaches `react-chessboard`'s `customArrows`; `highlightedSquares` merges
  into `customSquareStyles` alongside last-move highlighting.
- `GameDetailPage.test.tsx` addition: Analyse-position button drives the
  hook, renders each `status` correctly, draws the arrow on success.

## Open items for the implementation plan to resolve

- Exact `color` default for the engine-best-move arrow (reuse the
  existing `theme.POSITIVE` copper/positive tone already established
  elsewhere, per the Streamlit version's `f"{theme.POSITIVE}90"`).
- Whether `useAnalysePosition`'s per-FEN cache should be scoped to the
  hook instance (reset on `GameDetailPage` unmount, i.e. per game) or
  lifted higher — default to hook-scoped unless a real cross-page reuse
  case shows up.
- Confirm `config.load_config()`'s `interactive_engine.use_lichess_cloud_eval`
  flag reads correctly from a FastAPI process (no Streamlit-specific
  config-loading path expected, but not yet directly verified from `api/`).
