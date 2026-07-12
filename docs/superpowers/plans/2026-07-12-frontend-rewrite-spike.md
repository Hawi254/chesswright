# Frontend Rewrite Feasibility Spike Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove — with real evidence, not assumptions — that a standalone FastAPI service plus a React/Vite frontend can serve real Overview data alongside Chesswright's existing Python backend, survive PyInstaller freezing, and integrate cleanly with `desktop_app.py`'s subprocess-based process model, before any commitment to replacing Streamlit's 21-page dashboard.

**Architecture:** A new `api/` package exposes 3 read-only FastAPI endpoints that call the existing, Streamlit-free `dashboard/data/overview.py` and `dashboard/data/_shared.py` functions directly, reusing `dashboard/_common.py`'s existing DuckDB-snapshot/locking safety machinery via `get_connections()` (confirmed callable outside an active Streamlit run — see Task 2). The API runs as its own subprocess, launched and torn down the same way `desktop_app.py` already launches Streamlit (`launch_server_subprocess`/`wait_for_server`), because this codebase already tried and rejected the in-process-thread alternative (`desktop_app.py`'s own module docstring: calling a server's blocking run loop on a background thread crashed live, since Python only allows `signal.signal()` from the interpreter's main thread — uvicorn installs its own signal handlers the same way Streamlit's `bootstrap.run()` does). A new `frontend/` Vite+React app (mirroring the existing `dashboard/components/chessboard/frontend/` toolchain) renders the Overview identity zone against the running API.

**Tech Stack:** FastAPI (new dependency), uvicorn (already present, transitive), React 18 + Vite 5 (matching `dashboard/components/chessboard/frontend/package.json`'s pinned versions), pytest + FastAPI's `TestClient` (httpx already present) for backend tests.

## Global Constraints

- Linux-only for this spike (dev machine) — Windows/macOS packaging is explicitly out of scope and stays an open risk, not silently resolved.
- No auth, no write endpoints — every new endpoint is a read-only wrapper over an existing `dashboard/data/*.py` function, no new business logic.
- Do not modify `dashboard/*_view.py`, `app.py`, or `desktop_app.py`'s real production entry point (`main()`). All new code is additive (`api/`, `frontend/`, a new spike-only `.spec` file, a new spike-only launcher script).
- Do not modify `chesswright.spec` or `chesswright-pro.spec` (per `chesswright_pro_pyinstaller_spec_gotcha` — a third, spike-only spec file is used instead so the real production builds are untouched).
- Work happens on its own branch/worktree (e.g. `feature/frontend-spike`), independent of `feature/eval-dedup-cache`, which has an unrelated session's uncommitted work in flight as of 2026-07-12.

---

### Task 1: Record the re-scoped FastAPI decision

**Files:**
- Modify: `docs/scoping/fastapi-integration-scoping.md` (append new section at end)

**Interfaces:** None (documentation only).

- [ ] **Step 1: Append the re-scope section**

Add this section to the end of `docs/scoping/fastapi-integration-scoping.md`:

```markdown

## 8. 2026-07-12 re-scope: a concrete need appeared

This doc's original conclusion (§6-7: no-go, `st.App` is the cheaper path
"if a real API need ever appears") was explicitly conditioned on a real,
concrete need showing up — not a hypothetical one. One has: the user is
exploring setting Streamlit aside for the dashboard's UI layer entirely,
on a dedicated feature branch, keeping the existing Python backend. A
separate frontend needs a real HTTP API into that backend.

**Decision: standalone FastAPI service, not `st.App`.** `st.App`
(§2/§5's finding) is still the right answer for "expose one HTTP route
from inside the existing Streamlit process" — it is NOT the right answer
for "the frontend is being rewritten and Streamlit's own process may not
be running at all going forward." A standalone service is the more
conventional shape for a real SPA, and is accepted here deliberately,
extra framework/bundling surface included, because the alternative
(`st.App`) is scoped for a narrower problem than the one on the table now.

See `docs/superpowers/specs/2026-07-12-frontend-rewrite-spike-design.md`
for the full spike design, and
`docs/superpowers/plans/2026-07-12-frontend-rewrite-spike.md` for the
implementation plan and (once run) its findings.
```

- [ ] **Step 2: Verify the section was added**

Run: `grep -n "2026-07-12 re-scope" docs/scoping/fastapi-integration-scoping.md`
Expected: one matching line.

- [ ] **Step 3: Commit**

```bash
git add docs/scoping/fastapi-integration-scoping.md
git commit -m "Re-scope FastAPI decision: standalone service for the frontend spike"
```

---

### Task 2: Discovery — lock in that `get_connections()` works outside Streamlit

**Files:**
- Modify: `tests/integration/test_api_overview.py` (new file — created here, extended in Task 3)

**Interfaces:**
- Consumes: `dashboard/_common.py`'s `get_connections()` (no args, returns `(sqlite_conn, duck_conn)`; `@st.cache_resource`-decorated, exposes `.clear()`), `config.set_player_name(name, path=...)`, `config.set_database_path(path, path=...)` (both already exist, verified in `config.py`).
- Produces: confirms `_common.get_connections()` is safe for `api/db.py` (Task 3) to call directly.

This was already verified manually during planning (calling `_common.get_connections()`
from a plain script outside any Streamlit run works — it just logs a harmless
"missing ScriptRunContext... can be ignored when running in bare mode" warning). This
task locks that finding into the automated suite as a real regression check, using a
migrated fixture database rather than the live dev `chess.db`, so it doesn't depend on
that file's contents.

- [ ] **Step 1: Write the failing test**

```python
"""Integration tests for the FastAPI spike's data-layer reuse.

api/db.py calls dashboard/_common.py's get_connections() directly instead
of reimplementing DuckDB-snapshot safety from scratch -- that machinery
(per-PID snapshot + locked-connection wrapper) is the hard-won fix for a
real corruption incident (see the duckdb_sqlite_same_process_hazard
project memory), not something to risk reinventing. This file locks in
that get_connections() is actually safe to call from a plain process with
no active Streamlit script run, which is the whole premise api/db.py
depends on.
"""
import importlib
import pathlib
import shutil
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
DASHBOARD_DIR = REPO_ROOT / "dashboard"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(DASHBOARD_DIR))


@pytest.mark.integration
def test_get_connections_works_outside_streamlit(migrated_db_path, monkeypatch, tmp_path):
    scratch_config = tmp_path / "config.yaml"
    shutil.copy(REPO_ROOT / "config.yaml", scratch_config)
    monkeypatch.setenv("CHESSWRIGHT_CONFIG_PATH", str(scratch_config))

    import config as _config
    importlib.reload(_config)
    _config.set_player_name("spike_test_player", path=str(scratch_config))
    _config.set_database_path(str(migrated_db_path), path=str(scratch_config))

    import _common
    _common.get_connections.clear()  # st.cache_resource is process-wide;
                                      # force a fresh read for this config.
    sqlite_conn, duck_conn = _common.get_connections()

    assert duck_conn.execute("SELECT COUNT(*) FROM db.games").fetchone()[0] == 0
    assert sqlite_conn.execute("SELECT COUNT(*) FROM games").fetchone()[0] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_api_overview.py::test_get_connections_works_outside_streamlit -v`
Expected: FAIL (file/fixture doesn't exist yet, or a collection error) — confirms the test
doesn't vacuously pass before the real code path is exercised.

- [ ] **Step 3: Run again after fixing any collection errors**

If `migrated_db_path` isn't found, confirm `tests/conftest.py` (repo root) already defines
it — it does (seen during planning). No new fixture code needed; this step is just
running the test for real and confirming it now executes (not just fails to collect):

Run: `pytest tests/integration/test_api_overview.py::test_get_connections_works_outside_streamlit -v`
Expected: PASS. (No implementation step needed here — this test exercises existing code;
its job is to prove the existing `get_connections()` already does the right thing, not to
drive new production code.)

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_api_overview.py
git commit -m "Add regression test: get_connections() works outside a Streamlit run"
```

---

### Task 3: `api/` package — FastAPI app with 3 read-only endpoints

**Files:**
- Create: `api/__init__.py`
- Create: `api/db.py`
- Create: `api/main.py`
- Modify: `tests/integration/test_api_overview.py` (add endpoint tests)

**Interfaces:**
- Consumes: `data.get_headline_stats(duck_conn, sqlite_conn)` → dict with keys
  `total_games`, `analyzed_games`, `acpl`, `blunder_rate`, `win_pct`, `n_analyzed_moves`
  (all `int`/`float`/`None`). `data.get_rating_trajectory(duck_conn)` → pandas DataFrame
  with columns `year` (int), `avg_rating` (float), `n_games` (int).
  `data.get_rating_snapshot(duck_conn)` → dict (verify exact keys in Step 1 below by
  reading `dashboard/data/overview.py`'s `get_rating_snapshot` — used as
  `rating_snapshot.get("current_rating")` / `.get("peak_rating")` in `overview_view.py`).
- Produces: `api.main.app` (a `fastapi.FastAPI` instance) with routes
  `GET /api/overview/headline-stats`, `GET /api/overview/rating-trajectory`,
  `GET /api/overview/rating-snapshot`. `api.db.get_db_connections()` → `(sqlite_conn, duck_conn)`.

- [ ] **Step 1: Confirm `get_rating_snapshot`'s exact return shape**

Run: `sed -n '104,118p' dashboard/data/overview.py`
Confirms the dict includes a `current_rating` key (already used as
`rating_snapshot.get("current_rating")` in `dashboard/overview_view.py`) —
Task 7's frontend reads this same key from the endpoint's JSON passthrough.
`api/main.py`'s endpoint (Step 6) returns this dict unmodified, so no
key-specific code is needed there; this step is a confidence check for
Task 7, not a code input for this task.

- [ ] **Step 2: Write the failing tests**

Append to `tests/integration/test_api_overview.py`:

```python
from fastapi.testclient import TestClient


@pytest.fixture
def api_client(migrated_db_path, monkeypatch, tmp_path):
    scratch_config = tmp_path / "config.yaml"
    shutil.copy(REPO_ROOT / "config.yaml", scratch_config)
    monkeypatch.setenv("CHESSWRIGHT_CONFIG_PATH", str(scratch_config))

    import config as _config
    importlib.reload(_config)
    _config.set_player_name("spike_test_player", path=str(scratch_config))
    _config.set_database_path(str(migrated_db_path), path=str(scratch_config))

    import _common
    _common.get_connections.clear()

    import api.main as api_main
    return TestClient(api_main.app)


@pytest.mark.integration
def test_headline_stats_endpoint(api_client):
    resp = api_client.get("/api/overview/headline-stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_games"] == 0
    assert body["analyzed_games"] == 0


@pytest.mark.integration
def test_rating_trajectory_endpoint(api_client):
    resp = api_client.get("/api/overview/rating-trajectory")
    assert resp.status_code == 200
    assert resp.json() == []  # empty migrated DB has no games


@pytest.mark.integration
def test_rating_snapshot_endpoint(api_client):
    resp = api_client.get("/api/overview/rating-snapshot")
    assert resp.status_code == 200
    assert isinstance(resp.json(), dict)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/integration/test_api_overview.py -v -k "endpoint"`
Expected: FAIL with `ModuleNotFoundError: No module named 'api'` or similar.

- [ ] **Step 4: Create `api/__init__.py`**

```python
```

(Empty file — makes `api/` an importable package.)

- [ ] **Step 5: Create `api/db.py`**

```python
"""Connection helper for the FastAPI spike service.

Reuses dashboard/_common.py's get_connections() directly rather than
reimplementing it: get_connections() is @st.cache_resource-decorated, but
nothing in its own body touches an active ScriptRunContext (confirmed --
see tests/integration/test_api_overview.py::test_get_connections_works_outside_streamlit).
The DuckDB per-PID-snapshot + locked-connection machinery it wraps is a
hard-won fix for a real corruption incident (duckdb_sqlite_same_process_hazard
project memory) -- reused here, not duplicated, on purpose.
"""
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
DASHBOARD_DIR = REPO_ROOT / "dashboard"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(DASHBOARD_DIR))

import _common


def get_db_connections():
    """Returns (sqlite_conn, duck_conn). Thin re-export of
    dashboard/_common.py's get_connections() under an API-layer-scoped
    name."""
    return _common.get_connections()
```

- [ ] **Step 6: Create `api/main.py`**

```python
"""FastAPI spike service -- 3 read-only endpoints wrapping existing,
Streamlit-free dashboard/data/overview.py functions. No new business
logic; no auth; no write paths. See
docs/superpowers/specs/2026-07-12-frontend-rewrite-spike-design.md.
"""
from fastapi import FastAPI

from api.db import get_db_connections

import data

app = FastAPI(title="Chesswright API (spike)")


@app.get("/api/overview/headline-stats")
def headline_stats():
    sqlite_conn, duck_conn = get_db_connections()
    return data.get_headline_stats(duck_conn, sqlite_conn)


@app.get("/api/overview/rating-trajectory")
def rating_trajectory():
    _, duck_conn = get_db_connections()
    df = data.get_rating_trajectory(duck_conn)
    return df.to_dict(orient="records")


@app.get("/api/overview/rating-snapshot")
def rating_snapshot():
    _, duck_conn = get_db_connections()
    return data.get_rating_snapshot(duck_conn)
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/integration/test_api_overview.py -v`
Expected: all PASS (4 tests: the Task 2 discovery test + 3 endpoint tests).

- [ ] **Step 8: Commit**

```bash
git add api/__init__.py api/db.py api/main.py tests/integration/test_api_overview.py
git commit -m "Add FastAPI spike service: 3 read-only Overview endpoints"
```

---

### Task 4: Standalone manual verification

**Files:**
- Modify: `requirements.txt` (add `fastapi`)

**Interfaces:** None new — this task verifies Task 3's app runs for real against real data,
outside pytest.

- [ ] **Step 1: Add fastapi to requirements.txt**

Add this line to `requirements.txt` (after the existing `rapidfuzz==3.14.5` line, matching
its plain `pkg==version` style — pin whatever version installs; `uvicorn`/`starlette`/
`httpx` are already present as transitive deps, confirmed during planning):

```
fastapi==0.121.2
```

(Run `.venv/bin/pip index versions fastapi 2>&1 | head -5` first if unsure of the current
latest compatible version — pin to whatever actually installs cleanly, don't guess.)

- [ ] **Step 2: Install and run standalone**

```bash
.venv/bin/pip install fastapi
.venv/bin/uvicorn api.main:app --port 8123
```

Expected: server starts, logs `Uvicorn running on http://127.0.0.1:8123`.

- [ ] **Step 3: Hit it with real data (separate terminal, server still running)**

```bash
curl -s http://127.0.0.1:8123/api/overview/headline-stats | python3 -m json.tool
```

Expected: real JSON matching the live dashboard's own numbers (compare against the
`overview_live.png` screenshot from this session's earlier live-verify: `total_games:
32295`, `analyzed_games: 1495`, etc. — exact numbers may drift if the dev DB changed
since, but should be in the same ballpark, not zero/null).

- [ ] **Step 4: Stop the server, commit the dependency pin**

```bash
git add requirements.txt
git commit -m "Add fastapi dependency for the spike API service"
```

---

### Task 5: Subprocess process-model integration

**Files:**
- Create: `api/spike_launcher.py`

**Interfaces:**
- Consumes: `api.main:app` (Task 3).
- Produces: a runnable script proving the subprocess start/stop pattern; no other task
  depends on this one's internals.

- [ ] **Step 1: Write `api/spike_launcher.py`**

```python
"""Proves the FastAPI spike service can run as its own subprocess and
shut down cleanly -- the same pattern desktop_app.py already uses for
Streamlit, and for the same reason: desktop_app.py's own module docstring
documents that running a server's blocking loop in-process on a
background thread crashed live (bootstrap.run() installs a SIGTERM
handler, and Python only allows signal.signal() from the main thread --
uvicorn does the same signal-handler installation Streamlit's bootstrap
does, so the same crash applies here). Run directly:
    python3 api/spike_launcher.py
"""
import socket
import subprocess
import sys
import time
import urllib.request


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_for_server(url, timeout_s=30):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(url, timeout=1)
            return True
        except Exception:
            time.sleep(0.3)
    return False


def launch_api_subprocess(port):
    cmd = [sys.executable, "-m", "uvicorn", "api.main:app",
           "--host", "127.0.0.1", "--port", str(port)]
    return subprocess.Popen(cmd)


def main():
    port = free_port()
    url = f"http://127.0.0.1:{port}"
    proc = launch_api_subprocess(port)
    try:
        if not wait_for_server(f"{url}/api/overview/headline-stats"):
            print("API server did not start in time.", file=sys.stderr)
            proc.terminate()
            sys.exit(1)

        resp = urllib.request.urlopen(f"{url}/api/overview/headline-stats", timeout=5)
        body = resp.read()
        print("Fetched real data through the subprocess API:", body[:200])
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)

    assert proc.poll() is not None, "API subprocess did not exit cleanly"
    print(f"Clean shutdown confirmed -- exit code {proc.poll()}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it and verify clean start/stop**

Run: `python3 api/spike_launcher.py`
Expected output ends with:
```
Fetched real data through the subprocess API: b'{"total_games":...
Clean shutdown confirmed -- exit code 0
```

- [ ] **Step 3: Verify no orphaned process**

Run: `pgrep -fl "uvicorn api.main:app"`
Expected: no output (empty) — confirms the subprocess didn't survive the parent's exit.

- [ ] **Step 4: Commit**

```bash
git add api/spike_launcher.py
git commit -m "Add subprocess launcher proving clean API start/stop"
```

---

### Task 6: PyInstaller bundling (spike-only spec, production specs untouched)

**Files:**
- Create: `api_spike.spec`

**Interfaces:** None new — proves Task 3/5's code survives freezing.

- [ ] **Step 1: Write `api_spike.spec`**

```python
# Spike-only PyInstaller spec -- proves FastAPI/uvicorn survive freezing
# alongside this project's existing backend modules. Deliberately
# separate from chesswright.spec/chesswright-pro.spec (per the
# chesswright_pro_pyinstaller_spec_gotcha project memory: building the
# wrong spec silently drops things) -- this file is never used for a
# real release build.
import pathlib
from PyInstaller.utils.hooks import collect_all

ROOT = pathlib.Path(".").resolve()

BACKEND_MODULES = [
    "ingest.py", "worker.py", "annotate.py", "analytics.py", "db.py",
    "config.py", "chess_utils.py", "migrate.py", "sync.py", "opening_explorer.py",
    "db_import.py", "joblock.py", "motif.py", "opponent_analysis.py",
    "sync_chesscom.py", "chesscom_pgn.py", "backfill_batch_eval_cache.py",
]

datas = [(str(ROOT / name), ".") for name in BACKEND_MODULES]
datas += [(str(ROOT / "migrations"), "migrations")]
datas += [(str(ROOT / "dashboard" / "_common.py"), "dashboard")]
datas += [(str(ROOT / "dashboard" / "data"), "dashboard/data")]
datas += [(str(ROOT / "api"), "api")]

hiddenimports = []
binaries = []
for pkg in ["fastapi", "uvicorn", "starlette", "duckdb", "pandas", "chess", "yaml"]:
    pkg_datas, pkg_binaries, pkg_hiddenimports = collect_all(pkg)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hiddenimports

a = Analysis(
    ["api/spike_launcher.py"],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="api_spike",
    console=True,
)
coll = COLLECT(exe, a.binaries, a.datas, name="api_spike")
```

- [ ] **Step 2: Build**

Run: `.venv/bin/pyinstaller api_spike.spec`
Expected: completes without error, produces `dist/api_spike/api_spike`.

- [ ] **Step 3: Run the frozen build**

Run: `cd dist/api_spike && ./api_spike`
Expected: same output shape as Task 5 Step 2 (starts, fetches real data via the
subprocess it launches internally, shuts down cleanly, prints "Clean shutdown confirmed").
Note: `duckdb`'s sqlite extension network-fetch (see `chesswright.spec`'s own comment
about this) may need the same `fetch_duckdb_extensions` step if this fails with a
network-related DuckDB error — if so, that's a real finding to record in Task 8, not
a blocker to silently work around.

- [ ] **Step 4: Commit**

```bash
git add api_spike.spec
git commit -m "Add spike-only PyInstaller spec proving FastAPI freezes cleanly"
```

---

### Task 7: Frontend slice — React/Vite Overview identity zone

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/vite.config.js`
- Create: `frontend/index.html`
- Create: `frontend/src/main.jsx`
- Create: `frontend/src/App.jsx`

**Interfaces:**
- Consumes: `GET /api/overview/headline-stats`, `GET /api/overview/rating-snapshot`
  (Task 3), assumed reachable at `http://127.0.0.1:8123` for this spike (matching Task 4's
  manual-run port — no dynamic port wiring for the frontend spike itself; that's covered
  by Task 5/6's subprocess integration, which is about the desktop packaging path, not
  the frontend dev loop).

Note: this slice deliberately covers rating + the 4 stat tiles only, not the identity
badges (those need `get_career_findings`'s polarity split, a materially bigger data-layer
surface not needed to answer this spike's actual question — proving FastAPI+React can
serve real data end-to-end). Recorded as a deliberate simplification, not a silent cut.

- [ ] **Step 1: Create `frontend/package.json`**

```json
{
  "name": "chesswright-frontend-spike",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1"
  },
  "devDependencies": {
    "@vitejs/plugin-react": "^4.3.4",
    "vite": "^5.4.11"
  },
  "scripts": {
    "dev": "vite --port 5173",
    "build": "vite build"
  }
}
```

- [ ] **Step 2: Create `frontend/vite.config.js`**

```javascript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
})
```

- [ ] **Step 3: Create `frontend/index.html`**

```html
<!doctype html>
<html>
  <head>
    <meta charset="UTF-8" />
    <title>Chesswright Frontend Spike</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>
```

- [ ] **Step 4: Create `frontend/src/main.jsx`**

```jsx
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
```

- [ ] **Step 5: Create `frontend/src/App.jsx`**

```jsx
import { useEffect, useState } from 'react'

const API_BASE = 'http://127.0.0.1:8123'

export default function App() {
  const [stats, setStats] = useState(null)
  const [snapshot, setSnapshot] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    Promise.all([
      fetch(`${API_BASE}/api/overview/headline-stats`).then(r => r.json()),
      fetch(`${API_BASE}/api/overview/rating-snapshot`).then(r => r.json()),
    ])
      .then(([statsBody, snapshotBody]) => {
        setStats(statsBody)
        setSnapshot(snapshotBody)
      })
      .catch(e => setError(String(e)))
  }, [])

  if (error) return <div>Error fetching from API: {error}</div>
  if (!stats || !snapshot) return <div>Loading...</div>

  return (
    <div style={{ fontFamily: 'sans-serif', padding: '2rem' }}>
      <h1>Your chess identity</h1>
      <p style={{ fontSize: '2rem' }}>{snapshot.current_rating ?? '--'}</p>
      <div style={{ display: 'flex', gap: '2rem' }}>
        <div>
          <div style={{ fontSize: '1.5rem' }}>{stats.total_games.toLocaleString()}</div>
          <div>Total games</div>
        </div>
        <div>
          <div style={{ fontSize: '1.5rem' }}>{stats.analyzed_games.toLocaleString()}</div>
          <div>Analyzed games</div>
        </div>
        <div>
          <div style={{ fontSize: '1.5rem' }}>
            {stats.win_pct != null ? `${stats.win_pct.toFixed(1)}%` : '--'}
          </div>
          <div>Win rate</div>
        </div>
        <div>
          <div style={{ fontSize: '1.5rem' }}>
            {stats.acpl != null ? stats.acpl.toFixed(1) : '--'}
          </div>
          <div>ACPL</div>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 6: Install dependencies**

```bash
cd frontend && npm install
```

Expected: completes without error (mirrors `dashboard/components/chessboard/frontend`'s
already-working install, same React 18 / Vite 5 versions).

- [ ] **Step 7: Run against the real API (2 terminals)**

Terminal 1 (from repo root): `.venv/bin/uvicorn api.main:app --port 8123`
Terminal 2: `cd frontend && npm run dev`
Open `http://127.0.0.1:5173` in a browser.
Expected: page renders real rating + 4 stat tiles matching Task 4 Step 3's `curl` output
— not zeros, not "Loading..." stuck forever.

- [ ] **Step 8: Commit**

```bash
git add frontend/
git commit -m "Add React/Vite frontend slice rendering real Overview data"
```

---

### Task 8: Record spike findings

**Files:**
- Modify: `docs/scoping/fastapi-integration-scoping.md` (append findings under the §8
  section added in Task 1)

**Interfaces:** None (documentation only) — this is the plan's final task.

- [ ] **Step 1: Append findings**

Add real, specific results to §8 (added in Task 1) — a template of what to fill in
(replace bracketed parts with what actually happened across Tasks 2-7, don't leave the
brackets in):

```markdown

### Findings (2026-07-12 spike)

- `get_connections()` outside Streamlit: [confirmed working / found an issue: describe]
- Standalone FastAPI service: [3 endpoints served real data / issue: describe]
- Subprocess start/stop (api/spike_launcher.py): [clean, no orphan process / issue]
- PyInstaller freeze (api_spike.spec): [built and ran cleanly / issue, e.g. DuckDB
  extension network fetch, hidden-import gap]
- React/Vite frontend: [rendered real data end-to-end / issue]
- Open risks still unresolved: Windows/macOS packaging (untested, Linux dev machine
  only); whether a full 21-page migration is worth the cost (not estimated by this spike).
```

- [ ] **Step 2: Commit**

```bash
git add docs/scoping/fastapi-integration-scoping.md
git commit -m "Record frontend-rewrite spike findings"
```
