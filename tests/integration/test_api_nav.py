"""Integration test for the app-shell slice's nav/palette data endpoint.

Mirrors test_api_overview.py's api_client fixture pattern -- see that
file's module docstring for why get_connections() being safe outside
Streamlit matters here too (api.main imports `data`, which pulls in the
same _common connection machinery even though this specific endpoint
never touches a DB connection itself).
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
    # monkeypatch.setattr (not importlib.reload while CHESSWRIGHT_CONFIG_PATH
    # is monkeypatched) -- reload re-evaluates DEFAULT_CONFIG_PATH from the
    # env var but is never reloaded back, leaking this scratch path into
    # every later test in the same pytest process (see
    # test_api_overview.py's test_config_default_path_restored_after_api_client_tests
    # regression test). monkeypatch.setattr reverts automatically at teardown.
    monkeypatch.setattr(_config, "DEFAULT_CONFIG_PATH", scratch_config)
    _config.set_player_name("spike_test_player", path=str(scratch_config))
    _config.set_database_path(str(migrated_db_path), path=str(scratch_config))

    import _common
    _common.get_connections.clear()

    import api.main as api_main
    return TestClient(api_main.app)


@pytest.mark.integration
def test_nav_pages_endpoint(api_client):
    resp = api_client.get("/api/nav/pages")
    assert resp.status_code == 200
    body = resp.json()

    assert len(body) == 25  # 19 pages + 6 settings

    assert all(set(item.keys()) >= {"category", "title", "url_path"} for item in body)

    page_url_paths = {item["url_path"] for item in body if item["category"] == "page"}
    assert page_url_paths == {
        "overview", "patterns", "openings", "matchups", "game-endings",
        "tactical-highlights", "insights", "points", "evolution",
        "game-explorer", "drill-export", "training-queue", "srs-drills",
        "opening-tree", "opponent-prep", "ask", "settings",
        "analysis-jobs", "batch-impact",
    }

    setting_titles = {item["title"] for item in body if item["category"] == "setting"}
    assert setting_titles == {
        "Anthropic API key", "Live engine settings", "Import an existing database",
        "Chess.com account", "Chesswright Pro", "Support this project",
    }
