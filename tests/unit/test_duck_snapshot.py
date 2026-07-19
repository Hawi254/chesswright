"""
Tests for connections.py's DuckDB snapshot isolation -- DuckDB must never
attach the live database file. Two independent SQLite library copies
(python's sqlite3 + DuckDB's bundled one) in a single process can't see
each other's POSIX locks, which was reproduced 2026-07-04 corrupting the
real database and crashing with "disk I/O error"/SIGBUS -- see the
snapshot-isolation comment in dashboard/_common.py. These tests pin the
isolation contract: duck reads a private read-only copy, new live-file
data appears only via refresh_snapshot(), and dead processes' snapshots
get cleaned up.
"""
import os
import pathlib
import sqlite3
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "dashboard"))

import connections


@pytest.fixture
def live_db(tmp_path):
    p = tmp_path / "live.db"
    conn = sqlite3.connect(str(p))
    conn.execute("PRAGMA journal_mode = WAL")  # like every real chesswright db
    conn.execute("CREATE TABLE games (id TEXT PRIMARY KEY)")
    conn.execute("INSERT INTO games VALUES ('g1')")
    conn.commit()
    yield str(p), conn
    conn.close()


def test_duck_attaches_snapshot_not_live_file(live_db):
    db_path, _ = live_db
    duck = connections.get_duckdb_connection(db_path)
    try:
        attached = duck.execute(
            "SELECT path FROM duckdb_databases() WHERE database_name = 'db'"
        ).fetchone()[0]
        assert attached != db_path
        assert attached == str(connections._duck_snapshot_path(db_path))
        # No WAL machinery on the snapshot -- read-only attach must never
        # need to create/recover -wal/-shm files.
        snap_check = sqlite3.connect(attached)
        assert snap_check.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
        snap_check.close()
    finally:
        duck.close()


def test_live_writes_invisible_until_refresh(live_db):
    db_path, live = live_db
    duck = connections.get_duckdb_connection(db_path)
    try:
        assert duck.execute("SELECT COUNT(*) FROM db.games").fetchone()[0] == 1
        live.execute("INSERT INTO games VALUES ('g2')")
        live.commit()
        # Isolation: the live write must NOT be visible yet...
        assert duck.execute("SELECT COUNT(*) FROM db.games").fetchone()[0] == 1
        # ...and must appear after the explicit refresh point.
        duck.refresh_snapshot()
        assert duck.execute("SELECT COUNT(*) FROM db.games").fetchone()[0] == 2
    finally:
        duck.close()


def test_stale_snapshot_of_dead_process_removed(live_db):
    db_path, _ = live_db
    p = pathlib.Path(db_path)
    # A pid that can't be running: our own is alive, and pid_max caps real
    # ones well below 2**22 + our pid.
    dead = p.parent / f".{p.name}.duck-snapshot-{os.getpid() + 2**22}"
    dead.write_bytes(b"stale")
    ours = connections._duck_snapshot_path(db_path)
    duck = connections.get_duckdb_connection(db_path)
    try:
        assert not dead.exists()
        assert ours.exists()
    finally:
        duck.close()


def test_snapshot_is_attached_read_only(live_db):
    db_path, _ = live_db
    import duckdb
    duck = connections.get_duckdb_connection(db_path)
    try:
        with pytest.raises(duckdb.Error):
            duck.execute("INSERT INTO db.games VALUES ('nope')").fetchall()
    finally:
        duck.close()
