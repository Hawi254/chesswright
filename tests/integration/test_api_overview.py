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
