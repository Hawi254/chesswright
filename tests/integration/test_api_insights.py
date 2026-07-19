"""Integration tests for the Insights synthesis/coaching narrative
endpoints -- see
docs/superpowers/specs/2026-07-14-insights-page-redesign-phase1-design.md.
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
    return TestClient(api_main.app)


@pytest.mark.integration
class TestInsightsSynthesis:
    def test_returns_null_when_uncached(self, api_client):
        resp = api_client.get("/api/insights/synthesis")
        assert resp.status_code == 200
        assert resp.json() == {"narrative": None, "generated_at": None}

    def test_returns_cached_narrative(self, api_client):
        import data
        from api.db import get_db_connections
        sqlite_conn, _ = get_db_connections()
        data.save_narrative(sqlite_conn, "findings", "summary", "## Synthesis", "claude-sonnet-4-6")

        resp = api_client.get("/api/insights/synthesis")
        assert resp.status_code == 200
        body = resp.json()
        assert body["narrative"] == "## Synthesis"
        assert body["generated_at"] is not None


@pytest.mark.integration
class TestGenerateInsightsSynthesis:
    def test_generate_happy_path(self, api_client, monkeypatch):
        import claude_narrative
        monkeypatch.setattr(claude_narrative, "generate_insights_synthesis",
                             lambda *a, **k: "Generated synthesis")

        resp = api_client.post("/api/insights/synthesis/generate")
        assert resp.status_code == 200
        assert resp.json() == {"narrative": "Generated synthesis"}

        resp2 = api_client.get("/api/insights/synthesis")
        assert resp2.json()["narrative"] == "Generated synthesis"

    def test_returns_503_on_missing_api_key(self, api_client, monkeypatch):
        import claude_narrative

        def _raise(*args, **kwargs):
            raise claude_narrative.MissingApiKeyError("No Anthropic API key configured.")
        monkeypatch.setattr(claude_narrative, "generate_insights_synthesis", _raise)

        resp = api_client.post("/api/insights/synthesis/generate")
        assert resp.status_code == 503
        assert "API key" in resp.json()["detail"]

    def test_returns_502_on_generic_claude_failure(self, api_client, monkeypatch):
        import claude_narrative

        def _raise(*args, **kwargs):
            raise RuntimeError("connection reset")
        monkeypatch.setattr(claude_narrative, "generate_insights_synthesis", _raise)

        resp = api_client.post("/api/insights/synthesis/generate")
        assert resp.status_code == 502
        assert "connection reset" in resp.json()["detail"]


@pytest.mark.integration
class TestInsightsCoaching:
    def test_returns_null_when_uncached(self, api_client):
        resp = api_client.get("/api/insights/coaching")
        assert resp.status_code == 200
        assert resp.json() == {"narrative": None, "generated_at": None}

    def test_returns_cached_narrative(self, api_client):
        import data
        from api.db import get_db_connections
        sqlite_conn, _ = get_db_connections()
        data.save_narrative(sqlite_conn, "coaching", "recommendations", "## Coaching", "claude-sonnet-4-6")

        resp = api_client.get("/api/insights/coaching")
        assert resp.status_code == 200
        body = resp.json()
        assert body["narrative"] == "## Coaching"
        assert body["generated_at"] is not None


@pytest.mark.integration
class TestGenerateInsightsCoaching:
    def test_generate_happy_path(self, api_client, monkeypatch):
        import claude_narrative
        monkeypatch.setattr(claude_narrative, "generate_coaching_recommendations",
                             lambda *a, **k: "Generated coaching")

        resp = api_client.post("/api/insights/coaching/generate")
        assert resp.status_code == 200
        assert resp.json() == {"narrative": "Generated coaching"}

        resp2 = api_client.get("/api/insights/coaching")
        assert resp2.json()["narrative"] == "Generated coaching"

    def test_returns_503_on_missing_api_key(self, api_client, monkeypatch):
        import claude_narrative

        def _raise(*args, **kwargs):
            raise claude_narrative.MissingApiKeyError("No Anthropic API key configured.")
        monkeypatch.setattr(claude_narrative, "generate_coaching_recommendations", _raise)

        resp = api_client.post("/api/insights/coaching/generate")
        assert resp.status_code == 503
        assert "API key" in resp.json()["detail"]

    def test_returns_502_on_generic_claude_failure(self, api_client, monkeypatch):
        import claude_narrative

        def _raise(*args, **kwargs):
            raise RuntimeError("connection reset")
        monkeypatch.setattr(claude_narrative, "generate_coaching_recommendations", _raise)

        resp = api_client.post("/api/insights/coaching/generate")
        assert resp.status_code == 502
        assert "connection reset" in resp.json()["detail"]
