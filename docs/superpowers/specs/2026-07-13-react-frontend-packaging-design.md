# React frontend packaging design

Status: approved, not yet implemented. Branch: `worktree-frontend-spike`.

## Problem

`2026-07-12-frontend-rewrite-spike-design.md` proved FastAPI/uvicorn survive
PyInstaller freezing (`api_spike.spec`) and that the process model coexists
cleanly with `desktop_app.py`'s SIGTERM handling. It deliberately never
touched how the *built* React frontend (`frontend/dist`) actually gets
served in a packaged app: `api/main.py` today is a bare JSON API with a
wide-open CORS policy, meant only to be hit by `vite --port 5173` in dev.
There is no static-file serving, no SPA-fallback routing, and no step
wiring `npm run build` output into a PyInstaller spec. This design closes
that gap.

Scope decisions made explicitly, not assumed:
- This targets **real packaging now**, wired in **alongside** the existing
  Streamlit app, not deferred until the full 21-page migration finishes.
  Most nav destinations will still 404 — that's accepted, the goal is
  catching real packaging bugs early rather than in one big-bang cutover.
- `pywebview` stays. Its job (native window, own taskbar/dock identity, no
  browser chrome) was never Streamlit-specific and is unaffected by
  dropping Streamlit as the rendering layer.
- This must be a **pure React+Vite package with zero streamlit in its
  dependency closure** — not just "streamlit isn't rendered," but actually
  absent from the frozen bundle.

## Why streamlit currently leaks into the API's closure

Traced by reading every real import path `api/main.py` reaches (not
spot-checked):

1. `api/db.py` → `dashboard/_common.py`. That module imports `streamlit`
   at the top for exactly one reason: `get_connections()`'s
   `@st.cache_resource` decorator (plus its `st.error`/`st.stop()`
   disk-full message). But 10 of the `dashboard/data/*.py` modules
   (`matchups`, `game_endings`, `points`, `insights`, `analysis_batches`,
   `drills`, `prep`, `evolution`, `patterns`, `tactical`) also do
   `from _common import get_config` (or `get_duckdb_connection`/
   `get_sqlite_connection`) — plain functions with zero streamlit calls
   in their own bodies. Because Python executes a whole module on import,
   pulling in *any* name from `_common.py` drags in its top-level
   `import streamlit as st` too.
2. `api/main.py` → `import live_engine` (for the engine-status endpoint).
   Same shape: `LiveResult`/`EngineService`/`get_engine_service()`/
   `get_engine_status_summary()`/`batch_running()` have zero streamlit
   calls in their bodies except `get_engine_service()`'s
   `@st.cache_resource` decorator. The real Streamlit-only code in that
   file (`render_confirm_toggle`, `get_or_analyse_position` — actual
   `st.session_state`/`st.spinner`/`st.checkbox` calls) is separate and
   unused by the API.

`dashboard/narrative.py` and `dashboard/achievements.py` (also imported
directly by `api/main.py`) are already clean.

## Design

### 1. Decouple the data layer from streamlit (mechanical extraction)

- New root-level `connections.py` (same flat-module convention as
  `db.py`/`config.py`/`chess_utils.py`): holds the DuckDB per-PID-snapshot
  + locking machinery (`_LockedDuckDBConnection`, `_LockedDuckDBResult`,
  `_duck_snapshot_path`, `_cleanup_stale_snapshots`, `_build_duck_snapshot`,
  `_bundled_sqlite_extension_path`, `_load_duckdb_sqlite_extension`,
  `get_duckdb_connection`, `get_sqlite_connection`, `resolve_db_path`,
  `get_config`), plus a new plain, module-level-cached `open_connections()`
  — the un-decorated body of what's today `_common.get_connections()`.
- `dashboard/_common.py` shrinks to: import the above from `connections.py`,
  keep a 3-line `@st.cache_resource`-wrapped `get_connections()` that calls
  `connections.open_connections()` and preserves the exact current
  disk-full `st.error`/`st.stop()` UX, and keep the genuinely
  Streamlit-only view helpers (`game_labels`, `navigate_on_row_click`,
  `finding_chips_html`, `render_finding_actions`, `render_where_next`,
  `persist_filter`, `restore_filter_default`) untouched.
- The 10 `dashboard/data/*.py` modules change only their import source
  (`from _common import X` → `from connections import X`) — zero logic
  changes.
- `api/db.py` drops its `dashboard/_common` import and calls
  `connections.open_connections()` directly.
- Same split for `live_engine.py`: `LiveResult`, `EngineService`,
  `_service_started`, `get_engine_service()` (module-level cache instead
  of `@st.cache_resource`), `get_engine_status_summary()`,
  `batch_running()`, `_result_to_dict()` move to a new plain module (e.g.
  `dashboard/engine_status.py`). `dashboard/live_engine.py` keeps
  `render_confirm_toggle`/`get_or_analyse_position` (real Streamlit UI
  calls) and imports the extracted pieces so existing `*_view.py` callers
  don't change. `api/main.py` imports the new plain module directly.
- **Done bar**: full existing test suite still green after the split —
  this touches code the live Streamlit app depends on today, not just new
  code.

### 2. Frontend build & serving

- `frontend/dist/` stays gitignored — a build artifact, never committed.
- `api/main.py` gains a `StaticFiles` mount for `frontend/dist/assets` plus
  a catch-all SPA-fallback route serving `frontend/dist/index.html` for
  any non-`/api/*`, non-asset path (needed because `react-router-dom` does
  client-side routing — a hard refresh on `/patterns` must resolve to
  `index.html`, not 404). Registered *after* all `/api/*` routes so it
  never shadows them.
- Confirmed: asset paths in the current build output are already
  root-absolute (`/assets/...`), so serving from FastAPI's root needs no
  Vite `base` config change.
- The existing wildcard CORS middleware stays as-is for dev (`vite` on
  5173 talking to a standalone uvicorn on 8123 during ongoing page-by-page
  migration). In the packaged build everything is same-origin, so CORS is
  simply unused there — no dev workflow regresses.

### 3. Process/launcher model

- New root-level entry point `react_desktop_app.py` (mirrors
  `desktop_app.py`'s role as `chesswright.spec`'s entry point), becomes
  `chesswright-react.spec`'s target. Graduates `api/spike_launcher.py`'s
  already-proven subprocess pattern into a real launcher:
  - Picks a free port, re-invokes its own frozen executable with
    `--api-server-mode --port N` (the fork-bomb-safe dispatch
    `spike_launcher.py` already validated — reused verbatim).
  - Waits for the server to answer, then opens a `pywebview` window at
    `http://127.0.0.1:<port>/` — same shape `desktop_app.py` already uses
    for Streamlit, different port/process underneath.
  - On window close, terminates the subprocess via the same SIGTERM-safe
    path `desktop_app.py` already proved correct (no orphaned processes).

### 4. Packaging

- New `chesswright-react.spec`, graduated from `api_spike.spec`: same
  `BACKEND_MODULES`/`datas` list, plus `frontend/dist` added as a `datas`
  entry (mirrors the existing `config.yaml`/`migrations/` bundling
  precedent already in `api_spike.spec`). Kept as a **third**, isolated
  spec alongside `chesswright.spec`/`chesswright-pro.spec` — same
  precedent this repo already has for keeping specs from silently
  colliding (see `chesswright_pro_pyinstaller_spec_gotcha` project
  memory). Zero risk to the existing production `chesswright.spec`/
  `build.yml` — nothing about the Streamlit build changes.
- The `collect_all(...)` loop drops `"streamlit"` entirely, now that
  section 1's decoupling removes it from the real import closure — the
  one item this design actually changes from `api_spike.spec`'s list;
  everything else (fastapi, uvicorn, duckdb, pandas, chess, etc.) stays as
  already proven.
- Entry point changes from `api/spike_launcher.py` to
  `react_desktop_app.py`.

### 5. Build pipeline

- New `scripts/build_react_app.py` (matches the existing `scripts/`
  convention — all Python), running `npm ci && npm run build` in
  `frontend/` then `pyinstaller chesswright-react.spec --noconfirm`.
- Local-only for now — **not** wired into
  `.github/workflows/build.yml`. This path is an internal/parallel proof
  (most nav destinations still 404), not a real release artifact yet.
  Adding a CI matrix job is a clean, separable follow-up once enough
  pages are ported to matter.

## Known gaps, explicitly not resolved by this design

- Windows/macOS: pywebview+PyInstaller+FastAPI is still Linux-only proven
  — inherited unchanged from the spike's own carried-forward risk.
- The gi/GTK-bundling and DuckDB-extension-load CI verification steps that
  protect `chesswright.spec` builds don't automatically cover a future
  `chesswright-react.spec` CI job — they'd need to be copied over if/when
  this graduates to CI.
- 20 of 21 pages have no React implementation yet; their nav destinations
  404 client-side/API-side. Not a regression — pre-existing, ongoing
  migration work, out of scope here.
