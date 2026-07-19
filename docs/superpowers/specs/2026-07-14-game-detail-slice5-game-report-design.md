# Game Detail Slice 5 — Game Report

Status: approved by user 2026-07-14
Branch: worktree-frontend-spike

## Context

`docs/superpowers/specs/2026-07-13-game-detail-completion-design.md`
sequenced the remaining Game Detail work into six slices. Slices 1-4
(board-interaction infra, interactive board + variation mode, saved
variations, annotations) are shipped. This slice is next: **Game
Report** — the first Pro-gated feature ported to the React/FastAPI
frontend. It's a structured, Claude-generated phase-by-phase breakdown
of one game, exportable as Markdown and HTML.

The Streamlit reference (`dashboard/game_detail_view.py`'s
`_render_game_report`, `chesswright-pro/chesswright_pro/game_report.py`'s
`render_game_report`) is a source for business logic and requirements
only, per the standing directive — its `st.spinner`/`st.button`/
`st.rerun`/`st.download_button` control flow does not carry over.

**Cross-repo scope confirmed this session:** the actual report-generation
logic (phase-stats query, notable-moments selection, the Claude prompt
call) lives in the private `chesswright-pro` repo specifically so the
public core repo "never ships that logic, only the fact that it exists"
(the existing file's own docstring). `render_game_report()` is
Streamlit-coupled and not directly callable from FastAPI, so this slice
adds a new, parallel, Streamlit-free entry point to
`chesswright_pro/game_report.py` rather than moving the logic into the
public repo. This preserves the existing IP boundary at the cost of
touching two repos.

No API surface exists yet on the React/FastAPI side for Pro-gating at
all — this slice also establishes that pattern (`GET /api/pro-status` +
`useProStatus()`), reusing the already-Streamlit-free
`dashboard/pro_gate.is_pro_active()` directly.

## Goals

- Let the user generate (and regenerate) a Claude-written Game Report
  for the current game, gated on Pro license + Claude API key
  availability.
- Show the cached report (if one exists) with its generation timestamp.
- Let the user download the report as Markdown or as a standalone HTML
  file, matching the Streamlit original's two download buttons and
  filename scheme.
- Establish the general Pro-gating pattern (`pro-status` endpoint +
  hook) other Pro features (Board Chat, slice 6) will reuse.

## Non-goals

- Board Chat (slice 6) — separate, much larger slice.
- Any change to `render_game_report()`'s Streamlit UI — it keeps serving
  the Streamlit app unchanged; this slice only adds a sibling entry
  point.
- Tournament-prep / weekly HTML reports (Phase 7 territory) — unrelated
  report types, not part of Game Detail.
- A generic Pro nav/route-gating mechanism for whole pages — this slice
  only gates a panel embedded in an already-reachable page. Pro-gating
  entire pages/routes is deferred until a Pro feature actually needs its
  own page (e.g. Board Chat, if it ends up on its own route).

## Backend: `chesswright-pro` repo change

New function in `chesswright_pro/game_report.py`, alongside the
existing (unchanged) `render_game_report`:

```python
def generate_report(sqlite_conn, game_id: str, header, moves: pd.DataFrame) -> str:
    """Streamlit-free entry point for the FastAPI port. Runs the same
    phase-stats + notable-moments + Claude prompt sequence as
    render_game_report()'s button handler, caches via data.save_narrative,
    and returns the report text."""
    cfg = get_config()
    mid_ply = cfg.get("analytics", {}).get("middlegame_ply", 24)
    phase_stats = _phase_stats_text(sqlite_conn, game_id, mid_ply)
    notable = _notable_moments_text(moves, header.opponent_name)
    num_plies = int(moves.ply.max())
    report_text = claude_narrative.generate_game_report(header, num_plies, phase_stats, notable)
    data.save_narrative(sqlite_conn, "game_report", game_id, report_text, claude_narrative.MODEL)
    return report_text
```

- `_phase_stats_text` / `_notable_moments_text` are reused unchanged —
  already Streamlit-free; only `render_game_report`'s button handler has
  the UI coupling.
- Propagates whatever `claude_narrative.generate_game_report` raises
  (`MissingApiKeyError` or a generic exception) — the FastAPI caller
  translates those to 503/502.

## Backend: FastAPI endpoints (`api/main.py`, public repo)

```python
@app.get("/api/pro-status")
def pro_status():
    return {"active": pro_gate.is_pro_active()}

@app.get("/api/games/{game_id}/report")
def get_game_report(game_id: str):
    sqlite_conn, _ = get_db_connections()
    cached = data.get_cached_narrative(sqlite_conn, "game_report", game_id)
    if not cached:
        return {"report_text": None, "generated_at": None}
    report_text, generated_at = cached
    return {"report_text": report_text, "generated_at": generated_at}

@app.post("/api/games/{game_id}/report/generate")
def generate_game_report(game_id: str):
    if not pro_gate.is_pro_active():
        raise HTTPException(status_code=403, detail="Pro is not licensed")
    try:
        from chesswright_pro import game_report
    except ImportError:
        raise HTTPException(status_code=501, detail="chesswright_pro not installed")

    sqlite_conn, _ = get_db_connections()
    try:
        header, moves = data.get_game_detail(sqlite_conn, game_id)
    except IndexError:
        raise HTTPException(status_code=404, detail="Game not found")
    try:
        game_report.generate_report(sqlite_conn, game_id, header, moves)
    except claude_narrative.MissingApiKeyError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Claude API call failed: {e}")

    report_text, generated_at = data.get_cached_narrative(sqlite_conn, "game_report", game_id)
    return {"report_text": report_text, "generated_at": generated_at}

@app.get("/api/games/{game_id}/report/download.md")
def download_game_report_md(game_id: str):
    # 404 if no cached report. Content-Disposition attachment,
    # filename = chesswright_report_{opponent}_{utc_date}.md — same
    # scheme as Streamlit's report_filename.

@app.get("/api/games/{game_id}/report/download.html")
def download_game_report_html(game_id: str):
    # 404 if no cached report. Renders via
    # report_html.render_report_html("game_report.html", ...) with the
    # same context kwargs as the Streamlit version. Content-Disposition
    # attachment, filename = report_filename with .html.
```

Both download endpoints follow the exact `Response(content=...,
media_type=..., headers={"Content-Disposition": ...})` precedent already
used by `GET /api/variations/{variation_id}/pgn` — no new response
pattern introduced. `pro_gate` and `data.get_cached_narrative` /
`report_html` are plain-Python, already importable from `api/main.py`
without any Streamlit dependency.

## Frontend

**New hooks:**
- `useProStatus()` — mirrors `useClaudeKeyStatus`, fetches
  `/api/pro-status` → `{ active, loading }`.
- `useGameReport(gameId)` — fetches `/api/games/{gameId}/report` on
  mount/gameId-change (`reportText`, `generatedAt`, `loading`); exposes
  `generate()` which POSTs `/generate`, tracking `generating` + `error`
  state (error message taken from the HTTP response body, matching
  `AnnotationPanel`'s `aiError` pattern).

**New dependency:** `react-markdown` — the report body needs real
Markdown rendering (headers, lists, bold); nothing this size exists in
the app yet. Default config doesn't render raw HTML, so no XSS concern
from AI-generated report content.

**`GameReportPanel` component** (mirrors `_render_game_report`'s
container 1:1):
- Bordered container, "Game Report" title + the same caption copy.
- `useProStatus()`, `useClaudeKeyStatus()`, and `useGameReport(gameId)`
  are all called unconditionally (hooks-rules-safe), same as slice 4's
  per-position hooks.
- `!proActive` → upsell info box with the Gumroad link, same copy as
  Streamlit; nothing else renders.
- `proActive && !claudeKeyAvailable` → "Add your Anthropic API key on
  the Settings page to generate reports."
- Otherwise: cached report (if any) rendered via `<ReactMarkdown>`,
  "Generated {generatedAt}" caption, Generate/Regenerate button (label
  swap on `reportText` presence, like the AI-annotate button), inline
  error text on failure, and — once a report exists — two `<a
  href=... download>` links for `.md`/`.html` (same anchor-download
  pattern as `SavedVariationsPanel`'s PGN link, with the matching "Saves
  to your Downloads folder as..." captions).

**Wiring into `GameDetailPage`:** one mount, mainline-only, at the
bottom of the page (same position as Streamlit's
`_render_game_report(...)` call) — no variation-mode equivalent, since a
report is whole-game-scoped.

## Frontend error handling

- `403` (not licensed) / `501` (chesswright_pro not installed) on
  generate → both surface as the upsell/error state the panel already
  shows for "not licensed" (a `501` in practice means Pro is licensed
  but the package is broken — rare, matches Streamlit's `st.error("Pro
  is licensed but the chesswright_pro package couldn't be imported...")`
  text).
- `503` (missing API key) / `502` (Claude call failed) → inline error
  text below the button, button stays enabled for retry — same shape as
  `AnnotationPanel`'s ask-Claude error handling.
- Download endpoints 404 (no cached report yet) → download links are
  only rendered once `reportText` is truthy, so this is unreachable from
  the UI in normal use; the endpoint still returns a real 404 for direct
  URL access.

## Testing

- `chesswright-pro/tests/test_game_report.py`: new `generate_report()` —
  happy path (calls `claude_narrative.generate_game_report`, saves via
  `data.save_narrative`, returns text), `MissingApiKeyError` propagation.
- `tests/integration/test_api_game_report.py` (public repo, new):
  `pro-status` true/false; `GET report` empty/cached; `POST generate`
  happy path + 403 (not licensed, monkeypatch `pro_gate.is_pro_active`)
  + 501 (mock `ImportError`) + 503/502; both download endpoints,
  including 404-when-uncached.
- `frontend/src/hooks/useProStatus.test.ts`, `useGameReport.test.ts`:
  fetch, generate transitions, error states.
- `frontend/src/components/GameReportPanel.test.tsx`: all 4 gate states
  (not-licensed / no-key / empty-cached / has-cached), button label
  swap, download links only when `reportText` present.
- `frontend/src/pages/GameDetailPage.test.tsx`: panel mounted once,
  mainline-only.

## Open items for the implementation plan to resolve

- Exact `report_filename`/`html_filename` construction — port verbatim
  from Streamlit's `_render_game_report`/`render_game_report`
  (`chesswright_report_{opponent}_{utc_date}.{ext}`, spaces replaced
  with underscores in the opponent name).
- Whether `chesswright-pro`'s test suite needs its own conftest fixture
  for a mock `sqlite_conn`/`header`/`moves`, or can reuse an existing one
  — check at implementation time.
- Confirm the `chesswright-pro` local dev install (editable install?)
  used by this worktree actually round-trips a new function without a
  reinstall step — check at implementation time rather than assuming.
