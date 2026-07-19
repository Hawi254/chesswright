# Largest-File Modularization — Design

Status: approved by user, pending self-review + doc-review gate
Date: 2026-07-17
Branch: `feature/eval-dedup-cache` (current branch)

## Context

A file-size survey of this branch (excluding tests, `.venv`, and the gitignored
`worktree-frontend-spike` copy) found eleven non-test files over 550 lines, topped
by `dashboard/data/patterns.py` at 1366 lines. The Streamlit frontend is being
replaced page-by-page by the React/Vite rewrite on `worktree-frontend-spike`
(`streamlit_frontend_dropped_2026-07-13`), so `dashboard/*_view.py` files are
explicitly out of scope for this pass — refactoring code that's slated for
deletion is wasted effort. This design instead targets the six largest files
that survive the migration: the shared data-query layer, the core analysis
backend, and the desktop launcher.

Two of the six files were checked against `worktree-frontend-spike`'s FastAPI
layer and confirmed durable: `dashboard/data/*.py` is reachable from
`api/shared_data.py` via `import data`, resolved at runtime because
`tests/conftest.py` (and, by the same mechanism, the app's own bootstrap) puts
`dashboard/` on `sys.path`, making `dashboard/data` importable as a top-level
`data` package. The other four (`analytics.py`, `worker.py`,
`dashboard/claude_narrative.py`, `desktop_app.py`) have no Streamlit or React
dependency at all — they're pure backend/CLI/launcher code.

## Goals

- Split each of the six files into smaller, single-topic modules with no
  behavior change — same public functions, same signatures, same call sites.
- Preserve every existing import path (`patterns.get_castling_performance(...)`,
  `from worker import lines_payload_from_engine_lines`, etc.) so no caller
  outside these six files needs to change.
- Preserve every CLI/packaging invocation that depends on a literal file path:
  `python3 worker.py`, `python3 analytics.py`, `python3 desktop_app.py`, and
  `chesswright.spec`'s `Analysis(["desktop_app.py"])` entry point.
- Land as six independent, separately-tested, separately-committed units (one
  file per unit), not one large mixed diff.

## Non-goals (explicit)

- **No `dashboard/*_view.py` changes.** Streamlit views are being deleted
  page-by-page as the React migration proceeds; refactoring them now is
  work that gets thrown away.
- **No `dashboard/data/points.py` or `dashboard/data/openings.py`.** Both sit
  just under the 600-line threshold and have real internal seams (ledger vs.
  drill-position queries; move-history vs. engine-backed position analysis),
  but were explicitly deferred to keep this pass to the clearest six offenders.
- **No behavior changes, no bug fixes folded in**, even if one is noticed while
  moving code — file a separate note instead of fixing it inline.
- **No reconciliation with `worktree-frontend-spike`.** That branch appears to
  be independently extracting `dashboard/_common.py`'s connection logic into a
  top-level `connections.py` (per prior-session memory of a "connections.py
  first-request migration race" bug). This design does not attempt to name
  things to match that branch or otherwise pre-merge the two efforts — that's
  a separate concern for whoever eventually merges the branches.

## Architecture: two tiers

**Tier 1 — true packages (`foo.py` → `foo/__init__.py` + submodules).** Safe
for files that are only ever *imported*, never executed by path. All three are
already bundled as part of the `dashboard/` directory in `chesswright.spec`
(`datas += [(str(ROOT / "dashboard"), "dashboard")]`), which is already proven
to bundle a directory tree recursively — no spec change needed.

**Tier 2 — flat sibling modules, entry file stays a real `.py`.** Required for
`worker.py`, `analytics.py`, and `desktop_app.py`, because each is executed
directly by file path, not just imported:
- `python3 worker.py` and `python3 analytics.py` are documented, tested CLI
  entry points — `tests/integration/test_analysis_jobs_view.py` asserts the
  literal string `"python3 worker.py"`, and it appears verbatim in the app's
  own UI copy (`dashboard/analysis_jobs_view.py`).
- `python3 desktop_app.py` is a documented dev launch command, and
  `chesswright.spec`'s `Analysis(["desktop_app.py"])` requires a literal file
  at that path — PyInstaller's Analysis phase cannot target a directory here.
- `chesswright.spec`'s `BACKEND_MODULES` list bundles `worker.py`/`analytics.py`
  and everything they import (confirmed: `db.py`, `chess_utils.py`, etc. are
  already individually listed there) as loose data files by filename, because
  PyInstaller's static analysis never traces this graph (it's reached only via
  `dashboard/app.py`'s dynamic, path-based load through Streamlit's bootstrap,
  which Analysis can't follow). Any new sibling module `worker.py`/`analytics.py`
  imports needs the same treatment.
- `desktop_app.py` itself, by contrast, **is** the literal script PyInstaller's
  Analysis traces — anything it imports normally (not by dynamic path) is
  auto-discovered and compiled in without a spec change.

**Rule for both tiers, to avoid circular imports:** submodules never import
back through their own package's `__init__.py` (or, for Tier 2, back through
the slim entry file) — they import from each other or from a leaf module
(`_shared.py`, `client.py`) directly. `__init__.py`/the slim entry file only
imports *from* submodules, never the reverse.

## Per-file breakdown

### Tier 1

**`dashboard/data/patterns.py`** (1366 lines, ~35 functions, already divided by
comment banners) → `dashboard/data/patterns/`:
- `_shared.py` — `SHARPNESS_BUCKETS`, `PIECE_ORDER`, `PIECE_NAME` (the only
  constants used across more than one topic section)
- `time_and_session.py` — time-pressure/session/day-hour functions
- `material_structure.py` — material-structure and bishop-ending functions
- `piece_movement.py` — piece-movement/castling functions
- `rating_and_clock.py` — favorite/underdog and clock-pressure functions
- `events.py` — event-type/tournament breakdown functions
- `position_character.py` — board-position-character/squares functions
- `correlations.py` — sharpness/thinking-time/instant-move correlation functions
- `__init__.py` — re-exports every public name from the above

**`dashboard/claude_narrative.py`** (580 lines) → `dashboard/claude_narrative/`:
- `client.py` — `MODEL`, `PERSONA_AND_STYLE`, `MissingApiKeyError`,
  `api_key_available`, `contextualize`, `converse`, the two completeness-note
  helpers
- `game_narrative.py` — rich-narrative and game-report prompt/generate pairs,
  `explain_engine_move`, `annotate_position`
- `commentary.py` — opening and opponent commentary prompt/generate pairs
- `insights_and_coaching.py` — insights-synthesis and coaching-recommendation
  prompt/generate pairs
- `ask.py` — the Ask-page prompt/generate pair
- `__init__.py` — re-exports everything

**`dashboard/_common.py`** (558 lines) → split, not a package:
- New `dashboard/db_connections.py` — `_LockedDuckDBResult`,
  `_LockedDuckDBConnection`, the snapshot-isolation functions, extension
  loading, `get_duckdb_connection`, `get_sqlite_connection`, `resolve_db_path`,
  `get_config`. No `streamlit` import.
- `dashboard/_common.py` shrinks to the genuinely Streamlit-coupled remainder:
  `get_connections()` (thin `@st.cache_resource` wrapper calling into
  `db_connections`, plus its disk-full guard), `game_labels`,
  `navigate_on_row_click`, the finding-chip rendering block
  (`finding_chips_html`, `render_finding_actions`, `render_where_next`), and
  filter persistence (`persist_filter`/`restore_filter_default`). Re-exports
  `db_connections`'s names so `tests/unit/test_duck_snapshot.py` and
  `tests/unit/test_duckdb_extension_loading.py` (the only two files that
  import `_common`'s connection functions today) need no changes.

### Tier 2

**`worker.py`** (727 lines) → new siblings `worker_engine.py` (engine
discovery/validation/config), `worker_eval_cache.py` (cached-eval
fetch/store, `score_to_fields`, `lines_payload_from_engine_lines`,
`REUSE_EVAL_MAX_PLY`), `worker_analysis.py` (`fetch_next_game`,
`write_move_and_lines`, `analyze_game`), `worker_calibration.py`
(`calibrate`). `worker.py` itself keeps `now_iso`, `parse_duration`, `run()`,
`main()`, the `if __name__ == "__main__":` block, and imports + re-exposes
everything above (`worker.score_to_fields(...)`,
`from worker import lines_payload_from_engine_lines` keep working). Add the
four new siblings to `chesswright.spec`'s `BACKEND_MODULES`.

**`analytics.py`** (933 lines) → new siblings `analytics_reports.py` (all
`report_by_*`/`acpl_and_blunder_rate`/`classification_breakdown`/`fmt_row`,
plus `BASE_FILTER`/`SESSION_JOIN`/`SESSION_SECTIONS`), `analytics_session.py`
(`compute_session_context`, `ensure_session_ctx`), `analytics_structure.py`
(structure-context/middlegame/endgame functions, `STRUCTURE_SECTIONS`),
`analytics_position_caches.py` (the three `ensure_*_cache`/`ensure_*_stats`
functions). `analytics.py` itself keeps `_open_write_connection`, `run()`, the
`if __name__ == "__main__":` block, and re-exports the rest. Same
`BACKEND_MODULES` addition.

**`desktop_app.py`** (569 lines) → new siblings `desktop_preflight.py`
(`run_check_imports`, `run_preflight_imports`, `_sse42_confirmed`,
`_preflight_cmd`, `check_cpu_compat`, `check_webview2`,
`PREFLIGHT_MODULES`), `desktop_server.py` (`free_port`, `wait_for_server`,
`run_server_mode`, `launch_server_subprocess`). `desktop_app.py` itself keeps
`resource_dir`, `ensure_user_data`, the `NativeApi` class, `run_worker_mode`,
`main()`, and the module-level constants (`USER_DATA_DIR`, `RELEASES_URL`,
`ISSUES_URL`), importing the two new siblings normally. No spec change.

## Testing

The existing unit/integration suite is the safety net: every public call site
is preserved via re-exports, so no test should need to change. Run the full
suite after each file's split before starting the next one (six separate
verification passes, six separate commits). Two spots get an explicit,
individual check rather than relying on the general suite run:
- `tests/integration/test_analysis_jobs_view.py`'s two assertions on the
  literal string `"python3 worker.py"` — confirms the Tier 2 approach for
  `worker.py` didn't change user-facing help text.
- `tests/unit/test_duck_snapshot.py` and
  `tests/unit/test_duckdb_extension_loading.py` — confirms
  `dashboard/_common.py`'s re-export of `db_connections` names works.

`chesswright.spec` itself is not rebuilt/tested as part of this pass (no
pilot build scheduled) — the `BACKEND_MODULES` additions for `worker.py`'s and
`analytics.py`'s new siblings are made in the spec file but verified only by
inspection, not a real PyInstaller build, unless the user asks for one.

## Sequencing

Six independent units, each: split the file, run the full test suite, commit.
Suggested order, easiest/highest-value first: `patterns.py` (biggest win, purely
mechanical) → `claude_narrative.py` → `_common.py` (the one genuine
durable/UI split) → `worker.py` → `analytics.py` → `desktop_app.py` (the two
`BACKEND_MODULES`-touching ones last, since they're the only ones with a
packaging-adjacent change to double-check).
