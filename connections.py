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
