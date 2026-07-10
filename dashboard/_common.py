"""Shared helpers for the Phase 6 dashboard.

Mirrors analysis/_common.py's pattern (project-root sys.path insertion,
DuckDB-over-SQLite connection) but kept as its own module rather than
importing analysis/_common.py directly -- both directories are flat
(non-package) module collections, and adding both to sys.path at once
would risk an ambiguous `_common` import. Trivial duplication of the
connection helper, not of any query logic.
"""
import atexit
import os
import pathlib
import sqlite3
import sys
import threading
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import duckdb
import pandas as pd
import streamlit as st

import confidence
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
    get_connections() is @st.cache_resource -- one process-wide connection
    object, not one per session -- and DuckDB's Python connection isn't
    safe for concurrent multi-threaded query execution without external
    synchronization. Same fix shape as live_engine.py's EngineService,
    applied here to the DuckDB connection instead of the Stockfish
    subprocess.

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
    # In the frozen bundle, dashboard/ and duckdb_extensions/ are sibling
    # data directories under _internal/ (see chesswright.spec); in a
    # source checkout the same relative location is the repo root, where
    # the directory normally doesn't exist -- that's the INSTALL fallback.
    return pathlib.Path(__file__).resolve().parent.parent \
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


@st.cache_resource(show_spinner="Opening your game database…")
def get_connections():
    """One SQLite connection + one DuckDB connection for the whole server
    session (st.cache_resource, not cache_data -- these are live
    connections, not serializable results). Moved here from app.py in
    Phase 6c.3 (multi-page restructure) specifically so every page module
    (game_explorer_view.py, game_detail_view.py, app.py itself) shares the
    SAME cached singleton -- two separately-defined get_connections()
    functions in different modules would each get their OWN cache entry
    (Streamlit keys st.cache_resource by function identity), silently
    reopening the connection and re-triggering the ~94s structure_ctx
    rebuild cost this caching exists to avoid in the first place."""
    db_path = resolve_db_path()
    try:
        migrate.migrate(db_path)
    except Exception:
        import shutil
        try:
            db_dir = pathlib.Path(db_path).parent
            free_gb = shutil.disk_usage(db_dir).free / 1e9
            if free_gb < 0.5:
                st.error(
                    f"**Database error — disk is almost full** "
                    f"({free_gb:.1f} GB free on the volume holding your database). "
                    "Free up at least 1 GB and restart Chesswright.\n\n"
                    f"Database path: `{db_path}`"
                )
                st.stop()
        except Exception:
            pass
        raise
    return get_sqlite_connection(db_path), get_duckdb_connection(db_path)


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
# Promoted from insights_view.py (2026-07-10, Training Queue MVP) once a
# second page needed the exact same chip/action-button rendering for the
# same finding dicts -- same "promote to the one shared home, don't fork a
# second copy" convention as data/_shared.py's _classify_endgame_type
# promotion. Kept in _common.py rather than a new module: this file
# already plays the "cross-page view helper" role for finding-adjacent
# rendering (see game_labels/navigate_on_row_click above), so a second
# shared-helpers module would just split one convention into two homes.

# Severity tier -> sort rank. Insights sorts its full findings list by
# this; Training Queue sorts its weakness-only subset the same way.
SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}

# Severity tier -> (chip CSS class, label). Same pattern as
# confidence._TIER_CHIPS, kept here since it's a different axis
# (magnitude, not sample size).
_SEVERITY_CHIPS = {
    "high": ("chip-negative", "High impact"),
    "medium": ("chip-neutral", "Medium impact"),
    "low": ("chip-muted", "Low impact"),
}

# Category -> display label for the small category chip.
CATEGORY_LABELS = {
    "tactical": "Tactics",
    "time": "Time management",
    "defense": "King safety",
    "matchup": "Matchups",
    "giant_killer": "Giant-killing",
    "general": "General",
}

# Findings whose title maps to a Drill Export preset.
# Keys match finding["title"] exactly; values are passed as _drill_preset
# into session_state so drill_export_view can pre-select sources + motif filter.
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
            # Opponent Prep's fetch is lichess-only -- don't offer to
            # scout a chess.com username (see get_nemesis_opponents).
            and finding.get("opponent_on_lichess", True)):
        if st.button("→ Scout this opponent",
                     key="scout_nemesis",
                     help="Open Opponent Prep with this player's username pre-filled."):
            st.session_state["_prep_username"] = finding["opponent_name"]
            st.switch_page(prep_page)
