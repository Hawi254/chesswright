"""
Tests for _common.py's DuckDB sqlite-extension loading -- the packaged
app must not need extensions.duckdb.org at runtime. A real Windows pilot
machine (firewalled) died at startup on `INSTALL sqlite`'s download
(2026-07-06, v0.1.19); packaged builds now bundle the extension file and
load it from disk. These tests pin that contract by simulating the
no-network machine: an unreachable extension repository plus an empty
extension directory (so no ~/.duckdb cache can quietly satisfy INSTALL).
"""
import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "dashboard"))

import duckdb

import _common
import connections

_FETCHED_EXT = (REPO_ROOT / "build_assets" / "duckdb_extensions"
                / "sqlite_scanner.duckdb_extension")


def _offline_conn(tmp_path):
    """A connection that cannot install extensions from the network OR
    find a previously cached install -- the pilot machine's state."""
    conn = duckdb.connect(config={"extension_directory": str(tmp_path / "ext")})
    conn.execute("SET custom_extension_repository = 'http://127.0.0.1:1'")
    return conn


@pytest.mark.skipif(
    not _FETCHED_EXT.exists(),
    reason="run scripts/fetch_duckdb_extensions.py once (online) first",
)
def test_bundled_extension_loads_with_no_network(tmp_path, monkeypatch):
    monkeypatch.setattr(connections, "_bundled_sqlite_extension_path",
                        lambda: _FETCHED_EXT)
    conn = _offline_conn(tmp_path)
    try:
        _common._load_duckdb_sqlite_extension(conn)
        loaded = conn.execute(
            "SELECT loaded FROM duckdb_extensions() "
            "WHERE extension_name = 'sqlite_scanner'"
        ).fetchone()[0]
        assert loaded
    finally:
        conn.close()


def test_no_bundle_no_network_raises_actionable_error(tmp_path, monkeypatch):
    monkeypatch.setattr(connections, "_bundled_sqlite_extension_path",
                        lambda: tmp_path / "nope.duckdb_extension")
    conn = _offline_conn(tmp_path)
    try:
        with pytest.raises(RuntimeError, match="fetch_duckdb_extensions"):
            _common._load_duckdb_sqlite_extension(conn)
    finally:
        conn.close()
