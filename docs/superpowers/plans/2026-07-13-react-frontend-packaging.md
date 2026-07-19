# React Frontend Packaging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Package the React/Vite frontend into a real, distributable, pure-React desktop build (zero streamlit in its dependency closure) that runs alongside the existing Streamlit app, per `docs/superpowers/specs/2026-07-13-react-frontend-packaging-design.md`.

**Architecture:** Split `dashboard/_common.py` and `dashboard/live_engine.py` so their streamlit-free logic (DB connections, engine-status) lives in two new plain modules the API can import without pulling in streamlit; add asset-serving + SPA-fallback routes to `api/main.py`; graduate `api/spike_launcher.py` into a real pywebview launcher (`react_desktop_app.py`); package it all via a new `chesswright-react.spec` and a build script that runs `npm run build` first.

**Tech Stack:** Python 3.12, FastAPI/uvicorn/starlette, PyInstaller, pywebview, React + Vite (existing `frontend/`), pytest.

## Global Constraints

- Zero streamlit in `chesswright-react.spec`'s dependency closure — verify by inspecting the frozen bundle's `_internal/` directory, not just by reading source.
- Every extraction preserves exact current behavior for the Streamlit app — "done" means the full existing test suite is green after each change, not just new tests passing.
- `chesswright-react.spec`/`react_desktop_app.py` are additive — `chesswright.spec`/`desktop_app.py`/`build.yml` must not change.
- No new placeholder config keys or speculative abstractions — only what this plan's tasks actually need.
- Reuse proven patterns verbatim rather than re-deriving them: the DuckDB snapshot/locking machinery, the frozen-executable re-invocation dispatch (`--flag` not `-m module`), and `desktop_app.py`'s existing helpers (`ensure_user_data`, `resource_dir`, `free_port`, `wait_for_server`, `check_cpu_compat`, `check_webview2`) via direct import, not copies.

---

### Task 1: Extract `connections.py` from `dashboard/_common.py`

**Files:**
- Create: `connections.py` (repo root)
- Modify: `dashboard/_common.py` (shrink to Streamlit-only helpers + a thin wrapper)
- Modify: `tests/unit/test_duck_snapshot.py` (retarget `_common` → `connections`)
- Modify: `tests/unit/test_duckdb_extension_loading.py` (retarget `_common` → `connections`)
- Create: `tests/unit/test_connections.py` (new coverage for `open_connections()`/`DiskSpaceError`/`clear_cache()`)

**Interfaces:**
- Produces: `connections.get_duckdb_connection(db_path)`, `connections.get_sqlite_connection(db_path)`, `connections.resolve_db_path(cli_db_path=None, config_path=None)`, `connections.get_config(config_path=None)`, `connections.open_connections() -> (sqlite_conn, duck_conn)`, `connections.clear_cache()`, `connections.DiskSpaceError(RuntimeError)`, `connections._duck_snapshot_path`, `connections._cleanup_stale_snapshots`, `connections._build_duck_snapshot`, `connections._bundled_sqlite_extension_path`, `connections._load_duckdb_sqlite_extension`. All later tasks that need a DB connection import from here, not from `dashboard/_common.py`.
- Consumes: nothing from earlier tasks (this is the first task).

- [ ] **Step 1: Read the current file to confirm line numbers haven't shifted**

Run: `sed -n '1,30p' dashboard/_common.py` and confirm it still matches the version this plan was written against (imports: `atexit, os, pathlib, sqlite3, sys, threading, time`, then `duckdb, pandas as pd, streamlit as st`, then `confidence`, `config.load_config/pick`, `db.get_connection as _get_sqlite_connection`, `migrate`).

- [ ] **Step 2: Create `connections.py` with the extracted, streamlit-free logic**

```python
"""Streamlit-free DB connection helpers, shared by the Streamlit
dashboard (via dashboard/_common.py's thin @st.cache_resource wrapper,
see that module) and the FastAPI service (api/db.py) directly.

Extracted from dashboard/_common.py (2026-07-13) so the React/FastAPI
packaging path (docs/superpowers/specs/2026-07-13-react-frontend-
packaging-design.md) doesn't pull in streamlit merely because several of
dashboard/data/*.py's modules imported get_config/get_duckdb_connection/
get_sqlite_connection from the same file that also defined the
@st.cache_resource-decorated get_connections(). The DuckDB per-PID
snapshot + locked-connection machinery below is the hard-won fix for a
real corruption incident (see the duckdb_sqlite_same_process_hazard
project memory) -- moved here with IDENTICAL behavior, not reinvented.

Lives at the repo root (not dashboard/) so both api/db.py (which already
puts the repo root on sys.path) and dashboard/_common.py (which already
does the same) can import it with a plain `import connections` -- no new
sys.path wiring needed, matching how config.py/db.py/migrate.py already
work as flat root-level modules.
"""
import atexit
import os
import pathlib
import shutil
import sqlite3
import threading
import time

import duckdb

from config import load_config, pick
from db import get_connection as _get_sqlite_connection
import migrate

# Lock-acquire timeout for _LockedDuckDBResult's terminal fetch methods --
# generous (10s dwarfs any real query on this dashboard's data sizes, see
# tests/performance's benchmarks), but finite so a bug that forgets to call
# a terminal fetch method fails loudly (TimeoutError) instead of silently
# wedging the whole app for every other session forever.
_DUCK_LOCK_TIMEOUT_SEC = 10


class _LockedDuckDBResult:
    """Proxy returned by _LockedDuckDBConnection.execute(). Holds the lock
    from execute() through whichever terminal fetch method the caller uses
    -- fetchone/fetchall/fetchdf are the only three ever called on a
    duck_conn result anywhere in this codebase (confirmed by grep). The
    critical section has to span execute()+fetch() together, not just
    execute() alone: those are two separate calls on the SAME shared
    connection object, and a second thread's execute() landing in between
    them is the actual race (confirmed live -- see the Ask page crash this
    class exists to fix), not just execute() itself."""

    def __init__(self, conn, lock):
        self._conn = conn
        self._lock = lock
        self._released = False

    def _release(self):
        if not self._released:
            self._released = True
            self._lock.release()

    def fetchone(self):
        try:
            return self._conn.fetchone()
        finally:
            self._release()

    def fetchall(self):
        try:
            return self._conn.fetchall()
        finally:
            self._release()

    def fetchdf(self):
        try:
            return self._conn.fetchdf()
        finally:
            self._release()

    def __del__(self):
        # Safety net: if a caller's execute() is never followed by a
        # terminal fetch (shouldn't happen -- see the grep above -- but a
        # forgotten fetch must not permanently wedge every other session's
        # queries), release on garbage collection rather than deadlock.
        self._release()


class _LockedDuckDBConnection:
    """Serializes access to a single shared DuckDB connection across every
    concurrent Streamlit session/thread. dashboard/_common.py's
    get_connections() (via this module's open_connections()) caches one
    process-wide connection object, not one per session -- and DuckDB's
    Python connection isn't safe for concurrent multi-threaded query
    execution without external synchronization. Same fix shape as
    dashboard/engine_status.py's EngineService, applied here to the
    DuckDB connection instead of the Stockfish subprocess.

    Also owns the snapshot lifecycle (see get_duckdb_connection): queries
    run against a private read-only snapshot of source_db_path, never the
    live file, so new data only appears after refresh_snapshot()."""

    def __init__(self, conn, source_db_path):
        self._conn = conn
        self._source_db_path = source_db_path
        self._lock = threading.Lock()

    def refresh_snapshot(self):
        """Re-copies the live database into this connection's snapshot and
        re-attaches it -- the one way duck-side reads pick up new data.
        Called from app.py's "Refresh data" button, the same explicit
        refresh point new games already flow through (st.cache_data has no
        ttl -- see that button's comment). Takes the query lock so an
        in-flight execute()+fetch never straddles the DETACH/ATTACH."""
        if not self._lock.acquire(timeout=_DUCK_LOCK_TIMEOUT_SEC):
            raise TimeoutError(
                "Timed out waiting for the shared DuckDB connection lock "
                "before refreshing its database snapshot."
            )
        try:
            self._conn.execute("DETACH db")
            snapshot = _build_duck_snapshot(self._source_db_path)
            self._conn.execute(f"ATTACH '{snapshot}' AS db (TYPE sqlite, READ_ONLY)")
        finally:
            self._lock.release()

    def execute(self, *args, **kwargs):
        if not self._lock.acquire(timeout=_DUCK_LOCK_TIMEOUT_SEC):
            raise TimeoutError(
                "Timed out waiting for the shared DuckDB connection lock -- "
                "a caller likely executed a query without calling a terminal "
                "fetchone()/fetchall()/fetchdf(), holding the lock forever."
            )
        try:
            self._conn.execute(*args, **kwargs)
        except Exception:
            self._lock.release()
            raise
        return _LockedDuckDBResult(self._conn, self._lock)

    def __getattr__(self, name):
        # Anything other than execute() (e.g. .close()) passes through
        # unlocked -- nothing else is called on duck_conn anywhere in this
        # codebase (confirmed by grep), so this is a safety net, not a
        # sanctioned concurrent-access path.
        return getattr(self._conn, name)


_ATTACH_RETRY_ATTEMPTS = 3
_ATTACH_RETRY_DELAY_SEC = 0.5


# ---------- DuckDB snapshot isolation ----------
# DuckDB must NEVER attach the live database file. Root cause, reproduced
# deterministically 2026-07-04 (not theorized): DuckDB's ATTACH (TYPE
# sqlite) uses its own embedded SQLite library, independent of python's
# sqlite3 module -- two SQLite copies in ONE process. POSIX fcntl locks
# provide no exclusion within a single process, so each library's WAL
# checkpoint/recovery/close logic runs as if the other's connections don't
# exist. Reproduced outcomes on the real database: "disk I/O error" on a
# writer AND on the shared reader's next query (the Openings-page field
# crash), "file is not a database" on a previously-healthy connection, a
# SIGBUS process crash (mmap'd -shm truncated under a mapping; READ_ONLY
# on the attach does NOT prevent it), and outright database corruption
# (the 2026-07-04 chess.db incident). Serializing duck queries against
# write transactions with a process-wide lock was tried first and STILL
# reproduced "file is not a database" -- DuckDB's scan-pool sqlite
# connections open/close on its own schedule (background threads), so
# call-level mutual exclusion cannot contain it. The only sound in-process
# arrangement is for the two libraries to touch different files: DuckDB
# gets a private, read-only SNAPSHOT copy, rebuilt only at explicit
# refresh points (app start, the sidebar "Refresh data" button, cache
# clears) -- which matches the app's existing freshness contract, since
# new games already only appear after "Refresh data" (see app.py).
#
# The snapshot is per-PID so two running instances never share one (a
# rebuild would truncate a file the other process has mmap'd -- the same
# SIGBUS mechanism). Stale snapshots from dead processes are cleaned up on
# the next connection; our own is removed atexit.

def _duck_snapshot_path(db_path) -> pathlib.Path:
    p = pathlib.Path(db_path)
    return p.parent / f".{p.name}.duck-snapshot-{os.getpid()}"


def _cleanup_stale_snapshots(db_path):
    p = pathlib.Path(db_path)
    for snap in p.parent.glob(f".{p.name}.duck-snapshot-*"):
        try:
            pid = int(snap.name.rsplit("-", 1)[1])
        except ValueError:
            continue  # not a name this code wrote
        if pid == os.getpid():
            continue
        try:
            if os.name == "posix":
                # Liveness probe: signal 0 delivers nothing. A live owner's
                # snapshot must be left alone -- DuckDB's scan pool reopens
                # the file BY PATH, so unlinking it under a live process
                # breaks that process's queries.
                os.kill(pid, 0)
                continue  # alive
            # Windows has no safe probe (os.kill(pid, 0) TERMINATES the
            # process there) -- attempt the delete instead and let the OS
            # protect a live owner's attached file via sharing violation.
            snap.unlink(missing_ok=True)
        except ProcessLookupError:
            try:
                snap.unlink(missing_ok=True)
            except OSError:
                pass
        except PermissionError:
            pass  # posix: pid alive under another user; windows: file in use


def _build_duck_snapshot(db_path) -> str:
    """Copies db_path to this process's private snapshot via sqlite's
    backup API (a consistent point-in-time copy even against concurrent
    writers -- same mechanism and reasoning as db_import.import_database),
    then flips the copy to journal_mode=DELETE so DuckDB's read-only
    attach involves no WAL/-shm machinery at all."""
    snap = _duck_snapshot_path(db_path)
    src = sqlite3.connect(db_path)
    src.execute("PRAGMA busy_timeout = 5000")
    try:
        snap.unlink(missing_ok=True)
        dest = sqlite3.connect(str(snap))
        try:
            src.backup(dest)
            dest.execute("PRAGMA journal_mode = DELETE")
        finally:
            dest.close()
    finally:
        src.close()
    atexit.register(snap.unlink, missing_ok=True)  # idempotent if re-registered
    return str(snap)


def _bundled_sqlite_extension_path():
    # This module lives at the repo root (one level up from where
    # dashboard/_common.py used to define this same function), so it's
    # one fewer ".parent" hop to the same target directory. In the frozen
    # bundle, this file and duckdb_extensions/ are sibling entries under
    # _internal/ (see chesswright.spec / chesswright-react.spec); in a
    # source checkout the same relative location is the repo root, where
    # the directory normally doesn't exist -- that's the INSTALL fallback.
    return pathlib.Path(__file__).resolve().parent \
        / "duckdb_extensions" / "sqlite_scanner.duckdb_extension"


def _load_duckdb_sqlite_extension(conn):
    """DuckDB's sqlite extension is NOT part of the duckdb wheel --
    `INSTALL sqlite` downloads it from extensions.duckdb.org on first
    use. A Windows pilot tester whose machine couldn't reach that host
    got an IOException before the app drew a single page, so packaged
    builds now ship the extension file (fetched at build time by
    scripts/fetch_duckdb_extensions.py, mapped by chesswright.spec to
    _internal/duckdb_extensions/, i.e. this file's parent's parent) and
    load it from disk -- first launch needs no network at all. The
    INSTALL path survives only as the fallback for source checkouts
    (where the bundled file doesn't exist) and as a rescue if the
    bundled copy is somehow unloadable on a machine that does have
    network."""
    bundled = _bundled_sqlite_extension_path()
    if bundled.exists():
        # SQL-escape the quotes: a Windows install path can legitimately
        # contain one (C:/Users/O'Brien/...).
        quoted = bundled.as_posix().replace("'", "''")
        try:
            conn.execute(f"LOAD '{quoted}'")
            return
        except duckdb.Error:
            pass
    try:
        conn.execute("INSTALL sqlite; LOAD sqlite;")
    except duckdb.Error as e:
        raise RuntimeError(
            "Chesswright could not load DuckDB's sqlite extension. The "
            "packaged app ships it built in; running from source needs "
            "one-time internet access so DuckDB can download it "
            "(`INSTALL sqlite`), or run "
            "`python scripts/fetch_duckdb_extensions.py` once while "
            "online."
        ) from e


def get_duckdb_connection(db_path):
    """Snapshots db_path (see the snapshot-isolation comment above) and
    attaches the snapshot read-only. Retried because the backup's read of
    a live source can transiently collide with another writer mid-commit
    -- the same "first open right as a background analysis thread flips
    to done" race the original live-file ATTACH retry was added for
    (caught live on the Opponent Prep page)."""
    conn = duckdb.connect()
    _load_duckdb_sqlite_extension(conn)
    _cleanup_stale_snapshots(db_path)
    for attempt in range(1, _ATTACH_RETRY_ATTEMPTS + 1):
        try:
            snapshot = _build_duck_snapshot(db_path)
            conn.execute(f"ATTACH '{snapshot}' AS db (TYPE sqlite, READ_ONLY)")
            break
        except (duckdb.Error, sqlite3.Error):
            if attempt == _ATTACH_RETRY_ATTEMPTS:
                raise
            time.sleep(_ATTACH_RETRY_DELAY_SEC)
    return _LockedDuckDBConnection(conn, db_path)


def get_sqlite_connection(db_path):
    """check_same_thread=False -- see db.get_connection's docstring.
    Caveat worth knowing, not just silently working around: this allows
    cross-thread use but doesn't make the connection safe for truly
    CONCURRENT access from multiple threads at once. Fine for a
    single-user personal dashboard where reruns happen one at a time;
    would need real per-session connections if this ever serves multiple
    simultaneous users."""
    return _get_sqlite_connection(db_path, check_same_thread=False)


def resolve_db_path(cli_db_path=None, config_path=None):
    # Pro profile takes precedence when active, unless a specific path or
    # config was explicitly requested by the caller (CLI flags, import flow).
    if not cli_db_path and not config_path:
        from config import get_active_profile, get_profile_db_path
        active = get_active_profile()
        if active:
            return str(get_profile_db_path(active))
    cfg = load_config(config_path)
    return pick(cli_db_path, cfg["database"]["path"])


def get_config(config_path=None):
    if not config_path:
        from config import get_active_profile, get_profile_config_path
        active = get_active_profile()
        if active:
            profile_cfg = get_profile_config_path(active)
            if profile_cfg.exists():
                return load_config(str(profile_cfg))
    return load_config(config_path)


class DiskSpaceError(RuntimeError):
    """Raised by open_connections() when migrate.migrate() fails AND the
    volume holding the database has < 0.5 GB free -- almost certainly the
    actual cause. dashboard/_common.py's get_connections() catches this
    specifically to show a Streamlit-native error + st.stop(); a plain
    caller (api/db.py, via open_connections() directly) sees a normal
    Python exception with the same actionable message."""


_cached_connections = None
_cache_lock = threading.Lock()


def open_connections():
    """One SQLite connection + one DuckDB connection for the whole
    process (a plain module-level singleton, not per-caller) -- the
    streamlit-free equivalent of dashboard/_common.py's @st.cache_
    resource-decorated get_connections(). Extracted so api/db.py can
    share the exact same connection-opening logic (including the
    hard-won DuckDB snapshot machinery above) without importing
    streamlit at all."""
    global _cached_connections
    if _cached_connections is not None:
        return _cached_connections
    with _cache_lock:
        if _cached_connections is not None:
            return _cached_connections
        db_path = resolve_db_path()
        try:
            migrate.migrate(db_path)
        except Exception as exc:
            free_gb = None
            try:
                db_dir = pathlib.Path(db_path).parent
                free_gb = shutil.disk_usage(db_dir).free / 1e9
            except Exception:
                pass
            if free_gb is not None and free_gb < 0.5:
                raise DiskSpaceError(
                    f"**Database error — disk is almost full** "
                    f"({free_gb:.1f} GB free on the volume holding your database). "
                    "Free up at least 1 GB and restart Chesswright.\n\n"
                    f"Database path: `{db_path}`"
                ) from exc
            raise
        _cached_connections = (get_sqlite_connection(db_path), get_duckdb_connection(db_path))
        return _cached_connections


def clear_cache():
    """Test-only hook: open_connections() is a process-wide singleton, so
    a value cached by one test would otherwise leak into the next one --
    same reason dashboard/_common.py's get_connections is @st.cache_
    resource-decorated (which already exposes its own .clear()) and
    api/main.py's _TTLCache exposes reset_caches()."""
    global _cached_connections
    _cached_connections = None
```

- [ ] **Step 3: Shrink `dashboard/_common.py` to Streamlit-only helpers + a thin wrapper**

Replace the whole file with:

```python
"""Shared Streamlit-only helpers for the Phase 6 dashboard. The DuckDB/
SQLite connection machinery this file used to own directly now lives in
connections.py (extracted 2026-07-13 so the FastAPI/React service can
reuse it without importing streamlit) -- see connections.py's own
docstring and docs/superpowers/specs/2026-07-13-react-frontend-
packaging-design.md. Every name previously defined here that still has
non-Streamlit callers is re-exported below so no existing dashboard/
*_view.py or dashboard/data/*.py import breaks.
"""
import pathlib
import sys

import pandas as pd
import streamlit as st

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import confidence
from connections import (  # noqa: F401 -- re-exported for existing callers
    DiskSpaceError, get_config, get_duckdb_connection, get_sqlite_connection,
    resolve_db_path,
)
import connections


@st.cache_resource(show_spinner="Opening your game database…")
def get_connections():
    """One SQLite connection + one DuckDB connection for the whole server
    session (st.cache_resource, not cache_data -- these are live
    connections, not serializable results). The actual connection-opening
    logic (including the hard-won DuckDB snapshot isolation) lives in
    connections.open_connections(); this decorator is what makes every
    page module (game_explorer_view.py, game_detail_view.py, app.py
    itself) share the SAME cached singleton -- two separately-defined
    get_connections() functions in different modules would each get their
    OWN cache entry (Streamlit keys st.cache_resource by function
    identity), silently reopening the connection and re-triggering the
    ~94s structure_ctx rebuild cost this caching exists to avoid in the
    first place."""
    try:
        return connections.open_connections()
    except DiskSpaceError as e:
        st.error(str(e))
        st.stop()


# get_connections.clear() (Streamlit's cache_resource API) only clears
# THIS decorator's own cache -- it would leave connections.py's own
# process-wide singleton stale, so a caller expecting .clear() to force a
# genuinely fresh connection pair (dashboard/test_app.py, tests/ui/
# test_pages.py, and this project's other existing tests all do exactly
# that after repointing config at a different db_path) would silently get
# the OLD connections back. Chain both caches so the existing .clear()
# contract keeps meaning what every caller already assumes it means.
_st_clear = get_connections.clear


def _clear_both_caches():
    connections.clear_cache()
    _st_clear()


get_connections.clear = _clear_both_caches


def game_labels(game_ids) -> dict:
    """game_id -> a label a player recognizes ('vs masterkim (W, win) 2025.05.16').
    Point lookups on the games PK via the plain sqlite connection -- never
    routed through duck_conn (see the audit-dashboard-queries recipe)."""
    ids = [g for g in dict.fromkeys(game_ids) if g]
    if not ids:
        return {}
    sqlite_conn, _ = get_connections()
    qmarks = ",".join("?" * len(ids))
    rows = sqlite_conn.execute(
        f"SELECT id, opponent_name, player_color, outcome_for_player, utc_date "
        f"FROM games WHERE id IN ({qmarks})", ids).fetchall()
    out = {}
    for gid, opp, color, outcome, date in rows:
        c = {"white": "W", "black": "B"}.get(color, "?")
        out[gid] = f"vs {opp or 'unknown'} ({c}, {outcome or '?'}) {date or ''}".strip()
    return out


def navigate_on_row_click(df, key, detail_page, self_page, return_label, column_config=None):
    """One shared drill-down mechanism (Phase 6c.4): renders df with
    native st.dataframe row selection, and on a click, stores the
    selected row's game_id + where to return to, then switches to Game
    Detail. df MUST have a game_id column. Used by every Tactical
    Highlights/Matchups & Opponents panel that lists individual games --
    avoids re-typing the same on_select/session_state wiring per panel.

    Display transforms applied here so every drill-down table behaves the
    same way (UX review 2026-07-05):
    - game_id values are shown as a human game label (opponent, color,
      result, date) -- a raw platform id like 'ODeMleHV' identifies
      nothing to a player. The real id still drives the click handler.
    - ply/blunder_ply columns are converted to chess move numbers
      ((ply+1)//2, kept numeric so column sorting still works).
    - the pandas index is hidden (it's meaningless row positions)."""
    ids = df["game_id"].tolist() if "game_id" in df.columns else []
    display_df = df.reset_index(drop=True).copy()
    if ids:
        labels = game_labels(ids)
        display_df["game_id"] = [labels.get(g, g) for g in display_df["game_id"]]
    for ply_col in ("ply", "blunder_ply"):
        if ply_col in display_df.columns:
            display_df[ply_col] = display_df[ply_col].map(
                lambda p: (int(p) + 1) // 2 if pd.notna(p) else p)
    selection = st.dataframe(display_df, width='stretch', on_select="rerun",
                              selection_mode="single-row", key=key,
                              hide_index=True, column_config=column_config)
    st.caption("Tick the checkbox at the left of a row to open that game's full detail.")
    rows = selection.selection.rows if selection and selection.selection else []
    if rows:
        st.session_state["selected_game_id"] = ids[rows[0]]
        st.session_state["return_page"] = self_page
        st.session_state["return_page_label"] = return_label
        st.switch_page(detail_page)


# ---------- get_career_findings() rendering (shared by Insights + Training Queue) ----------
SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}

_SEVERITY_CHIPS = {
    "high": ("chip-negative", "High impact"),
    "medium": ("chip-neutral", "Medium impact"),
    "low": ("chip-muted", "Low impact"),
}

CATEGORY_LABELS = {
    "tactical": "Tactics",
    "time": "Time management",
    "defense": "King safety",
    "matchup": "Matchups",
    "giant_killer": "Giant-killing",
    "general": "General",
}

DRILL_PRESETS = {
    "Piece blunder hot-spot": {
        "include_motifs": True,
        "include_moments": False,
        "include_holes": False,
        "motif_filter": None,
    },
    "Tactical highlights so far": {
        "include_motifs": True,
        "include_moments": False,
        "include_holes": False,
        "motif_filter": None,
    },
    "King moves off the back rank": {
        "include_motifs": True,
        "include_moments": False,
        "include_holes": False,
        "motif_filter": "back_rank_mate",
    },
}


def finding_chips_html(finding) -> str:
    """Confidence + severity + category chips for one finding, as HTML. Empty string if none apply."""
    chips = []
    if finding.get("confidence"):
        badge = confidence.confidence_badge_html(finding["confidence"])
        if badge:
            chips.append(badge)
    severity_entry = _SEVERITY_CHIPS.get(finding.get("severity"))
    if severity_entry:
        cls, label = severity_entry
        chips.append(f'<span class="chip {cls}">{label}</span>')
    category_label = CATEGORY_LABELS.get(finding.get("category"))
    if category_label:
        chips.append(f'<span class="chip chip-neutral">{category_label}</span>')
    return "".join(chips)


def render_finding_actions(finding, drill_export_page, prep_page) -> None:
    drill_preset = DRILL_PRESETS.get(finding["title"])
    if drill_preset and drill_export_page:
        if st.button("→ Export practice positions",
                     key=f"drill_{finding['title']}",
                     help="Open Drill Export with this weakness pre-selected."):
            st.session_state["_drill_preset"] = drill_preset
            st.switch_page(drill_export_page)

    if (finding["title"] == "Toughest opponent"
            and prep_page
            and finding.get("opponent_name")
            and finding.get("opponent_on_lichess", True)):
        if st.button("→ Scout this opponent",
                     key="scout_nemesis",
                     help="Open Opponent Prep with this player's username pre-filled."):
            st.session_state["_prep_username"] = finding["opponent_name"]
            st.switch_page(prep_page)


def render_where_next(links) -> None:
    """Bottom-of-page cross-link panel (roadmap §28 Q1). `links` is a
    list of (label, target_page) pairs; entries whose target_page is
    None are skipped (same "page might not be wired in yet" guard as
    render_finding_actions above)."""
    live_links = [(label, page) for label, page in links if page is not None]
    if not live_links:
        return
    st.divider()
    st.subheader("Where next?")
    cols = st.columns(len(live_links))
    for col, (label, page) in zip(cols, live_links):
        with col:
            if st.button(label, key=f"where_next_{label}", width="stretch"):
                st.switch_page(page)


def persist_filter(key: str) -> None:
    """Mirror a keyed widget's current value into a plain (non-widget)
    session_state entry so it survives st.navigation's page-switch
    widget-state garbage collection -- confirmed live 2026-07-11 (roadmap
    §28 Q3): keyed widget state does NOT survive page-away-and-back on
    its own in this app. Call this right after creating a keyed widget
    whose value should persist across navigation."""
    st.session_state[f"_persist_{key}"] = st.session_state[key]


def restore_filter_default(key: str, fallback) -> None:
    """Call BEFORE a keyed widget is created (Streamlit requires a
    widget's key be set in session_state before the widget call, not
    after). Seeds session_state[key] from the mirror persist_filter()
    wrote the last time this filter was touched, but only if
    session_state[key] isn't already present this run -- i.e. exactly
    the nav-away-and-back case; a value already present this run (e.g.
    from the widget's own rerun) must not be clobbered."""
    if key not in st.session_state:
        st.session_state[key] = st.session_state.get(f"_persist_{key}", fallback)
```

- [ ] **Step 4: Retarget `tests/unit/test_duck_snapshot.py` at `connections`**

Replace its `import _common` with `import connections`, and every `_common.X` reference with `connections.X` (`_common.get_duckdb_connection` → `connections.get_duckdb_connection`, `_common._duck_snapshot_path` → `connections._duck_snapshot_path`, etc.). Update the module docstring's first line from `Tests for _common.py's DuckDB snapshot isolation` to `Tests for connections.py's DuckDB snapshot isolation`. No logic changes — every assertion stays identical.

- [ ] **Step 5: Retarget `tests/unit/test_duckdb_extension_loading.py` at `connections`**

Same mechanical change: `import _common` → `import connections`, `_common._bundled_sqlite_extension_path`/`_common._load_duckdb_sqlite_extension` → `connections.` equivalents, docstring's `_common.py's` → `connections.py's`.

- [ ] **Step 6: Write new tests for `open_connections()`/`DiskSpaceError`/`clear_cache()`**

Create `tests/unit/test_connections.py`:

```python
"""Unit tests for connections.py's open_connections()/DiskSpaceError/
clear_cache() -- the process-wide-singleton behavior that api/db.py
depends on directly (no streamlit involved), and that dashboard/
_common.py's get_connections() wraps for the Streamlit app.
"""
import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

import connections


@pytest.fixture(autouse=True)
def _clear_connections_cache():
    connections.clear_cache()
    yield
    connections.clear_cache()


def test_open_connections_returns_same_objects_on_repeat_calls(migrated_db_path, monkeypatch):
    monkeypatch.setattr(connections, "resolve_db_path", lambda *a, **k: migrated_db_path)
    sqlite_conn1, duck_conn1 = connections.open_connections()
    sqlite_conn2, duck_conn2 = connections.open_connections()
    assert sqlite_conn1 is sqlite_conn2
    assert duck_conn1 is duck_conn2


def test_clear_cache_forces_a_fresh_pair(migrated_db_path, monkeypatch):
    monkeypatch.setattr(connections, "resolve_db_path", lambda *a, **k: migrated_db_path)
    sqlite_conn1, _ = connections.open_connections()
    connections.clear_cache()
    sqlite_conn2, _ = connections.open_connections()
    assert sqlite_conn1 is not sqlite_conn2


def test_open_connections_raises_disk_space_error_when_disk_almost_full(monkeypatch, tmp_path):
    bad_db_path = str(tmp_path / "nonexistent" / "chess.db")
    monkeypatch.setattr(connections, "resolve_db_path", lambda *a, **k: bad_db_path)

    def _fail_migrate(_path):
        raise RuntimeError("simulated migrate failure")

    monkeypatch.setattr(connections.migrate, "migrate", _fail_migrate)

    class _FakeUsage:
        free = 0.1e9  # 0.1 GB, below the 0.5 GB threshold

    monkeypatch.setattr(connections.shutil, "disk_usage", lambda _dir: _FakeUsage())

    with pytest.raises(connections.DiskSpaceError, match="disk is almost full"):
        connections.open_connections()


def test_open_connections_reraises_original_error_when_disk_is_fine(monkeypatch, tmp_path):
    bad_db_path = str(tmp_path / "nonexistent" / "chess.db")
    monkeypatch.setattr(connections, "resolve_db_path", lambda *a, **k: bad_db_path)

    def _fail_migrate(_path):
        raise RuntimeError("simulated migrate failure, not disk-related")

    monkeypatch.setattr(connections.migrate, "migrate", _fail_migrate)

    class _FakeUsage:
        free = 50e9  # plenty of space

    monkeypatch.setattr(connections.shutil, "disk_usage", lambda _dir: _FakeUsage())

    with pytest.raises(RuntimeError, match="simulated migrate failure, not disk-related"):
        connections.open_connections()
```

- [ ] **Step 7: Run the new and retargeted tests**

Run: `pytest tests/unit/test_connections.py tests/unit/test_duck_snapshot.py tests/unit/test_duckdb_extension_loading.py -v`
Expected: all PASS.

- [ ] **Step 8: Run the full existing suite to confirm zero regressions in the Streamlit app**

Run: `pytest -x -q` (allow the known ~5-6 minute runtime; do not run this in a background job you then poll)
Expected: same pass/fail counts as before this task (this repo has a few pre-existing, already-documented flaky/failing tests unrelated to this change — compare against the baseline, don't expect literally zero failures).

- [ ] **Step 9: Commit**

```bash
git add connections.py dashboard/_common.py tests/unit/test_connections.py \
        tests/unit/test_duck_snapshot.py tests/unit/test_duckdb_extension_loading.py
git commit -m "Extract streamlit-free connections.py from dashboard/_common.py"
```

---

### Task 2: Point the 10 `dashboard/data/*.py` modules at `connections.py`

**Files:**
- Modify: `dashboard/data/matchups.py:5`
- Modify: `dashboard/data/game_endings.py:8`
- Modify: `dashboard/data/points.py:34`
- Modify: `dashboard/data/insights.py:24`
- Modify: `dashboard/data/analysis_batches.py:56`
- Modify: `dashboard/data/drills.py:29`
- Modify: `dashboard/data/prep.py:8`
- Modify: `dashboard/data/evolution.py:19`
- Modify: `dashboard/data/patterns.py:12`
- Modify: `dashboard/data/tactical.py:8`

**Interfaces:**
- Consumes: `connections.get_config`, `connections.get_duckdb_connection`, `connections.get_sqlite_connection` (Task 1).
- Produces: nothing new — this task removes `dashboard/data/*.py`'s only remaining transitive path to `streamlit` (via `_common.py`), which is what makes `import data` (used by `api/main.py`) streamlit-free.

- [ ] **Step 1: Change each file's import line (9 files import only `get_config`)**

In each of `dashboard/data/matchups.py`, `game_endings.py`, `points.py`, `insights.py`, `analysis_batches.py`, `drills.py`, `evolution.py`, `patterns.py`, `tactical.py`, change:

```python
from _common import get_config
```
to:
```python
from connections import get_config
```

- [ ] **Step 2: Change `dashboard/data/prep.py`'s import line (imports two names)**

Change:
```python
from _common import get_duckdb_connection, get_sqlite_connection
```
to:
```python
from connections import get_duckdb_connection, get_sqlite_connection
```

- [ ] **Step 3: Confirm no other `_common` references remain in these 10 files**

Run: `grep -n "_common" dashboard/data/matchups.py dashboard/data/game_endings.py dashboard/data/points.py dashboard/data/insights.py dashboard/data/analysis_batches.py dashboard/data/drills.py dashboard/data/prep.py dashboard/data/evolution.py dashboard/data/patterns.py dashboard/data/tactical.py`
Expected: no output (any hits would only be in comments/docstrings referencing `_common.py` historically — check by eye that nothing is a real import; this repo's convention keeps a few explanatory docstring mentions like "DuckDB (dashboard/data/_common.get_duckdb_connection)" in `board_chat.py`/`ai_coach.py`/`_shared.py`, which are prose, not imports, and are out of scope for this task).

- [ ] **Step 4: Confirm `import data` no longer imports streamlit**

Run:
```bash
python3 -c "
import sys
sys.path.insert(0, '.')
sys.path.insert(0, 'dashboard')
import data
assert 'streamlit' not in sys.modules, 'streamlit was imported transitively by data package'
print('OK: data package imported with zero streamlit')
"
```
Expected: prints `OK: data package imported with zero streamlit`.

- [ ] **Step 5: Run the data-layer integration tests**

Run: `pytest tests/integration/test_data_layer.py tests/unit/test_insights.py tests/integration/test_material_structure.py -v`
Expected: all PASS (these two test files still do `from _common import get_config`, which continues to work via `_common.py`'s re-export from Task 1 — no changes needed to them).

- [ ] **Step 6: Run the full existing suite**

Run: `pytest -x -q`
Expected: same baseline as Task 1's Step 8.

- [ ] **Step 7: Commit**

```bash
git add dashboard/data/matchups.py dashboard/data/game_endings.py dashboard/data/points.py \
        dashboard/data/insights.py dashboard/data/analysis_batches.py dashboard/data/drills.py \
        dashboard/data/prep.py dashboard/data/evolution.py dashboard/data/patterns.py \
        dashboard/data/tactical.py
git commit -m "Point dashboard/data/*.py at connections.py instead of _common.py"
```

---

### Task 3: Extract `dashboard/engine_status.py` from `dashboard/live_engine.py`

**Files:**
- Create: `dashboard/engine_status.py`
- Modify: `dashboard/live_engine.py` (shrink to Streamlit-only helpers + a thin `get_engine_service` wrapper)
- Create: `tests/unit/test_engine_status.py` (content moved from `test_live_engine.py`, retargeted)
- Modify: `tests/unit/test_live_engine.py` (add a regression test for the `.clear()` delegation)

**Interfaces:**
- Produces: `engine_status.LiveResult`, `engine_status.EngineService`, `engine_status.get_engine_service() -> EngineService | None`, `engine_status.get_engine_status_summary() -> dict`, `engine_status.clear_engine_service_cache()`, `engine_status._service_started` (module global). `api/main.py` (Task 5) imports `engine_status.get_engine_status_summary` directly.
- Consumes: nothing from earlier tasks (independent of Tasks 1/2).

- [ ] **Step 1: Create `dashboard/engine_status.py`**

```python
"""Streamlit-free on-demand-Stockfish state, shared by the Streamlit
dashboard (via dashboard/live_engine.py's thin get_engine_service()
wrapper) and the FastAPI service (api/main.py's engine-status endpoint)
directly.

Extracted from dashboard/live_engine.py (2026-07-13) so api/main.py's
`/api/overview/engine-status` endpoint doesn't pull in streamlit merely
by importing this module -- see docs/superpowers/specs/2026-07-13-
react-frontend-packaging-design.md. EngineService/LiveResult/
get_engine_service/get_engine_status_summary have zero streamlit calls in
their own bodies in the original file; only get_engine_service()'s
@st.cache_resource decorator did, replaced below with a plain
process-wide singleton (identical caching behavior, including caching a
legitimate None result -- see the _UNSET sentinel).

dashboard/live_engine.py keeps everything that actually touches
st.session_state/st.spinner/st.checkbox/st.caption
(render_confirm_toggle, get_or_analyse_position) -- those stay
Streamlit-only and unmoved.
"""
import atexit
import dataclasses
import json
import threading

import chess
import chess.engine

import config
import joblock
import worker


@dataclasses.dataclass
class LiveResult:
    eval_cp: int | None
    eval_mate: int | None
    best_move_san: str | None
    pv_json: str          # JSON-encoded list of SAN moves
    depth: int            # actual search depth reached
    engine_version: str


class EngineService:
    """Wraps a persistent Stockfish subprocess for on-demand analysis.

    Thread-safe via a single threading.Lock.  Restarts on failure up to
    _MAX_RESTARTS times.  Registers an atexit handler so the subprocess
    doesn't linger when the process exits.
    """

    _MAX_RESTARTS = 3

    def __init__(self, path: str, cfg: dict):
        self._path = path
        self._cfg = cfg
        self._engine: chess.engine.SimpleEngine | None = None
        self._engine_version = ""
        self._lock = threading.Lock()
        self._restart_count = 0
        self._dead = False
        self._start()
        atexit.register(self._shutdown)

    def _start(self) -> None:
        self._engine = chess.engine.SimpleEngine.popen_uci(self._path)
        self._engine_version = self._engine.id.get("name", "unknown")
        worker.configure_supported(self._engine, {
            "Threads": self._cfg.get("threads", 1),
            "Hash":    self._cfg.get("hash_mb", 32),
        })

    def _ensure_alive(self) -> bool:
        """Return True if the engine is ready.  Try to restart if it crashed."""
        if self._dead:
            return False
        if self._engine is not None:
            return True  # still alive; analyse() will set to None on failure
        if self._restart_count >= self._MAX_RESTARTS:
            self._dead = True
            return False
        self._restart_count += 1
        try:
            self._start()
            return True
        except Exception:
            self._engine = None
            if self._restart_count >= self._MAX_RESTARTS:
                self._dead = True
            return False

    def analyse(self, fen: str) -> LiveResult | None:
        """Analyse a position.  Returns None if engine unavailable or batch running."""
        lock_info = joblock.status()
        if lock_info is not None and lock_info.alive:
            return None  # hard block: never compete with batch

        time_sec = float(self._cfg.get("time_sec", 0.5))
        depth    = int(self._cfg.get("depth", 20))
        limit    = chess.engine.Limit(time=time_sec, depth=depth)

        with self._lock:
            if not self._ensure_alive():
                return None
            try:
                board = chess.Board(fen)
                info  = self._engine.analyse(board, limit)
            except Exception:
                self._engine = None  # trigger restart on next call
                return None

        score = info.get("score")
        if score is None:
            return None

        eval_cp, eval_mate = worker.score_to_fields(score, board.turn)

        pv_moves = info.get("pv", [])
        b, pv_sans = board.copy(), []
        for m in pv_moves[:15]:
            try:
                pv_sans.append(b.san(m))
                b.push(m)
            except Exception:
                break

        return LiveResult(
            eval_cp=eval_cp,
            eval_mate=eval_mate,
            best_move_san=pv_sans[0] if pv_sans else None,
            pv_json=json.dumps(pv_sans),
            depth=info.get("depth", 0),
            engine_version=self._engine_version,
        )

    def _shutdown(self) -> None:
        if self._engine:
            try:
                self._engine.quit()
            except Exception:
                pass
        self._engine = None


_service_started = False

_UNSET = object()
_cached_service = _UNSET
_cache_lock = threading.Lock()


def get_engine_service() -> EngineService | None:
    """Process-wide singleton, including caching a legitimate None result
    (Stockfish not found) -- mirrors what the original @st.cache_resource
    decorator did (Streamlit caches whatever a decorated function returns,
    None included, until .clear()). _UNSET (not None) is the "never
    computed yet" sentinel so a real None doesn't trigger a rebuild on
    every call."""
    global _cached_service, _service_started
    if _cached_service is not _UNSET:
        return _cached_service
    with _cache_lock:
        if _cached_service is not _UNSET:
            return _cached_service
        _service_started = True
        cfg = config.load_config()
        ie_cfg = cfg.get("interactive_engine", {})
        path = worker.find_engine_path(cfg.get("engine", {}).get("path"))
        if not path:
            _cached_service = None
            return _cached_service
        try:
            _cached_service = EngineService(path, ie_cfg)
        except Exception:
            _cached_service = None
        return _cached_service


def clear_engine_service_cache():
    """Test hook / settings-change hook: get_engine_service() is a
    process-wide singleton, so this is the explicit way to force a
    reconnect. dashboard/live_engine.py's get_engine_service.clear()
    attribute (see that module) delegates here -- it's the same single
    source of truth dashboard/settings_view.py's existing call sites
    already expect (force a fresh EngineService after the user changes
    the engine path)."""
    global _cached_service
    _cached_service = _UNSET


def get_engine_status_summary() -> dict:
    """Cheap, read-only status for display (Overview's status strip, both
    the Streamlit and React versions). Only reports on an engine ALREADY
    started elsewhere (e.g. Game Detail's interactive analysis panel) --
    never calls get_engine_service() as the first caller, since that's
    what actually constructs a real Stockfish subprocess on its
    first-ever invocation. Viewing Overview must never be what eagerly
    starts the engine for a user who never opened an interactive-analysis
    feature."""
    if not _service_started:
        return {"connected": False, "version": None}
    service = get_engine_service()
    if service is None:
        return {"connected": False, "version": None}
    return {"connected": not service._dead, "version": service._engine_version or None}
```

- [ ] **Step 2: Shrink `dashboard/live_engine.py`**

Replace the whole file with:

```python
"""On-demand Stockfish analysis for interactive Streamlit dashboard
panels. The streamlit-free core (EngineService, LiveResult,
get_engine_service, get_engine_status_summary) moved to
dashboard/engine_status.py (2026-07-13) so api/main.py can use engine
status without importing streamlit -- see that module's docstring. This
file keeps only what actually touches st.session_state/st.spinner/
st.checkbox/st.caption.

A threading.Lock (inside EngineService, in engine_status.py) serialises
analyse() calls from rapid reruns.
"""
import config
import joblock
import streamlit as st

import chess_display
import engine_status
from engine_status import EngineService, LiveResult, get_engine_status_summary  # noqa: F401 -- re-exported


def get_engine_service():
    """Thin wrapper: the real process-wide singleton lives in
    engine_status.py so api/main.py can reuse it without importing
    streamlit. .clear() is attached below so dashboard/settings_view.py's
    existing live_engine.get_engine_service.clear() calls (force a
    reconnect after an engine-path change) keep clearing the SAME cache
    engine_status.py owns, not a second, independently-stale one."""
    return engine_status.get_engine_service()


get_engine_service.clear = engine_status.clear_engine_service_cache


def batch_running() -> bool:
    """True when the batch worker holds the joblock and its process is alive."""
    info = joblock.status()
    return info is not None and info.alive


def _result_to_dict(live_result: LiveResult) -> dict:
    """LiveResult -> the {eval_cp, ..., source} dict shape callers display.
    source is derived from engine_version rather than tracked separately --
    fetch_cloud_eval() tags its results "Lichess cloud", any real UCI
    engine reports its own name instead."""
    source = "lichess_cloud" if live_result.engine_version == "Lichess cloud" else "live"
    return {
        "eval_cp": live_result.eval_cp,
        "eval_mate": live_result.eval_mate,
        "best_move_san": live_result.best_move_san,
        "pv_json": live_result.pv_json,
        "depth": live_result.depth,
        "source": source,
    }


def get_or_analyse_position(sqlite_conn, fen: str, analysis: dict | None,
                             session_key: str, on_fresh_result=None) -> dict | None:
    """Fills a DB-cache miss (analysis is None) by trying Lichess's cloud-eval
    database first, then falling back to a local engine spinner probe --
    consolidates the sequence previously duplicated across
    openings_view.py's "Most-repeated positions" and "Repertoire holes"
    panels.

    `analysis` is whatever the caller's own st.cache_data-wrapped
    data.get_position_analysis() lookup already returned (moves/
    position_cache tiers) -- passed straight through on a hit.

    session_key: a caller-chosen key (typically the FEN, or something that
    varies with it) used to memoize a fresh cloud/live result in
    st.session_state across reruns of the same position, the same
    convention openings_view.py's live_result__{fen} keys already used.

    on_fresh_result: called once, only when this invocation newly wrote a
    result (cloud or local) -- never on a rerun that finds the result
    already in st.session_state. Callers use this to invalidate their own
    page-level st.cache_data wrapper (e.g. cached_position_analysis.clear())
    so the position promotes to the fast DB-cache tier on the next lookup,
    exactly as the pre-refactor inline code did."""
    if analysis is not None:
        return analysis

    import data  # local import: avoids a module-level dashboard.data <-> live_engine dependency

    live_key = f"live_result__{session_key}"
    live_result = st.session_state.get(live_key)
    if live_result is not None:
        return _result_to_dict(live_result)

    cfg = config.load_config().get("interactive_engine", {})
    if cfg.get("use_lichess_cloud_eval", True):
        import lichess_cloud_eval  # local import: avoids a live_engine <-> lichess_cloud_eval cycle
        cloud_result = lichess_cloud_eval.fetch_cloud_eval(fen)
        if cloud_result is not None:
            st.session_state[live_key] = cloud_result
            data.store_position_analysis(sqlite_conn, fen, cloud_result)
            if on_fresh_result:
                on_fresh_result()
            return _result_to_dict(cloud_result)

    engine_svc = get_engine_service()
    if engine_svc is None:
        st.caption("Stockfish not found — configure the engine path in Settings.")
        return None
    if batch_running():
        st.caption("Batch analysis running — live engine paused until it finishes.")
        return None
    with st.spinner("Analysing position..."):
        live_result = engine_svc.analyse(fen)
    if live_result is None:
        return None
    st.session_state[live_key] = live_result
    data.store_position_analysis(sqlite_conn, fen, live_result)
    if on_fresh_result:
        on_fresh_result()
    return _result_to_dict(live_result)


def render_confirm_toggle(sqlite_conn, fen: str, key: str,
                           label: str = "Confirm with live engine") -> None:
    """Optional live-engine confirmation, off by default (analyse() has a
    real time cost) -- shared by SRS Drills and Opening Tree so both get
    the same session_state caching convention game_detail_view.py's
    "Analyse position" button already established."""
    import data  # local import: avoids a module-level dashboard.data <-> live_engine dependency

    engine_svc = get_engine_service()
    if engine_svc is None:
        return

    if not st.checkbox(label, key=key):
        return

    live_key = f"live_result__{fen}"
    live_result = st.session_state.get(live_key)
    if live_result is None:
        if batch_running():
            st.caption("Batch analysis running — live engine paused.")
            return
        with st.spinner("Analysing..."):
            live_result = engine_svc.analyse(fen)
        if live_result is None:
            st.caption("Engine analysis unavailable right now.")
            return
        st.session_state[live_key] = live_result
        data.store_position_analysis(sqlite_conn, fen, live_result)

    eval_label = chess_display.eval_str(live_result.eval_cp, live_result.eval_mate)
    pv = chess_display.pv_str(fen, live_result.pv_json)
    depth_str = f" (depth {live_result.depth})" if live_result.depth else ""
    st.caption("Engine: " + eval_label + (f" — {pv}" if pv else "") + depth_str)
```

- [ ] **Step 3: Create `tests/unit/test_engine_status.py` (content moved from `test_live_engine.py`)**

```python
import engine_status


class _FakeEngineService:
    def __init__(self, dead, version):
        self._dead = dead
        self._engine_version = version


def test_get_engine_status_summary_when_never_started(monkeypatch):
    monkeypatch.setattr(engine_status, "_service_started", False)

    def _fail_if_called():
        raise AssertionError("get_engine_service() must not be called when the engine was never started")

    monkeypatch.setattr(engine_status, "get_engine_service", _fail_if_called)
    result = engine_status.get_engine_status_summary()
    assert result == {"connected": False, "version": None}


def test_get_engine_status_summary_when_no_engine_detected(monkeypatch):
    monkeypatch.setattr(engine_status, "_service_started", True)
    monkeypatch.setattr(engine_status, "get_engine_service", lambda: None)
    result = engine_status.get_engine_status_summary()
    assert result == {"connected": False, "version": None}


def test_get_engine_status_summary_when_engine_connected(monkeypatch):
    fake = _FakeEngineService(dead=False, version="Stockfish 16")
    monkeypatch.setattr(engine_status, "_service_started", True)
    monkeypatch.setattr(engine_status, "get_engine_service", lambda: fake)
    result = engine_status.get_engine_status_summary()
    assert result == {"connected": True, "version": "Stockfish 16"}


def test_get_engine_status_summary_when_engine_dead(monkeypatch):
    fake = _FakeEngineService(dead=True, version="Stockfish 16")
    monkeypatch.setattr(engine_status, "_service_started", True)
    monkeypatch.setattr(engine_status, "get_engine_service", lambda: fake)
    result = engine_status.get_engine_status_summary()
    assert result == {"connected": False, "version": "Stockfish 16"}


def test_get_engine_service_caches_a_none_result(monkeypatch):
    """A legitimate None (Stockfish not found) must be cached too, not
    recomputed on every call -- the whole reason _UNSET (not None) is the
    sentinel."""
    engine_status.clear_engine_service_cache()
    call_count = {"n": 0}

    class _FakeConfig:
        def get(self, *_a, **_k):
            return {}

    def _fake_load_config():
        call_count["n"] += 1
        return _FakeConfig()

    monkeypatch.setattr(engine_status.config, "load_config", _fake_load_config)
    monkeypatch.setattr(engine_status.worker, "find_engine_path", lambda *_a, **_k: None)

    result1 = engine_status.get_engine_service()
    result2 = engine_status.get_engine_service()
    assert result1 is None
    assert result2 is None
    assert call_count["n"] == 1
    engine_status.clear_engine_service_cache()
```

- [ ] **Step 4: Rewrite `tests/unit/test_live_engine.py` as a regression test for the `.clear()` delegation**

```python
"""Regression test for dashboard/live_engine.py's get_engine_service --
the four behavioral tests for get_engine_status_summary moved to
tests/unit/test_engine_status.py when that logic moved to
dashboard/engine_status.py (2026-07-13). This file now only pins the one
thing that's specific to live_engine.py itself: that .clear() on its
thin wrapper actually clears engine_status.py's real cache, not a second,
independently-stale one -- the exact behavior dashboard/settings_view.py's
existing live_engine.get_engine_service.clear() call sites depend on.
"""
import engine_status
import live_engine


def test_get_engine_service_clear_delegates_to_engine_status(monkeypatch):
    calls = {"n": 0}

    def _fake_clear():
        calls["n"] += 1

    monkeypatch.setattr(engine_status, "clear_engine_service_cache", _fake_clear)
    live_engine.get_engine_service.clear()
    assert calls["n"] == 1


def test_get_engine_service_delegates_to_engine_status(monkeypatch):
    sentinel = object()
    monkeypatch.setattr(engine_status, "get_engine_service", lambda: sentinel)
    assert live_engine.get_engine_service() is sentinel
```

- [ ] **Step 5: Run the new/rewritten tests**

Run: `pytest tests/unit/test_engine_status.py tests/unit/test_live_engine.py -v`
Expected: all PASS.

- [ ] **Step 6: Confirm `dashboard/settings_view.py`'s existing `.clear()` call sites still work unchanged**

Run: `grep -n "live_engine.get_engine_service.clear()" dashboard/settings_view.py`
Expected: 6 matches, unchanged — this task deliberately makes no edits to `settings_view.py`.

- [ ] **Step 7: Run the full existing suite**

Run: `pytest -x -q`
Expected: same baseline as Task 1's Step 8.

- [ ] **Step 8: Commit**

```bash
git add dashboard/engine_status.py dashboard/live_engine.py \
        tests/unit/test_engine_status.py tests/unit/test_live_engine.py
git commit -m "Extract streamlit-free engine_status.py from dashboard/live_engine.py"
```

---

### Task 4: Point `api/db.py` at `connections.py`

**Files:**
- Modify: `api/db.py`
- Modify: `tests/integration/test_api_overview.py` (fixture + engine-status monkeypatch target)
- Modify: `tests/integration/test_api_nav.py` (fixture)

**Interfaces:**
- Consumes: `connections.open_connections`, `connections.clear_cache` (Task 1); `engine_status.get_engine_status_summary` (Task 3).
- Produces: `api.db.get_db_connections() -> (sqlite_conn, duck_conn)` — unchanged public signature, now streamlit-free internally.

- [ ] **Step 1: Rewrite `api/db.py`**

```python
"""Connection helper for the FastAPI service.

Reuses connections.py's open_connections() directly rather than
reimplementing it: the DuckDB per-PID-snapshot + locked-connection
machinery it wraps is a hard-won fix for a real corruption incident
(duckdb_sqlite_same_process_hazard project memory) -- reused here, not
duplicated. Unlike dashboard/_common.py's get_connections() (which this
module used to call through), connections.open_connections() has no
streamlit dependency at all -- see connections.py's own docstring and
docs/superpowers/specs/2026-07-13-react-frontend-packaging-design.md.
"""
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import connections


def get_db_connections():
    """Returns (sqlite_conn, duck_conn). Thin re-export of connections.py's
    open_connections() under an API-layer-scoped name."""
    return connections.open_connections()
```

- [ ] **Step 2: Update `tests/integration/test_api_overview.py`'s fixture and direct test**

Replace the module's `test_get_connections_works_outside_streamlit` test (lines ~24-47) with a version that goes through `connections` directly instead of `_common`:

```python
@pytest.mark.integration
def test_open_connections_works_outside_streamlit(migrated_db_path, monkeypatch, tmp_path):
    scratch_config = tmp_path / "config.yaml"
    shutil.copy(REPO_ROOT / "config.yaml", scratch_config)

    import config as _config
    monkeypatch.setattr(_config, "DEFAULT_CONFIG_PATH", scratch_config)
    _config.set_player_name("spike_test_player", path=str(scratch_config))
    _config.set_database_path(str(migrated_db_path), path=str(scratch_config))

    import connections
    connections.clear_cache()  # process-wide singleton; force a fresh read for this config.
    sqlite_conn, duck_conn = connections.open_connections()

    assert duck_conn.execute("SELECT COUNT(*) FROM db.games").fetchone()[0] == 0
    assert sqlite_conn.execute("SELECT COUNT(*) FROM games").fetchone()[0] == 0
```

Then update the `api_client` fixture: replace
```python
    import _common
    _common.get_connections.clear()
```
with
```python
    import connections
    connections.clear_cache()
```

Then update `test_engine_status_endpoint_reports_connected_engine` to monkeypatch `engine_status` instead of `live_engine`:
```python
@pytest.mark.integration
def test_engine_status_endpoint_reports_connected_engine(api_client, monkeypatch):
    import engine_status

    def fake_get_engine_status_summary():
        return {"connected": True, "version": "17.1"}

    monkeypatch.setattr(engine_status, "get_engine_status_summary", fake_get_engine_status_summary)

    resp = api_client.get("/api/overview/engine-status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["connected"] is True
    assert body["version"] == "17.1"
```

(This anticipates Task 5's change of `api/main.py`'s import from `live_engine` to `engine_status` — this test will fail until Task 5 lands; that's expected and fine within this same plan.)

- [ ] **Step 3: Update `tests/integration/test_api_nav.py`'s fixture**

Replace
```python
    import _common
    _common.get_connections.clear()
```
with
```python
    import connections
    connections.clear_cache()
```

- [ ] **Step 4: Run the API integration tests**

Run: `pytest tests/integration/test_api_overview.py tests/integration/test_api_nav.py -v`
Expected: `test_engine_status_endpoint_reports_connected_engine` FAILS at this point (still monkeypatching `engine_status` but `api/main.py` still imports `live_engine` — Task 5 fixes this). Every other test PASSES.

- [ ] **Step 5: Commit**

```bash
git add api/db.py tests/integration/test_api_overview.py tests/integration/test_api_nav.py
git commit -m "Point api/db.py at connections.py, retarget API test fixtures"
```

---

### Task 5: Update `api/main.py` — swap `live_engine`→`engine_status`, add asset-serving + SPA-fallback routes

**Files:**
- Modify: `api/main.py`
- Create: `tests/integration/test_api_static.py`

**Interfaces:**
- Consumes: `engine_status.get_engine_status_summary` (Task 3).
- Produces: `api.main.FRONTEND_DIST_DIR` (module-level `pathlib.Path` constant, monkeypatchable per-test) — the path later tasks (build script, packaging spec) must keep in sync with where `frontend/dist` actually lands, both in a source checkout and frozen.

- [ ] **Step 1: Update the import and the engine-status endpoint in `api/main.py`**

Change:
```python
import live_engine
```
to:
```python
import engine_status
```

Change:
```python
@app.get("/api/overview/engine-status")
def engine_status():
    status = live_engine.get_engine_status_summary()
    return {"connected": status["connected"], "version": status["version"], "app_version": _app_version}
```
to (renaming the local variable so it doesn't shadow the module name):
```python
@app.get("/api/overview/engine-status")
def engine_status_endpoint():
    status = engine_status.get_engine_status_summary()
    return {"connected": status["connected"], "version": status["version"], "app_version": _app_version}
```

- [ ] **Step 2: Add the frontend dist path constant and two new imports**

Near the top of `api/main.py`, after the existing imports, add:
```python
import pathlib

from fastapi import HTTPException
from fastapi.responses import FileResponse
```

After the `app = FastAPI(...)` / CORS middleware block, add:
```python
# Where the built React frontend lives -- frontend/dist relative to this
# file's own directory's parent, both in a source checkout (frontend/dist
# is produced by `npm run build` in frontend/) and frozen (chesswright-
# react.spec bundles it to the same relative location under _internal/,
# since api/main.py itself is bundled at _internal/api/main.py). A plain
# module-level constant (not resolved inside a function) so tests can
# monkeypatch it directly -- see test_api_static.py.
FRONTEND_DIST_DIR = pathlib.Path(__file__).resolve().parent.parent / "frontend" / "dist"
```

- [ ] **Step 3: Add the asset-serving and SPA-fallback routes at the very end of the file**

After every existing `@app.get("/api/...")` route (i.e. after the `nav_pages` route at the bottom of the current file), append:

```python
@app.get("/assets/{asset_path:path}")
def frontend_asset(asset_path: str):
    """Serves frontend/dist/assets/* -- the built React app's JS/CSS
    bundle (Vite emits root-absolute /assets/... references in
    index.html). Path-traversal-safe: resolves the joined path and
    verifies it's still inside assets_dir before serving, rather than
    trusting the path parameter directly."""
    assets_dir = (FRONTEND_DIST_DIR / "assets").resolve()
    candidate = (assets_dir / asset_path).resolve()
    try:
        candidate.relative_to(assets_dir)
    except ValueError:
        raise HTTPException(status_code=404)
    if not candidate.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(candidate)


@app.get("/{full_path:path}")
def spa_fallback(full_path: str):
    """Catch-all SPA-fallback for the built React app's client-side
    routing (react-router-dom) -- must be the LAST route registered in
    this file so it never shadows the /api/* routes above. Returns a
    plain 404 (not a crash) when the frontend hasn't been built yet --
    api/main.py must still work standalone against a bare `npm run dev`
    Vite server on 5173, where this route is never hit at all."""
    index_path = FRONTEND_DIST_DIR / "index.html"
    if not index_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="Frontend not built -- run `npm run build` in frontend/ first.",
        )
    return FileResponse(index_path)
```

- [ ] **Step 4: Write `tests/integration/test_api_static.py`**

```python
"""Integration tests for api/main.py's frontend asset-serving and
SPA-fallback routes (docs/superpowers/specs/2026-07-13-react-frontend-
packaging-design.md). Uses a temp frontend/dist directory monkeypatched
onto api.main.FRONTEND_DIST_DIR -- doesn't depend on a real `npm run
build` having run, so this test is robust in a fresh checkout/CI.
"""
import pathlib
import shutil
import sys

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
DASHBOARD_DIR = REPO_ROOT / "dashboard"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(DASHBOARD_DIR))


@pytest.fixture
def api_client(migrated_db_path, monkeypatch, tmp_path):
    scratch_config = tmp_path / "config.yaml"
    shutil.copy(REPO_ROOT / "config.yaml", scratch_config)

    import config as _config
    monkeypatch.setattr(_config, "DEFAULT_CONFIG_PATH", scratch_config)
    _config.set_player_name("spike_test_player", path=str(scratch_config))
    _config.set_database_path(str(migrated_db_path), path=str(scratch_config))

    import connections
    connections.clear_cache()

    import api.main as api_main
    api_main.reset_caches()
    return api_main, TestClient(api_main.app)


@pytest.fixture
def fake_dist_dir(tmp_path):
    dist_dir = tmp_path / "dist"
    assets_dir = dist_dir / "assets"
    assets_dir.mkdir(parents=True)
    (dist_dir / "index.html").write_text("<html><body><div id='root'></div></body></html>")
    (assets_dir / "index-abc123.js").write_text("console.log('fake bundle');")
    return dist_dir


@pytest.mark.integration
def test_asset_is_served(api_client, fake_dist_dir, monkeypatch):
    api_main, client = api_client
    monkeypatch.setattr(api_main, "FRONTEND_DIST_DIR", fake_dist_dir)

    resp = client.get("/assets/index-abc123.js")
    assert resp.status_code == 200
    assert "fake bundle" in resp.text


@pytest.mark.integration
def test_unknown_asset_is_404(api_client, fake_dist_dir, monkeypatch):
    api_main, client = api_client
    monkeypatch.setattr(api_main, "FRONTEND_DIST_DIR", fake_dist_dir)

    resp = client.get("/assets/does-not-exist.js")
    assert resp.status_code == 404


@pytest.mark.integration
def test_asset_path_traversal_is_blocked(api_client, fake_dist_dir, monkeypatch):
    api_main, client = api_client
    monkeypatch.setattr(api_main, "FRONTEND_DIST_DIR", fake_dist_dir)

    resp = client.get("/assets/..%2f..%2f..%2fetc%2fpasswd")
    assert resp.status_code in (404, 400)


@pytest.mark.integration
def test_spa_fallback_serves_index_html_for_client_routes(api_client, fake_dist_dir, monkeypatch):
    api_main, client = api_client
    monkeypatch.setattr(api_main, "FRONTEND_DIST_DIR", fake_dist_dir)

    resp = client.get("/patterns")
    assert resp.status_code == 200
    assert "<div id='root'>" in resp.text


@pytest.mark.integration
def test_api_routes_still_take_precedence_over_spa_fallback(api_client, fake_dist_dir, monkeypatch):
    api_main, client = api_client
    monkeypatch.setattr(api_main, "FRONTEND_DIST_DIR", fake_dist_dir)

    resp = client.get("/api/overview/headline-stats")
    assert resp.status_code == 200
    body = resp.json()
    assert "total_games" in body  # a real API JSON response, not index.html


@pytest.mark.integration
def test_spa_fallback_404s_cleanly_when_frontend_not_built(api_client, tmp_path, monkeypatch):
    api_main, client = api_client
    monkeypatch.setattr(api_main, "FRONTEND_DIST_DIR", tmp_path / "never_built")

    resp = client.get("/patterns")
    assert resp.status_code == 404
```

- [ ] **Step 5: Run the API tests, including the now-fixed engine-status test from Task 4**

Run: `pytest tests/integration/test_api_static.py tests/integration/test_api_overview.py tests/integration/test_api_nav.py -v`
Expected: all PASS, including `test_engine_status_endpoint_reports_connected_engine` (now passes since `api/main.py` imports `engine_status`).

- [ ] **Step 6: Confirm `import api.main` still has zero streamlit**

Run:
```bash
python3 -c "
import sys
sys.path.insert(0, '.')
sys.path.insert(0, 'dashboard')
import api.main
assert 'streamlit' not in sys.modules, 'streamlit was imported transitively by api.main'
print('OK: api.main imported with zero streamlit')
"
```
Expected: prints `OK: api.main imported with zero streamlit`.

- [ ] **Step 7: Run the full existing suite**

Run: `pytest -x -q`
Expected: same baseline as Task 1's Step 8.

- [ ] **Step 8: Commit**

```bash
git add api/main.py tests/integration/test_api_static.py
git commit -m "Serve the built React frontend from api/main.py, drop live_engine import"
```

---

### Task 6: Create `chesswright-react.spec`

**Files:**
- Create: `chesswright-react.spec`

**Interfaces:**
- Consumes: `frontend/dist` (produced by `npm run build`, Task 8's build script runs this), `react_desktop_app.py` (Task 7 — this spec's entry point).
- Produces: `dist/chesswright-react/chesswright-react[.exe]` when built.

- [ ] **Step 1: Create `chesswright-react.spec`, graduated from `api_spike.spec`**

```python
# Real (non-spike) PyInstaller spec for the pure React+FastAPI desktop
# build -- see docs/superpowers/specs/2026-07-13-react-frontend-
# packaging-design.md. Graduated from api_spike.spec, which proved
# FastAPI/uvicorn survive freezing alongside this project's backend
# modules. Kept as a THIRD, isolated spec alongside chesswright.spec/
# chesswright-pro.spec -- same precedent this repo already has for
# keeping specs from silently colliding (chesswright_pro_pyinstaller_
# spec_gotcha project memory). Zero risk to the existing production
# chesswright.spec/build.yml -- nothing about the Streamlit build
# changes.
import pathlib
from PyInstaller.utils.hooks import collect_all

ROOT = pathlib.Path(".").resolve()

# Every root-level module the API's import chain reaches, PLUS
# connections.py (new) and desktop_app.py (reused for its
# ensure_user_data/resource_dir/free_port/wait_for_server/
# check_cpu_compat/check_webview2 helpers -- see react_desktop_app.py).
# desktop_app.py's own `if __name__ == "__main__"` guard means importing
# it has no side effects.
BACKEND_MODULES = [
    "ingest.py", "worker.py", "annotate.py", "analytics.py", "db.py",
    "config.py", "chess_utils.py", "migrate.py", "sync.py", "opening_explorer.py",
    "db_import.py", "joblock.py", "motif.py", "opponent_analysis.py",
    "sync_chesscom.py", "chesscom_pgn.py", "backfill_batch_eval_cache.py",
    "achievements.py", "backfill_achievements.py", "backfill_legal_reply_count.py",
    "connections.py", "desktop_app.py",
]

datas = [(str(ROOT / name), ".") for name in BACKEND_MODULES]
datas += [(str(ROOT / "config.yaml"), ".")]
datas += [(str(ROOT / "migrations"), "migrations")]
# dashboard/*.py's transitive flat-module dependencies (chess_display.py,
# confidence.py, etc.) -- same reasoning as api_spike.spec: bundling the
# whole directory (a few MB) is simpler and more robust than whack-a-mole
# adding individual modules as ModuleNotFoundErrors surface.
datas += [(str(ROOT / "dashboard"), "dashboard")]
datas += [(str(ROOT / "api"), "api")]
# The built frontend -- produced by `npm run build` in frontend/ (see
# scripts/build_react_app.py, which runs that BEFORE this spec).
# api/main.py's FRONTEND_DIST_DIR resolves to this same relative location
# in both source and frozen mode (see that module's comment).
datas += [(str(ROOT / "frontend" / "dist"), "frontend/dist")]

hiddenimports = []
binaries = []
# NOTE: "streamlit" is deliberately ABSENT from this list, unlike
# api_spike.spec -- the connections.py/engine_status.py extraction
# (docs/superpowers/specs/2026-07-13-react-frontend-packaging-design.md)
# removed it from api/main.py's real import closure. Confirmed by
# Task 5's zero-streamlit check; this spec's own build (Task 9) confirms
# it again against the actual frozen bundle.
for pkg in ["fastapi", "uvicorn", "starlette", "duckdb", "pandas", "chess", "yaml",
            "numpy", "matplotlib", "anthropic", "requests", "plotly",
            "keyring", "jinja2", "rapidfuzz", "markdown", "pywebview"]:
    pkg_datas, pkg_binaries, pkg_hiddenimports = collect_all(pkg)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hiddenimports

a = Analysis(
    ["react_desktop_app.py"],
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
    name="chesswright-react",
    console=True,
)
coll = COLLECT(exe, a.binaries, a.datas, name="chesswright-react")
```

- [ ] **Step 2: Confirm the spec file has no syntax errors**

Run: `python3 -c "compile(open('chesswright-react.spec').read(), 'chesswright-react.spec', 'exec')"`
Expected: no output (successful compile). This does NOT run PyInstaller yet — Task 7 must exist first (the spec's `Analysis(["react_desktop_app.py"], ...)` entry point doesn't exist until then), so a real build is deferred to Task 9.

- [ ] **Step 3: Commit**

```bash
git add chesswright-react.spec
git commit -m "Add chesswright-react.spec (pure React+FastAPI packaging, no streamlit)"
```

---

### Task 7: Create `react_desktop_app.py` (pywebview launcher)

**Files:**
- Create: `react_desktop_app.py`
- Create: `tests/integration/test_react_desktop_app.py`

**Interfaces:**
- Consumes: `desktop_app.ensure_user_data`, `desktop_app.resource_dir`, `desktop_app.free_port`, `desktop_app.wait_for_server`, `desktop_app.check_cpu_compat`, `desktop_app.check_webview2`, `desktop_app.USER_DATA_DIR` (all existing, unchanged, reused via import).
- Produces: `react_desktop_app.launch_api_subprocess(port, config_path)`, `react_desktop_app.run_api_server_mode(port, config_path)`, `react_desktop_app.main()` — this is `chesswright-react.spec`'s entry point (Task 6).

- [ ] **Step 1: Create `react_desktop_app.py`**

```python
#!/usr/bin/env python3
"""
Packaged-app entry point for the pure React+FastAPI build (see
docs/superpowers/specs/2026-07-13-react-frontend-packaging-design.md).
Sibling to desktop_app.py (the Streamlit build's entry point) -- reuses
desktop_app.py's already-proven helpers (ensure_user_data, resource_dir,
free_port, wait_for_server, check_cpu_compat, check_webview2) directly
via import rather than duplicating them; desktop_app.py's own
`if __name__ == "__main__"` guard makes that safe (no side effects on
import).

Process model graduates api/spike_launcher.py's already-proven subprocess
pattern (proves clean start/fetch/shutdown, no orphaned processes) into a
real launcher that also opens a pywebview window, mirroring exactly how
desktop_app.py points pywebview at Streamlit's own local server --
different port/process underneath, same shape. The frozen-executable
re-invocation dispatch (`--api-server-mode` flag, not `-m uvicorn`) is
the same fork-bomb-safe fix desktop_app.py's own module docstring
documents and api/spike_launcher.py already validated -- reused verbatim.

Usage:
    python3 react_desktop_app.py             # GUI launcher mode (default)
    python3 react_desktop_app.py --api-server-mode --port N --config PATH
                                        # internal -- re-invoked by the
                                          launcher itself, not meant to
                                          be run directly
"""
import os
import subprocess
import sys
import urllib.request

import desktop_app


def launch_api_subprocess(port, config_path):
    """Re-invokes this same executable with --api-server-mode. sys.executable
    alone is correct in BOTH modes: a real Python interpreter in a source
    checkout (needs this script's own path passed too) or the bundled exe
    itself when frozen (which already knows its own entry point -- no
    extra script argument exists or is needed). Mirrors desktop_app.
    launch_server_subprocess() exactly."""
    if getattr(sys, "frozen", False):
        cmd = [sys.executable, "--api-server-mode", "--port", str(port), "--config", config_path]
    else:
        cmd = [sys.executable, __file__, "--api-server-mode", "--port", str(port), "--config", config_path]
    return subprocess.Popen(cmd, cwd=str(desktop_app.resource_dir()))


def run_api_server_mode(port, config_path):
    """Runs in a dedicated subprocess (see launch_api_subprocess) -- this
    is that subprocess's entire job, on ITS main thread, so uvicorn.run()'s
    internal SIGTERM-handler registration is safe here, same reasoning as
    desktop_app.py's run_server_mode()."""
    os.environ["CHESSWRIGHT_CONFIG_PATH"] = config_path
    sys.path.insert(0, str(desktop_app.resource_dir()))

    import uvicorn
    from api.main import app
    uvicorn.run(app, host="127.0.0.1", port=port)


def main():
    if "--api-server-mode" in sys.argv:
        port = int(sys.argv[sys.argv.index("--port") + 1])
        config_path = sys.argv[sys.argv.index("--config") + 1]
        run_api_server_mode(port, config_path)
        return

    desktop_app.check_cpu_compat()
    desktop_app.check_webview2()
    user_config = desktop_app.ensure_user_data()
    port = desktop_app.free_port()
    url = f"http://127.0.0.1:{port}"

    proc = launch_api_subprocess(port, str(user_config))
    try:
        if not desktop_app.wait_for_server(f"{url}/api/overview/headline-stats"):
            print("API server did not start in time.", file=sys.stderr)
            proc.terminate()
            sys.exit(1)

        import webview

        webview.create_window(
            "Chesswright", url, width=1280, height=860,
            background_color="#14181F",
            min_size=(1000, 650),
        )
        webview.start(
            private_mode=False,
            storage_path=str(desktop_app.USER_DATA_DIR / "webview_data"),
        )
    finally:
        # The window closing (webview.start() returning) is the signal to
        # shut the server down -- same reasoning as desktop_app.py's main().
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Write an integration test for the subprocess lifecycle (not the pywebview window itself)**

Create `tests/integration/test_react_desktop_app.py`:

```python
"""Integration test for react_desktop_app.py's subprocess lifecycle --
start, serve, clean shutdown, no orphaned process. Mirrors what
api/spike_launcher.py's own manual main() already proved by hand;
this pins it as an automated regression. Does NOT drive pywebview itself
(no automated test framework here does that for the Streamlit build
either -- window creation is verified live/manually, per this project's
existing convention).
"""
import pathlib
import shutil
import subprocess
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

import react_desktop_app


@pytest.mark.integration
def test_api_subprocess_starts_serves_and_shuts_down_cleanly(migrated_db_path, tmp_path):
    scratch_config = tmp_path / "config.yaml"
    shutil.copy(REPO_ROOT / "config.yaml", scratch_config)

    import config as _config
    _config.set_player_name("react_launcher_test_player", path=str(scratch_config))
    _config.set_database_path(str(migrated_db_path), path=str(scratch_config))

    port = react_desktop_app.desktop_app.free_port()
    proc = react_desktop_app.launch_api_subprocess(port, str(scratch_config))
    try:
        url = f"http://127.0.0.1:{port}"
        assert react_desktop_app.desktop_app.wait_for_server(f"{url}/api/overview/headline-stats"), \
            "API subprocess did not start in time"

        import urllib.request
        resp = urllib.request.urlopen(f"{url}/api/overview/headline-stats", timeout=5)
        assert resp.status == 200
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)

    assert proc.poll() is not None, "API subprocess did not exit cleanly"
```

- [ ] **Step 3: Run the new test**

Run: `pytest tests/integration/test_react_desktop_app.py -v -m integration`
Expected: PASS. (This spawns a real subprocess and hits a real port — if it hangs, check that `CHESSWRIGHT_CONFIG_PATH` is being read correctly by the subprocess; don't add a retry loop to mask a real startup failure.)

- [ ] **Step 4: Commit**

```bash
git add react_desktop_app.py tests/integration/test_react_desktop_app.py
git commit -m "Add react_desktop_app.py, the pure React+FastAPI pywebview launcher"
```

---

### Task 8: Create `scripts/build_react_app.py`

**Files:**
- Create: `scripts/build_react_app.py`

**Interfaces:**
- Consumes: `frontend/package.json`'s `build` script (existing, unchanged), `chesswright-react.spec` (Task 6), `build_assets/duckdb_extensions/sqlite_scanner.duckdb_extension` (existing prerequisite, produced by `scripts/fetch_duckdb_extensions.py`).
- Produces: `dist/chesswright-react/` (the frozen build directory).

- [ ] **Step 1: Create `scripts/build_react_app.py`**

```python
#!/usr/bin/env python3
"""Local build pipeline for the pure React+FastAPI packaged app (see
docs/superpowers/specs/2026-07-13-react-frontend-packaging-design.md).
Local-only for now -- NOT wired into .github/workflows/build.yml, since
this path is an internal/parallel proof (most nav destinations still
404), not a real release artifact yet.

Steps: build the frontend (npm run build), confirm the DuckDB sqlite
extension has already been fetched, run PyInstaller, then copy the
DuckDB extension into the frozen bundle OUTSIDE PyInstaller's own
Analysis/COLLECT TOC -- mirrors .github/workflows/build.yml's existing
"Bundle DuckDB sqlite extension (post-build, outside PyInstaller's TOC)"
step exactly, for the same reason documented there: routing a
.duckdb_extension file through datas triggers PyInstaller's binary
reclassification and a macOS codesign failure that has nothing to do
with the file being broken (see the duckdb_macos_codesign_saga project
memory).

Usage: python3 scripts/build_react_app.py
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT / "frontend"
DUCKDB_EXTENSION = ROOT / "build_assets" / "duckdb_extensions" / "sqlite_scanner.duckdb_extension"


def run(cmd, cwd=None):
    print(f"$ {' '.join(cmd)}" + (f"  (cwd={cwd})" if cwd else ""))
    subprocess.run(cmd, cwd=cwd, check=True)


def main():
    if not DUCKDB_EXTENSION.exists():
        print(
            f"error: {DUCKDB_EXTENSION} is missing.\n"
            "Run `python scripts/fetch_duckdb_extensions.py` once (while "
            "online) before building.",
            file=sys.stderr,
        )
        sys.exit(1)

    run(["npm", "ci"], cwd=str(FRONTEND_DIR))
    run(["npm", "run", "build"], cwd=str(FRONTEND_DIR))

    run(["pyinstaller", "chesswright-react.spec", "--noconfirm"], cwd=str(ROOT))

    bundled_ext_dir = ROOT / "dist" / "chesswright-react" / "_internal" / "duckdb_extensions"
    bundled_ext_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(DUCKDB_EXTENSION, bundled_ext_dir / DUCKDB_EXTENSION.name)
    print(f"Copied {DUCKDB_EXTENSION.name} into {bundled_ext_dir}")

    print("Build complete: dist/chesswright-react/chesswright-react")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Confirm the script has no syntax errors**

Run: `python3 -m py_compile scripts/build_react_app.py`
Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add scripts/build_react_app.py
git commit -m "Add scripts/build_react_app.py build pipeline"
```

---

### Task 9: End-to-end build and manual verification

**Files:** none (verification only — this task should not need to modify any file; if it finds a bug, fix it in the relevant task's file and note the fix when reporting this task's result).

**Interfaces:** none produced — this is the plan's final acceptance check against the spec's stated success criteria.

- [ ] **Step 1: Run the full existing suite one last time before building**

Run: `pytest -x -q`
Expected: same baseline as Task 1's Step 8 (no regressions accumulated across Tasks 1-8).

- [ ] **Step 2: Run the real build pipeline**

Run: `python3 scripts/build_react_app.py`
Expected: completes successfully, ending with `Build complete: dist/chesswright-react/chesswright-react`.

- [ ] **Step 3: Confirm zero streamlit in the frozen bundle**

Run: `find dist/chesswright-react/_internal -maxdepth 1 -iname "streamlit*"`
Expected: no output (empty). This is the design's core acceptance criterion — verify it against the real frozen bundle, not just against source-level import tracing.

- [ ] **Step 4: Confirm the DuckDB sqlite extension actually loads from the frozen bundle**

Run:
```bash
./dist/chesswright-react/chesswright-react --api-server-mode --port 18123 --config config.yaml &
sleep 3
curl -s http://127.0.0.1:18123/api/overview/headline-stats
kill %1
```
Expected: a real JSON response (not a connection error or a DuckDB extension-loading traceback in the killed process's stderr).

- [ ] **Step 5: Launch the real packaged app and manually verify the window**

Run: `./dist/chesswright-react/chesswright-react`
Expected (manual/live check, not automatable — same category as this project's existing pywebview verification convention): a native window opens (no browser chrome), the Overview page renders with real data from the configured `chess.db`, and closing the window leaves no orphaned `chesswright-react` process behind (check with `ps aux | grep chesswright-react` after closing).

- [ ] **Step 6: Report the outcome**

Summarize: full suite status, zero-streamlit confirmation, DuckDB extension load confirmation, and the manual window-launch result (working / what broke). If Step 5 surfaces a real bug, fix it in the relevant earlier task's file, re-run Steps 1-5, and note the fix explicitly rather than silently amending an earlier task's commit.
