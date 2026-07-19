# chesswright-react repo split — design

## Purpose

Scope how to spin the React/FastAPI rewrite (currently living as ~480
unpushed commits on the `worktree-frontend-spike` branch/worktree) out
into its own local repo, with a fresh git history, as a first concrete
step toward eventually retiring the Streamlit dashboard. This spec
covers the mechanics of that split only — not the eventual public
rename, GitHub push, or Gumroad/product-identity decision.

## Context

Two branches have been diverging from a shared ancestor
(`e6b49fb6cea1ef20728bf184318b13b3d81fedb4`):

- `feature/eval-dedup-cache` (the current working branch): 16 commits of
  pure backend modularization since the shared ancestor — splitting
  `patterns.py`, `points.py`, `openings.py`, `worker.py`,
  `desktop_app.py`, `analytics.py` into packages; relocating
  `dashboard/db_connections.py` to root-level `connections.py`; computing
  `BACKEND_MODULES` from a glob. None of this touches Streamlit view
  code — it's shared-layer work that `api/` (the FastAPI backend) also
  depends on, since `api/` reuses `dashboard/data/*.py` and
  `connections.py` directly rather than reimplementing them.
- `worktree-frontend-spike`: 405 commits since the same ancestor,
  building the full React/Vite + FastAPI rewrite. Verified directly
  against the code (not stale docs — `docs/frontend_migration_status.md`
  undercounts real progress): every one of the 16 non-Settings pages
  plus all 8 Settings sub-pages is a real, routed component in
  `frontend/src/App.tsx`'s `PAGE_COMPONENTS` map. `PageStub` has no live
  route pointing at it. Only Onboarding and Help have no page at all —
  not even a stub. The Pro extension point (`chesswright_pro`) already
  has an independent hook on the API side (`pro_gate.is_pro_active()` in
  `api/routers/board_chat.py` and `opening_tree.py`), so it isn't
  Streamlit-app-specific already.
- Real Phase D pilot users exist today, running the Streamlit-packaged
  installer (`BRIEF.md`: "Phase D — Small pilot group. In progress, not
  yet at its bar" / "Phase E — Wider public release. Only after Phase
  D's bar is [met]"). This is why Streamlit isn't being deleted outright
  as part of this spec — it's the thing currently in real users' hands.

Three considered approaches: (A) merge `worktree-frontend-spike` into
`main` in place, freezing rather than deleting Streamlit; (B) a true
repo split, new repo for the React app; (C) defer any repo/branch
surgery and just push `worktree-frontend-spike` as the new trunk without
touching `main`. **This spec scopes (B)**, specifically the "set up
fresh locally" variant, per direct instruction — not because it strictly
dominates (A) on the criteria examined, but because the user has three
concrete goals a repo split serves better than an in-place merge: a
clean git history, a Streamlit line that can keep existing independently
as a real fallback (not just a frozen tag), and an explicit boundary
around Pro-adjacent code.

## Decisions

- **New repo name (working, local-only): `chesswright-react`.** Not
  `chesswright` — claiming that name, and any corresponding rename of
  the current public repo, the Gumroad listing, or the installer
  product name, is explicitly deferred to a later decision once this
  split is validated. Per `CLAUDE.md`, that rename is a real
  cross-repo operation, not something to fold into this pass.
- **True fresh git history**, not a `git filter-repo`-curated one. One
  clean initial state (post identity-scrub), not ~480 raw commits and
  not a rewritten-but-preserved history. Costs real `git blame`/`git
  log` continuity for hard-won fixes (e.g. the DuckDB same-process
  corruption saga) — those remain narrated in `BRIEF.md`, just not in
  git itself. Chosen because history curation is real, ongoing setup
  work for marginal benefit here: nothing external depends on this
  branch's commit history yet (0 commits pushed to
  `origin/worktree-frontend-spike`... note: `git branch -vv` shows 375
  ahead of that remote specifically, meaning most — not all — of this
  work has never left this machine).
- **Explicit `from core import data`-style imports**, replacing the
  current flat `import data` / `import pro_gate` convention (which only
  works today via a `PYTHONPATH`-onto-`dashboard` side effect — the dev
  run command inserts `dashboard/` onto `PYTHONPATH`, and
  `react_desktop_app.py` does the packaged-build equivalent via
  `sys.path.insert(0, str(resource_dir / "dashboard"))`). Decided over
  keeping the flat style, since every one of the ~19 files doing `import
  data` already needs touching for the `dashboard` → `core` rename
  below — fixing the implicit-`sys.path`-layering convention at the same
  time costs little and removes a real "why does this only work by
  accident" surprise for anyone new to the codebase.

## Scope boundary: what crosses into `chesswright-react`

**Crosses over as-is** (shared backend core — config-driven, zero
Streamlit coupling, confirmed via `grep` for `streamlit`/`st\.` imports
across every root-level `.py` file):
`achievements.py`, `analytics.py`, `annotate.py`, `chesscom_pgn.py`,
`chess_utils.py`, `config.py`, `connections.py`, `db.py`, `db_import.py`,
`ingest.py`, `joblock.py`, `migrate.py`, `migrations/*.sql` (all 42,
pure schema), `motif.py`, `opening_explorer.py`, `opponent_analysis.py`,
`snapshots.py`, `sync.py`, `sync_chesscom.py`, `worker.py`,
`backfill_*.py` (3 files), `react_desktop_app.py`,
`chesswright-react.spec`, `pyproject.toml`, `constraints.txt`,
`requirements.txt`, `frontend/` (wholesale), `api/` (wholesale).

**Crosses over, renamed** — the 13 non-Streamlit-coupled files currently
living inside `dashboard/` move to a new `core/` package: `data/`
(subpackage), `pro_gate.py`, `narrative.py`, `claude_narrative.py`,
`api_key_store.py`, `chess_display.py`, `confidence.py`,
`report_html.py`, `theme.py`, `version.py`, `app_capabilities.py`.
Verified via `grep` for `^import streamlit|^from streamlit|st\.(session_state|cache|sidebar)`
across every `dashboard/*.py` file — these 13 (plus `data/`) are the
only ones that don't match.

**Stays behind** (Streamlit-only): `dashboard/*_view.py` (22 files),
`dashboard/app.py`, `dashboard/_common.py`, `dashboard/cached_queries.py`,
`dashboard/engine_status.py`, `dashboard/job_runner.py`,
`dashboard/live_engine.py`, `dashboard/opponent_prep_runner.py`,
`desktop_app.py`, `chesswright.spec`, `api_spike.spec` (confirmed dead —
its own header comment says "never used for a real release build"),
`.streamlit/config.toml`, `tests/ui/test_pages.py` (the sole Streamlit
`AppTest` file).

**Needs a fresh pass, not a copy:**
- `.github/workflows/build.yml` — currently only builds `chesswright.spec`
  (grep confirms zero React/FastAPI build steps exist in CI today). The
  new repo needs its own workflow targeting `chesswright-react.spec`.
  Reuse the *steps* that are still structurally relevant (DuckDB
  extension bundling, the pywebview Linux GTK/WebKit2 dependency install,
  since `react_desktop_app.py` uses the same pywebview-wrapped-desktop
  shape) but drop everything Streamlit-specific. Scope as its own
  implementation task, not a copy-paste.
- `tests/unit/`, `tests/integration/`, `tests/performance/` — per-file
  triage (backend-core tests cross, `dashboard/*_view.py`-adjacent tests
  don't). Not enumerated file-by-file here; becomes an implementation
  checklist item.
- Public docs (`README.md`, `CODE_OF_CONDUCT.md`, `CONTRIBUTING.md`,
  `LICENSE`, `PILOT.md`, `.github/ISSUE_TEMPLATE/*`, `.github/FUNDING.yml`)
  cross over but need a content pass — several currently describe or
  screenshot the Streamlit UI (`docs/screenshots/*.png`, `demo.gif`).

## Fresh-init mechanics + identity scrub

`git grep` for the real, tracked lichess username this project is
supposed to never hardcode (`CLAUDE.md`: "Config-driven by lichess
username... preserve it, don't reintroduce a hardcoded player") returns
exactly **one** hit anywhere in the tracked repo: `config.yaml`'s
`player.name`. Not in `docs/`, not in `tests/fixtures/`. Because history
isn't carried over, there's no historical-commit scrubbing risk (a
`filter-repo`/BFG pass would be a much bigger job) — the fix just has to
land before the very first commit.

Steps:
1. `git init` in a new local directory (`chesswright-react`), no history
   imported.
2. Copy over the "crosses over" + "crosses over, renamed" file sets from
   the current `worktree-frontend-spike` working tree.
3. Rename `dashboard/{data,pro_gate.py,narrative.py,claude_narrative.py,
   api_key_store.py,chess_display.py,confidence.py,report_html.py,
   theme.py,version.py,app_capabilities.py}` → `core/`. Update every
   caller from the flat `import data`/`import pro_gate` style to
   `from core import data`/`from core import pro_gate` (per the Decisions
   section above) — this touches roughly 19 files under `api/routers/`
   plus `api/shared_data.py`. Also remove the two places that currently
   rely on the `PYTHONPATH`-onto-`dashboard` side effect, now that
   imports are explicit: the dev-run command's
   `PYTHONPATH="$(pwd)/dashboard:$(pwd)"` simplifies to `$(pwd)` alone
   (repo root on path is still required, since `from core import data`
   resolves `core` as a package under it — only the extra `dashboard`
   entry is dead weight), and `react_desktop_app.py`'s
   `sys.path.insert(0, str(resource_dir / "dashboard"))` line is deleted
   outright (`resource_dir` itself, already on `sys.path` earlier in
   that function, is sufficient). Also update `chesswright-react.spec`'s
   `datas += [(str(ROOT / "dashboard"), "dashboard")]` line to bundle
   `core/` instead.
4. Scrub `config.yaml`: replace `player.name`'s real value with the
   file's own existing placeholder convention (matching e.g.
   `utc_offset_hours: 0 # CHANGE_ME`).
5. Do **not** copy `chess.db` into the new directory at all (already
   gitignored/untracked in the source, but avoid even an untracked copy
   sitting in the new repo's working tree).
6. Commit as a handful of logical commits (e.g. backend core +
   migrations, `dashboard`→`core` rename, API layer, frontend) rather
   than one flat commit or hundreds of raw ones — a short but real
   starting history, without carrying over the old branch's warts.

## CI

The new repo needs its own `.github/workflows/build.yml` targeting
`chesswright-react.spec`, not a port of the existing one — the existing
workflow's PyInstaller step, Streamlit-specific `datas` handling, and
`.streamlit/` bundling don't apply. Reusable pieces: the DuckDB
extension post-build bundling step and the pywebview Linux
GTK/WebKit2 `gi` dependency install, since `react_desktop_app.py` uses
the same pywebview-wrapped-desktop pattern as `desktop_app.py`. This is
scoped as its own implementation task.

## chesswright-pro linkage

No code changes needed inside `chesswright-pro` itself. Its package
(`chesswright_pro/tournament_prep.py`, `srs_drills.py`,
`opening_tree.py`, `game_report.py`) only *mentions*
`pro_gate.is_pro_active()` in docstrings/comments describing the gating
contract — the actual gate check and `import pro_gate` live on the
calling side, in `chesswright-react`'s own `api/routers/board_chat.py`
and `opening_tree.py`, which conditionally `from chesswright_pro import
...` only after the gate passes. That import becomes `from core import
pro_gate` per the rename above — a one-line change in those two router
files. The only cross-repo action needed: repoint
`chesswright-pro.spec`'s `CHESSWRIGHT_CORE_ROOT` env var at the new
local checkout path (it's already an env var, not a pinned path or git
submodule, so this is a build-time operational change, not a code
change).

## Explicitly out of scope for this pass

- Pushing to GitHub / creating the remote.
- The `chesswright` vs. `chesswright-react` naming/identity decision —
  which repo eventually becomes "the" public `chesswright`, whether the
  current repo gets renamed to something like `chesswright-legacy`, and
  the corresponding Gumroad/installer-name changes. `CLAUDE.md` flags
  this as a real cross-repo operation; it's a separate decision once
  this split is validated.
- README/CONTRIBUTING/PILOT.md content rewrites and `docs/screenshots/*`
  refresh.
- The per-file `tests/unit`/`tests/integration` triage.
- Reconciling `feature/eval-dedup-cache`'s 16 pending backend-refactor
  commits into `worktree-frontend-spike` — **this should happen before**
  copying files into the new repo, so `chesswright-react` starts from
  the already-modularized backend (`patterns.py`/`points.py`/`worker.py`
  splits, glob-based `BACKEND_MODULES`) rather than needing the same
  split done twice. Treated as a prerequisite, not a step of this spec.
- Any core-architecture performance refactor — a separate future
  initiative layered on top of the new repo, not part of getting the
  split done.

## Open follow-ups

- Decide the `chesswright` naming/identity question once
  `chesswright-react` has been validated (e.g. once Onboarding + Help
  ship and the React build has cleared whatever bar makes it a credible
  pilot replacement).
- Write the new CI workflow.
- Do the `tests/` per-file triage.
- Content pass on public docs and screenshots.
