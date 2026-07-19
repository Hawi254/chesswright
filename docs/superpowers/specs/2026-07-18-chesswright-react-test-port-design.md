# Porting the Python test suite to chesswright-react

## Context

The chesswright-react repo split (`docs/superpowers/plans/2026-07-18-chesswright-react-repo-split-implementation-plan.md`,
executed 2026-07-18) deliberately left `tests/` triage out of scope. As a
result `/home/jasper/Desktop/wider_release/chesswright-react/` currently
has **zero** `tests/` directory, while `worktree-frontend-spike` has 107
Python test files under `tests/unit/`, `tests/integration/`,
`tests/performance/`, and `tests/ui/`.

The frontend side needs no work: all 199 `frontend/src/**/*.test.ts(x)`
files already landed in chesswright-react's `03ef222` commit ("Add the
React/Vite frontend"), and vitest is fully configured there
(`frontend/vite.config.ts`, `frontend/src/setupTests.ts`,
`"test": "vitest run"` in `package.json`). This spec covers the Python
suite only. A one-time `npm test` smoke-check of the frontend suite in
chesswright-react is worth doing as part of verification, but is not a
porting task.

This is not a plain copy, because of two structural changes the repo
split already made on the source side:

1. **Streamlit is gone.** chesswright-react has no `dashboard/app.py`, no
   `dashboard/*_view.py` Streamlit pages, nothing that renders a
   Streamlit page at all.
2. **`dashboard/`'s Streamlit-free subset was renamed to a real package,
   `core/`.** `worktree-frontend-spike`'s `tests/conftest.py` puts both
   the repo root and `dashboard/` on `sys.path`, so tests bare-import
   things like `from data.evolution import ...` or `from chess_display
   import ...` — resolving through the `dashboard/`-on-`sys.path` hack.
   In chesswright-react, anything that used to live inside `dashboard/`
   now lives inside `core/` as a real (namespace) package, so those same
   bare imports need a `core.` prefix. Modules that were already at repo
   root in `worktree-frontend-spike` (e.g. `achievements.py`,
   `motif.py`, `snapshots.py`, `config.py`, `worker*.py`) are unaffected
   — same bare import, same root location, in both repos.

This exact bug class — a test (or `monkeypatch.setattr`) still pointing
at a pre-rename module path after code moves into a package — already
bit the repo-split merge 3 separate times (see
`chesswright_react_repo_split_built_2026-07-18` memory). This port
treats that risk as a first-class verification step, not an afterthought.

## Scope

Port everything that has a valid target in chesswright-react:
`tests/unit/`, `tests/integration/`, `tests/performance/`, plus
`tests/fixtures/synthetic_games.pgn` (a `conftest.py` dependency).

Drop `tests/ui/` entirely (see below) and 3 individual files that test
Streamlit-only code with no `core/` equivalent (also below). Everything
else — roughly 101 of the 107 files — is a mechanical import-rewrite
port.

## Source: include today's uncommitted WIP

`tests/integration/test_api_overview.py` and
`tests/integration/test_api_variations.py` currently have uncommitted
additions (50 and 42 lines) in this worktree. Per user decision, the
port includes this WIP rather than leaving it for a later pass.

Sequence:
1. Commit the current WIP in `worktree-frontend-spike` first, so both
   repos converge on the same content (ordinary commit, not part of this
   plan's "port" step itself).
2. Archive `tests/` from the resulting commit via
   `git archive <sha> -- tests | tar -x` into chesswright-react — the
   safer primitive established by the repo-split postmortem
   (`git ls-files | rsync --files-from` trusts the live working tree,
   which is a real risk if there's any uncommitted state at copy time;
   `git archive <commit>` is immune to it).

## Drop entirely: `tests/ui/` (3 files)

`tests/ui/test_pages.py` is a Streamlit `AppTest` harness that drives
`dashboard/app.py`. Neither `app.py` nor any `*_view.py` Streamlit page
exists in chesswright-react — there is no target to rewrite this
against. `tests/ui/__init__.py` goes with it.

(`dashboard/test_ask_view.py` is a same-named-pattern file living in
`dashboard/`, not `tests/ui/` — unrelated to this port, not touched.)

## Drop individually: 3 files testing Streamlit-only code

Found by reading each file, not just grepping module names — most other
`_view` string hits across the suite turned out to be comments/docstrings
referencing Streamlit pages for context, not real imports of them.

- **`tests/integration/test_analysis_jobs_view.py`** — tests
  `_active_run_id` and `_run_cache_stats`, two plain-sqlite helpers that
  live *inside* `dashboard/analysis_jobs_view.py` itself (never routed
  through `dashboard/data/*.py`, per the file's own docstring). No
  `core/` equivalent exists. Drop.
- **`tests/unit/test_settings_view.py`** — tests `settings_view.py`'s
  engine-binary-install helpers (`install_engine_binary` etc.).
  Confirmed via grep: chesswright-react's `api/` and `core/` have no
  engine-install logic at all — the React Settings page deferred native
  file dialog / engine install (per the 2026-07-17 Settings page design).
  Drop. Worth flagging separately (not part of this plan) that
  engine-install has no React-side equivalent yet.
- **`tests/unit/test_ask_brief.py`** — a golden-text test asserting
  `dashboard/data/ask_brief.py`'s extraction is byte-identical to the
  legacy `ask_view._build_data_brief()`. The extraction is historical and
  already proven; the legacy comparison target doesn't exist in
  chesswright-react. Drop.

## Import rewrite rules

**Modules that moved `dashboard/` → `core/` (need a `core.` prefix
wherever bare-imported):** `chess_display`, `api_key_store`,
`app_capabilities`, `confidence`, `engine_status`, `narrative`,
`claude_narrative` (package), and the whole `data` subpackage (`data`,
`data.evolution`, `data.insights`, `data.openings` (subpackage),
`data.search`, `data._shared`, `data.patterns`, `data.points`, etc.).

Example: `from data.evolution import compute_rating_trend` becomes
`from core.data.evolution import compute_rating_trend`. Same pattern for
`import narrative` → `import core.narrative`, and for any
`monkeypatch.setattr("data.evolution.some_fn", ...)` /
`mock.patch("data.evolution.some_fn")` string target → prefix the string
with `core.` too.

**Modules that were already at repo root in both trees (no rewrite):**
`achievements`, `motif`, `snapshots`, `opening_explorer`,
`opponent_analysis`, `config`, `db`, `db_import`, `ingest`, `migrate`,
`connections`, `joblock`, `chess_utils`, `annotate`, `worker*`,
`analytics*`, `chesscom_pgn`, `sync*`, `backfill*`.

**`conftest.py`:** drop the `sys.path.insert(0, str(DASHBOARD_DIR))` line
(nothing at that path in chesswright-react) and keep the
`sys.path.insert(0, str(REPO_ROOT))` line (still needed for the
root-level bare imports above). `core/` itself needs no `sys.path`
entry — it's an importable package/namespace-package directly under
`REPO_ROOT`, exactly like `api/` already is.

**Mechanism:** scripted regex rewrite across the copied `tests/` tree
covering both plain `from X import` / `import X` forms and
string-literal `monkeypatch.setattr(...)` / `mock.patch(...)` /
`patch(...)` targets for the 8 relocated module names above. Followed by
a mandatory grep audit of the *rewritten* tree for any remaining bare
reference to those 8 names in either form — string-based patch targets
in particular are invisible to an import-only regex, and this is the
precise failure mode that recurred 3 times during the repo-split merge.

## Config

chesswright-react's `pyproject.toml` already has
`[tool.pytest.ini_options]` with `testpaths = ["tests"]` and the
`unit`/`integration`/`perf`/`slow` markers pre-configured (copied over in
the original split, ahead of any tests actually existing there). No
config changes needed.

## Verification

Run the full `pytest` suite inside chesswright-react itself (not the
worktree) after the port — collection errors and import failures only
prove the rewrite works when run against chesswright-react's actual
layout, not the source repo's. Also run `npm test` in
chesswright-react's `frontend/` as a smoke-check that the
already-ported frontend suite still passes there (expected to be a
no-op, but unverified until now).

## Out of scope

- Pushing chesswright-react to a GitHub remote.
- Building a `core/` equivalent for engine-install (settings) or the
  analysis-jobs cache-stats helpers, so the 2 dropped tests could be
  un-dropped later — tracked as a product gap, not a test-porting task.
- `tests/performance/` benchmark thresholds/tuning — ported as-is with
  the same import rewrite, not re-tuned for chesswright-react's
  environment.
