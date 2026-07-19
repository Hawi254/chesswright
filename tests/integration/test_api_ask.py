"""Integration tests for the Ask feature's streaming endpoint -- see
docs/superpowers/specs/2026-07-17-ask-page-design.md.
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
class TestAskStream:
    def test_returns_503_when_no_api_key(self, api_client, monkeypatch):
        import claude_narrative
        monkeypatch.setattr(claude_narrative, "api_key_available", lambda: False)

        resp = api_client.post("/api/ask/stream", json={"question": "When do I blunder most?"})

        assert resp.status_code == 503
        assert "API key" in resp.json()["detail"]

    def test_streams_deltas_then_a_done_event(self, api_client, monkeypatch):
        import claude_narrative
        monkeypatch.setattr(claude_narrative, "api_key_available", lambda: True)

        def fake_stream(question, data_brief):
            yield "You blunder "
            yield "most in the middlegame."
        monkeypatch.setattr(claude_narrative, "answer_question_stream", fake_stream)

        resp = api_client.post("/api/ask/stream", json={"question": "When do I blunder most?"})

        assert resp.status_code == 200
        body = resp.text
        assert 'data: {"delta": "You blunder "}' in body
        assert 'data: {"delta": "most in the middlegame."}' in body
        assert '"done": true' in body
        assert '"answer": "You blunder most in the middlegame."' in body

    def test_mid_stream_error_emits_terminal_error_event(self, api_client, monkeypatch):
        import claude_narrative
        monkeypatch.setattr(claude_narrative, "api_key_available", lambda: True)

        def fake_stream(question, data_brief):
            yield "Starting..."
            raise RuntimeError("rate limited")
        monkeypatch.setattr(claude_narrative, "answer_question_stream", fake_stream)

        resp = api_client.post("/api/ask/stream", json={"question": "When do I blunder most?"})

        assert resp.status_code == 200
        assert 'data: {"delta": "Starting..."}' in resp.text
        assert '"error": "rate limited"' in resp.text
