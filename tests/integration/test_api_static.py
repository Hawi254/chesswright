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


@pytest.mark.integration
def test_spa_fallback_404s_undefined_api_paths_instead_of_serving_html(api_client, fake_dist_dir, monkeypatch):
    """A typo'd or not-yet-implemented /api/* path must not fall through
    to the SPA catch-all and come back 200 with index.html's HTML --
    found live 2026-07-13 against the real frozen build: a frontend
    fetch()-and-parse-as-JSON caller would see a confusing JSON-parse
    error instead of an obvious 404."""
    api_main, client = api_client
    monkeypatch.setattr(api_main, "FRONTEND_DIST_DIR", fake_dist_dir)

    resp = client.get("/api/does-not-exist")
    assert resp.status_code == 404
    assert "<div id='root'>" not in resp.text
