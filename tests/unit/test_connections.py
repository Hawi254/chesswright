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
