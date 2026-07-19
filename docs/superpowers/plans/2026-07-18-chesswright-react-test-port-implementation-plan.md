# Chesswright-react Test Port Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port the 107-file Python test suite from `worktree-frontend-spike`'s `tests/` into `/home/jasper/Desktop/wider_release/chesswright-react/`, which currently has none, so the new repo has real test coverage instead of zero.

**Architecture:** Raw `git archive` copy of `tests/` first (traceable, mechanical), then a separate commit dropping the 5 files/dirs with no valid target in chesswright-react (Streamlit-only), then a scripted `core.`-prefix import rewrite for the subset of modules that moved `dashboard/` → `core/` during the repo split, then a grep audit pass to catch anything the regex missed (string-based `monkeypatch`/`patch` targets in particular), then a full pytest run inside chesswright-react itself to prove it actually works there.

**Tech Stack:** Python 3.12, pytest 9.1.1, pytest-benchmark 5.2.3, git archive/tar, a one-off Python regex-rewrite script (not committed — a migration tool, not project code).

## Global Constraints

- Source repo: `/home/jasper/Desktop/wider_release/chess_app/.claude/worktrees/frontend-spike` (branch `worktree-frontend-spike`). Target repo: `/home/jasper/Desktop/wider_release/chesswright-react` (branch `main`). These are two separate git repositories — every `git` command below must run with the correct working directory or `-C <path>`.
- Never touch `/home/jasper/Desktop/chess_project/chess-analyzer/` — unrelated to this task, but stated here because it's a standing hard rule for this whole project.
- Modules that moved `dashboard/` → `core/` in the split (need a `core.` prefix when bare-imported in tests): `data` (whole subpackage), `chess_display`, `api_key_store`, `app_capabilities`, `confidence`, `engine_status`, `narrative`, `claude_narrative` (package). No other module name gets rewritten.
- Drop entirely, no rewrite attempted: `tests/ui/` (2 files: `__init__.py`, `test_pages.py`), `tests/integration/test_analysis_jobs_view.py`, `tests/unit/test_settings_view.py`, `tests/unit/test_ask_brief.py`.
- Expected file count after drops: 107 − 2 (`tests/ui/`) − 3 (individual drops) = **102** `.py` files remaining under `tests/`.
- Spec: `docs/superpowers/specs/2026-07-18-chesswright-react-test-port-design.md`.

---

### Task 1: Commit today's WIP in worktree-frontend-spike and capture the source commit

**Files:**
- Modify (already dirty, just commit as-is): `tests/integration/test_api_overview.py`, `tests/integration/test_api_variations.py` (in `worktree-frontend-spike`)

**Interfaces:**
- Produces: a commit SHA in `worktree-frontend-spike` that Task 3's `git archive` will read from.

- [ ] **Step 1: Confirm no other test files are dirty**

Run (from `worktree-frontend-spike`):
```bash
git status --short tests/
```
Expected: exactly these two lines, nothing else —
```
 M tests/integration/test_api_overview.py
 M tests/integration/test_api_variations.py
```
If anything else under `tests/` shows up, stop and ask before continuing — this plan assumes only these two files are in flight.

- [ ] **Step 2: Commit the WIP**

```bash
git add tests/integration/test_api_overview.py tests/integration/test_api_variations.py
git commit -m "$(cat <<'EOF'
test: commit in-progress API overview/variations test additions

Committing now so chesswright-react's test port (see
docs/superpowers/plans/2026-07-18-chesswright-react-test-port-implementation-plan.md)
carries this content across too, per the design spec's decision to
include rather than defer this WIP.
EOF
)"
```

- [ ] **Step 3: Capture the commit SHA**

```bash
git rev-parse HEAD
```
Write down this SHA — it's `<SOURCE_SHA>` in Task 3.

---

### Task 2: Set up a Python venv in chesswright-react to run the ported suite

**Files:**
- Create: `/home/jasper/Desktop/wider_release/chesswright-react/.venv/` (not committed — gitignored, same convention as the worktree)

**Interfaces:**
- Produces: `chesswright-react/.venv/bin/python` and `chesswright-react/.venv/bin/pytest`, used by every later task's verification steps.

- [ ] **Step 1: Confirm chesswright-react has no venv yet**

```bash
ls -d /home/jasper/Desktop/wider_release/chesswright-react/.venv 2>&1
```
Expected: `No such file or directory`. (If one already exists, skip to Step 4 and just verify pytest is installed at the version below.)

- [ ] **Step 2: Create the venv and install product dependencies**

```bash
cd /home/jasper/Desktop/wider_release/chesswright-react
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt -c constraints.txt
```
Expected: installs without error (these are the same pins already used by `worktree-frontend-spike`, so no resolution surprises expected).

- [ ] **Step 3: Install test-only dependencies (pinned to match worktree-frontend-spike's .venv)**

```bash
.venv/bin/pip install pytest==9.1.1 pytest-benchmark==5.2.3 httpx==0.28.1
```
Expected: installs without error.

- [ ] **Step 4: Verify**

```bash
.venv/bin/python -c "import pytest, pytest_benchmark, httpx; print(pytest.__version__)"
```
Expected: `9.1.1` with no `ImportError`.

- [ ] **Step 5: Confirm `.venv` is gitignored (don't commit it)**

```bash
cd /home/jasper/Desktop/wider_release/chesswright-react
git check-ignore -v .venv || echo "NOT IGNORED"
```
Expected: prints a `.gitignore` match. If it prints `NOT IGNORED`, add `.venv/` to `chesswright-react/.gitignore` before proceeding (check `git status` doesn't show `.venv/` files afterward).

No commit for this task — a local venv is machine state, not repo content.

---

### Task 3: Raw-copy tests/ from worktree-frontend-spike into chesswright-react

**Files:**
- Create: `/home/jasper/Desktop/wider_release/chesswright-react/tests/` (full tree, 107 files, verbatim from `<SOURCE_SHA>`)

**Interfaces:**
- Consumes: `<SOURCE_SHA>` from Task 1.
- Produces: an unmodified `tests/` tree in chesswright-react, ready for Task 4's drops and Task 5's rewrite.

- [ ] **Step 1: Archive and extract**

```bash
git -C /home/jasper/Desktop/wider_release/chess_app/.claude/worktrees/frontend-spike \
  archive <SOURCE_SHA> -- tests \
  | tar -x -C /home/jasper/Desktop/wider_release/chesswright-react
```
(Replace `<SOURCE_SHA>` with the value from Task 1, Step 3.)

- [ ] **Step 2: Verify file count**

```bash
find /home/jasper/Desktop/wider_release/chesswright-react/tests -name "*.py" | wc -l
```
Expected: `107`.

```bash
ls /home/jasper/Desktop/wider_release/chesswright-react/tests/fixtures/
```
Expected: `synthetic_games.pgn`.

- [ ] **Step 3: Commit the raw copy**

```bash
cd /home/jasper/Desktop/wider_release/chesswright-react
git add tests/
git commit -m "$(cat <<'EOF'
test: raw-copy tests/ from worktree-frontend-spike

Verbatim copy via git archive (immune to any uncommitted state in the
source working tree, unlike an rsync-from-working-tree copy). Imports
are not yet rewritten for the dashboard/ -> core/ rename, and 5
Streamlit-only files/dirs with no target here are still present --
both handled in the next two commits.
EOF
)"
```

---

### Task 4: Drop the 5 files/dirs with no valid target in chesswright-react

**Files:**
- Delete: `tests/ui/` (whole directory: `__init__.py`, `test_pages.py`)
- Delete: `tests/integration/test_analysis_jobs_view.py`
- Delete: `tests/unit/test_settings_view.py`
- Delete: `tests/unit/test_ask_brief.py`

**Interfaces:**
- Produces: a `tests/` tree with exactly 102 `.py` files, none of which reference Streamlit or any `*_view.py` module.

- [ ] **Step 1: Delete**

```bash
cd /home/jasper/Desktop/wider_release/chesswright-react
git rm -r tests/ui
git rm tests/integration/test_analysis_jobs_view.py
git rm tests/unit/test_settings_view.py
git rm tests/unit/test_ask_brief.py
```

- [ ] **Step 2: Verify count and absence of Streamlit references**

```bash
find tests -name "*.py" | wc -l
```
Expected: `102`.

```bash
grep -rl "streamlit\|_view import\|import .*_view\b" tests --include="*.py"
```
Expected: no output (empty).

- [ ] **Step 3: Commit**

```bash
git commit -m "$(cat <<'EOF'
test: drop Streamlit-only tests with no chesswright-react target

tests/ui/test_pages.py drives dashboard/app.py, which doesn't exist
here (Streamlit was dropped from this frontend rewrite entirely).
test_analysis_jobs_view.py, test_settings_view.py, and test_ask_brief.py
each test logic that still lives only inside a Streamlit *_view.py page,
never routed through dashboard/data/*.py -- none of the three have a
core/ equivalent (confirmed via grep, not assumed). See the design spec
for the per-file reasoning.
EOF
)"
```

---

### Task 5: Scripted import rewrite (dashboard/ -> core/ prefix)

**Files:**
- Create (temporary, not committed): `/home/jasper/.claude/jobs/5dc524e5/tmp/rewrite_test_imports.py`
- Modify: every file under `tests/` that bare-imports one of the 8 relocated modules, plus `tests/conftest.py`

**Interfaces:**
- Consumes: the 8-module list from Global Constraints.
- Produces: a `tests/` tree where every reference to those 8 modules is `core.`-prefixed; Task 6 audits the result.

- [ ] **Step 1: Write the rewrite script**

```python
# /home/jasper/.claude/jobs/5dc524e5/tmp/rewrite_test_imports.py
import pathlib
import re

TESTS_ROOT = pathlib.Path("/home/jasper/Desktop/wider_release/chesswright-react/tests")

MODULES = [
    "data", "chess_display", "api_key_store", "app_capabilities",
    "confidence", "engine_status", "narrative", "claude_narrative",
]
MOD_ALT = "|".join(re.escape(m) for m in MODULES)

# from X import ... / from X.sub import ...
FROM_RE = re.compile(rf"^(\s*from )({MOD_ALT})(\.|\s)", re.MULTILINE)
# import X / import X.sub  (bare "import X" form, not "from X import Y")
IMPORT_RE = re.compile(rf"^(\s*import )({MOD_ALT})(\.|\s|$)", re.MULTILINE)
# quoted string targets for monkeypatch.setattr(...) / mock.patch(...) / patch(...)
STRING_RE = re.compile(rf"([\"'])({MOD_ALT})\.")

changed_files = []

for path in sorted(TESTS_ROOT.rglob("*.py")):
    text = path.read_text()
    original = text

    text = FROM_RE.sub(r"\1core.\2\3", text)
    text = IMPORT_RE.sub(r"\1core.\2\3", text)
    text = STRING_RE.sub(r"\1core.\2.", text)

    if text != original:
        path.write_text(text)
        changed_files.append(str(path.relative_to(TESTS_ROOT.parent)))

print(f"Rewrote {len(changed_files)} files:")
for f in changed_files:
    print(f"  {f}")
```

- [ ] **Step 2: Run it**

```bash
python3 /home/jasper/.claude/jobs/5dc524e5/tmp/rewrite_test_imports.py
```
Expected: a list of changed files printed (roughly a dozen or more — every file that imports `data.*`, `narrative`, `engine_status`, etc.). Read the list; nothing should look surprising (e.g. no file outside `tests/unit` or `tests/integration` — `tests/performance/test_query_perf.py` may legitimately appear if it imports `core.data.*`).

- [ ] **Step 3: Review the diff for over-broad string rewrites**

`STRING_RE` matches any quoted string starting with one of the 8 module names followed by a dot — including `"data."`, which is generic enough to false-positive on something unrelated (e.g. a hypothetical `"data.csv"` path string that has nothing to do with the `data` package). `FROM_RE`/`IMPORT_RE` can't false-positive this way (they only match literal `from `/`import ` at the start of a line), but `STRING_RE` needs a human look:

```bash
cd /home/jasper/Desktop/wider_release/chesswright-react
git diff -- tests | grep -B2 '^\+.*core\.\(data\|chess_display\|api_key_store\|app_capabilities\|confidence\|engine_status\|narrative\|claude_narrative\)\.' | grep -v '^\+.*^\s*\(from\|import\)'
```
Read every hit this produces. Each should be a `monkeypatch.setattr(...)`, `mock.patch(...)`, or `patch(...)` call target — a legitimate rewrite. If any hit is something else (a docstring, a comment, an unrelated string literal), that file has a false-positive rewrite: manually revert just that line to its original quoted string before continuing.

- [ ] **Step 4: Fix conftest.py's sys.path hack by hand**

Open `tests/conftest.py` and find:
```python
REPO_ROOT = pathlib.Path(__file__).parent.parent
DASHBOARD_DIR = REPO_ROOT / "dashboard"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(DASHBOARD_DIR))
```
Replace with:
```python
REPO_ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))
```
(Delete the `DASHBOARD_DIR` line and its `sys.path.insert` entirely — there is no `dashboard/` in chesswright-react. `core/` needs no `sys.path` entry; it's an importable package directly under `REPO_ROOT`, which is already on the path.)

If any other file in `tests/` has the same two-line `DASHBOARD_DIR` / `sys.path.insert(..., DASHBOARD_DIR)` pattern (check with the command below), apply the same fix there too:
```bash
grep -rl "DASHBOARD_DIR" tests --include="*.py"
```

- [ ] **Step 5: Spot-check one rewritten file**

```bash
grep -n "^from core\.\|^import core\." tests/integration/test_api_overview.py tests/unit/test_evolution.py 2>/dev/null
```
Expected: at least one line per file starting `from core.` (both files import from the `data` subpackage in the original suite). If a file shows no `core.` lines but should, re-check Step 2's changed-files list — it may not have needed rewriting (fine) or the regex may have missed a shape (check manually and fix by hand).

- [ ] **Step 6: Commit**

```bash
cd /home/jasper/Desktop/wider_release/chesswright-react
git add tests/
git commit -m "$(cat <<'EOF'
test: rewrite dashboard/ imports to core/ for the ported test suite

Scripted regex rewrite: any bare import of data, chess_display,
api_key_store, app_capabilities, confidence, engine_status, narrative,
or claude_narrative (all relocated dashboard/ -> core/ by the repo
split) now gets a core. prefix, including monkeypatch/patch string
targets. Modules that were already at repo root in both trees
(achievements, motif, snapshots, config, worker*, etc.) are untouched.
conftest.py's dashboard/-on-sys.path hack is removed -- nothing at
that path here.

Next commit audits for anything this regex missed.
EOF
)"
```

---

### Task 6: Grep audit for stale bare references

**Files:**
- Modify: any file the audit finds (expected: none, but must be checked, not assumed — this exact bug class recurred 3 times during the repo split)

**Interfaces:**
- Consumes: the rewritten `tests/` tree from Task 5.
- Produces: a `tests/` tree with zero remaining bare references to the 8 relocated module names.

- [ ] **Step 1: Audit remaining bare imports**

```bash
cd /home/jasper/Desktop/wider_release/chesswright-react
grep -rnE "^\s*(from|import) (data|chess_display|api_key_store|app_capabilities|confidence|engine_status|narrative|claude_narrative)(\.|\s|$)" tests --include="*.py"
```
Expected: no output.

- [ ] **Step 2: Audit remaining string-based patch/monkeypatch targets**

```bash
grep -rnE "(monkeypatch\.setattr|mock\.patch|patch)\(\s*[\"'](data|chess_display|api_key_store|app_capabilities|confidence|engine_status|narrative|claude_narrative)\." tests --include="*.py"
```
Expected: no output.

- [ ] **Step 3: If either command produced output, fix each hit by hand**

For every matched line, prepend `core.` to the module name in that exact spot (same transformation as Task 5, applied manually because the regex missed this shape). Re-run both Step 1 and Step 2 commands after each fix until both are empty.

- [ ] **Step 4: Commit (only if Step 3 found and fixed anything)**

```bash
git add tests/
git commit -m "$(cat <<'EOF'
test: fix import(s) the scripted rewrite missed

Manual fixups for reference shapes the Task 5 regex didn't cover
(e.g. a string-based monkeypatch target on its own line, or an import
split across multiple lines).
EOF
)"
```
If Steps 1-2 produced no output at all, skip this commit — there's nothing to commit.

---

### Task 7: Run the full pytest suite in chesswright-react

**Files:**
- Modify: whatever files a real failure points to (expected: none — this step exists to prove the port works, not to build new fixes; if failures do turn up, they're either a missed rewrite shape or a genuine incompatibility to report, not something to paper over)

**Interfaces:**
- Consumes: the fully-rewritten `tests/` tree and the venv from Task 2.

- [ ] **Step 1: Run the suite**

```bash
cd /home/jasper/Desktop/wider_release/chesswright-react
.venv/bin/python -m pytest
```
Expected: collection succeeds (no `ImportError`/`ModuleNotFoundError` during collection) and the run completes. Some individual test failures unrelated to the import rewrite (e.g. a real behavioral difference between the two repos) are possible but should be rare — chesswright-react's `core/`+`api/` code is the same logic as the worktree's `dashboard/`+`api/`, just renamed.

- [ ] **Step 2: Triage any failures**

For each failure:
- If it's `ImportError`/`ModuleNotFoundError` mentioning one of the 8 relocated modules: Task 5/6's rewrite missed this shape. Fix the import by hand, re-run just that test file (`pytest tests/path/to/test_file.py -v`), confirm it passes.
- If it's a `ModuleNotFoundError` for something NOT in the 8-module list: likely a genuine environment gap (e.g. a dependency version mismatch between the two repos' `requirements.txt`). Compare the two files' pins for that dependency and reconcile Task 2's venv, don't edit the test.
- If it's an assertion failure unrelated to imports: stop and report it rather than editing the test to make it pass — a real behavioral difference between the two codebases is a separate finding, not something this port should paper over.

- [ ] **Step 3: Re-run until clean**

```bash
.venv/bin/python -m pytest
```
Expected: same pass/fail counts as a fresh `pytest` run on `worktree-frontend-spike` itself (run `cd /home/jasper/Desktop/wider_release/chess_app/.claude/worktrees/frontend-spike && .venv/bin/python -m pytest tests/` for comparison if unsure what "clean" should look like — note the worktree's own suite currently reports ~2min/all passing per project memory, not counting the 5 files dropped in Task 4).

- [ ] **Step 4: Commit any fixes from Step 2**

```bash
cd /home/jasper/Desktop/wider_release/chesswright-react
git add tests/
git commit -m "$(cat <<'EOF'
test: fix remaining import/env issues found by a real pytest run

Verification failures caught here that Task 5's regex and Task 6's
grep audit didn't -- see individual fixes for specifics.
EOF
)"
```
If Step 1 passed clean on the first try, skip this commit.

---

### Task 8: Smoke-check the already-ported frontend suite

**Files:**
- None expected to change — this step verifies existing content, it doesn't port anything new (frontend tests already landed in commit `03ef222`).

**Interfaces:**
- Consumes: `chesswright-react/frontend/`'s existing `package.json` `test` script.

- [ ] **Step 1: Install frontend deps if needed**

```bash
cd /home/jasper/Desktop/wider_release/chesswright-react/frontend
ls node_modules >/dev/null 2>&1 || npm install
```

- [ ] **Step 2: Run the frontend suite**

```bash
npm test
```
Expected: all tests pass (199 test files, matching `worktree-frontend-spike`'s own frontend suite — this is a smoke-check confirming the earlier repo-split commit's copy was sound, not new porting work).

- [ ] **Step 3: If anything fails**

Compare against the equivalent run in the worktree:
```bash
cd /home/jasper/Desktop/wider_release/chess_app/.claude/worktrees/frontend-spike/frontend
npm test
```
If the worktree's own suite has the same failure, it's pre-existing and out of scope for this plan — report it rather than fixing it here. If chesswright-react fails where the worktree passes, that's a real copy discrepancy worth its own fix commit in chesswright-react.

No commit expected for this task unless Step 3 turns up a real, fixable discrepancy.

---

## Done Criteria

- [ ] chesswright-react's `tests/` has exactly 102 `.py` files plus `conftest.py`, `__init__.py`, and `fixtures/synthetic_games.pgn`.
- [ ] `grep -rnE "^\s*(from|import) (data|chess_display|api_key_store|app_capabilities|confidence|engine_status|narrative|claude_narrative)(\.|\s|$)" tests --include="*.py"` returns nothing.
- [ ] `.venv/bin/python -m pytest` (run from chesswright-react) passes.
- [ ] `npm test` (run from chesswright-react/frontend) passes.
- [ ] All commits above exist on chesswright-react's `main` branch (not pushed anywhere — this plan doesn't touch any remote).
