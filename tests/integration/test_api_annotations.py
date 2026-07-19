"""Integration tests for the annotation CRUD + AI-comment endpoints. See
docs/superpowers/specs/2026-07-14-game-detail-slice4-annotations-design.md.
"""
import pathlib
import shutil
import sqlite3
import sys

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
DASHBOARD_DIR = REPO_ROOT / "dashboard"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(DASHBOARD_DIR))

BRANCH_FEN = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"


def _insert_game(db_path, game_id):
    """game_annotations.game_id has a real FK to games(id) (unlike
    variations, which has no FK to games at all) and the app's connection
    runs with PRAGMA foreign_keys = ON, so any test that writes a game
    annotation needs a real games row first."""
    conn = sqlite3.connect(db_path)
    conn.execute("INSERT INTO games (id, white, black) VALUES (?, 'W', 'B')", [game_id])
    conn.commit()
    conn.close()


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


@pytest.fixture
def variation_id(api_client):
    resp = api_client.post(
        "/api/games/test_game_1/variations",
        json={"branch_ply": 2, "branch_fen": BRANCH_FEN, "moves": ["g8f6"]},
    )
    return resp.json()["id"]


@pytest.mark.integration
class TestVariationAnnotationEndpoints:
    def test_get_returns_null_when_unannotated(self, api_client, variation_id):
        resp = api_client.get(f"/api/variations/{variation_id}/annotations/1")
        assert resp.status_code == 200
        assert resp.json() is None

    def test_put_upserts_and_returns_updated_annotation(self, api_client, variation_id):
        resp = api_client.put(
            f"/api/variations/{variation_id}/annotations/1",
            json={"glyph": "!", "comment": "Good move"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["glyph"] == "!"
        assert body["comment"] == "Good move"
        assert body["variation_id"] == variation_id
        assert body["move_index"] == 1

    def test_get_after_put_returns_the_saved_annotation(self, api_client, variation_id):
        api_client.put(
            f"/api/variations/{variation_id}/annotations/1",
            json={"glyph": "??", "comment": None},
        )
        resp = api_client.get(f"/api/variations/{variation_id}/annotations/1")
        assert resp.status_code == 200
        assert resp.json()["glyph"] == "??"

    def test_ai_comment_success(self, api_client, variation_id, monkeypatch):
        import claude_narrative
        monkeypatch.setattr(claude_narrative, "annotate_position",
                            lambda **kwargs: "A sharp tactical shot.")
        resp = api_client.post(
            f"/api/variations/{variation_id}/annotations/1/ai-comment",
            json={"fen": BRANCH_FEN, "eval_cp": 120, "best_move_san": "Nf6", "user_comment": None},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ai_comment"] == "A sharp tactical shot."
        assert body["ai_model"] == claude_narrative.MODEL
        assert body["generated_at"] is not None

    def test_ai_comment_missing_api_key_returns_503(self, api_client, variation_id, monkeypatch):
        import claude_narrative

        def _raise(**kwargs):
            raise claude_narrative.MissingApiKeyError("No Anthropic API key configured.")
        monkeypatch.setattr(claude_narrative, "annotate_position", _raise)

        resp = api_client.post(
            f"/api/variations/{variation_id}/annotations/1/ai-comment",
            json={"fen": BRANCH_FEN, "eval_cp": None, "best_move_san": None, "user_comment": None},
        )
        assert resp.status_code == 503
        assert "API key" in resp.json()["detail"]

    def test_ai_comment_generic_exception_returns_502(self, api_client, variation_id, monkeypatch):
        import claude_narrative

        def _raise(**kwargs):
            raise RuntimeError("connection reset")
        monkeypatch.setattr(claude_narrative, "annotate_position", _raise)

        resp = api_client.post(
            f"/api/variations/{variation_id}/annotations/1/ai-comment",
            json={"fen": BRANCH_FEN, "eval_cp": None, "best_move_san": None, "user_comment": None},
        )
        assert resp.status_code == 502
        assert "connection reset" in resp.json()["detail"]


@pytest.mark.integration
class TestGameAnnotationEndpoints:
    def test_get_returns_null_when_unannotated(self, api_client):
        resp = api_client.get("/api/games/test_game_2/annotations/4")
        assert resp.status_code == 200
        assert resp.json() is None

    def test_put_upserts_and_returns_updated_annotation(self, api_client, migrated_db_path):
        _insert_game(migrated_db_path, "test_game_2")
        resp = api_client.put(
            "/api/games/test_game_2/annotations/4",
            json={"glyph": "!!", "comment": "Brilliant"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["glyph"] == "!!"
        assert body["comment"] == "Brilliant"
        assert body["game_id"] == "test_game_2"
        assert body["move_index"] == 4

    def test_get_after_put_returns_the_saved_annotation(self, api_client, migrated_db_path):
        _insert_game(migrated_db_path, "test_game_2")
        api_client.put("/api/games/test_game_2/annotations/4", json={"glyph": "?!", "comment": None})
        resp = api_client.get("/api/games/test_game_2/annotations/4")
        assert resp.status_code == 200
        assert resp.json()["glyph"] == "?!"

    def test_annotations_are_scoped_to_game_id(self, api_client, migrated_db_path):
        _insert_game(migrated_db_path, "test_game_2")
        api_client.put("/api/games/test_game_2/annotations/4", json={"glyph": "!", "comment": None})
        resp = api_client.get("/api/games/other_game/annotations/4")
        assert resp.status_code == 200
        assert resp.json() is None

    def test_ai_comment_success(self, api_client, migrated_db_path, monkeypatch):
        _insert_game(migrated_db_path, "test_game_2")
        import claude_narrative
        monkeypatch.setattr(claude_narrative, "annotate_position",
                            lambda **kwargs: "A quiet positional move.")
        resp = api_client.post(
            "/api/games/test_game_2/annotations/4/ai-comment",
            json={"fen": BRANCH_FEN, "eval_cp": -30, "best_move_san": "Bg5", "user_comment": "hmm"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ai_comment"] == "A quiet positional move."
        assert body["ai_model"] == claude_narrative.MODEL

    def test_ai_comment_missing_api_key_returns_503(self, api_client, monkeypatch):
        import claude_narrative

        def _raise(**kwargs):
            raise claude_narrative.MissingApiKeyError("No Anthropic API key configured.")
        monkeypatch.setattr(claude_narrative, "annotate_position", _raise)

        resp = api_client.post(
            "/api/games/test_game_2/annotations/4/ai-comment",
            json={"fen": BRANCH_FEN, "eval_cp": None, "best_move_san": None, "user_comment": None},
        )
        assert resp.status_code == 503

    def test_ai_comment_generic_exception_returns_502(self, api_client, monkeypatch):
        import claude_narrative

        def _raise(**kwargs):
            raise RuntimeError("timeout")
        monkeypatch.setattr(claude_narrative, "annotate_position", _raise)

        resp = api_client.post(
            "/api/games/test_game_2/annotations/4/ai-comment",
            json={"fen": BRANCH_FEN, "eval_cp": None, "best_move_san": None, "user_comment": None},
        )
        assert resp.status_code == 502


@pytest.mark.integration
class TestClaudeKeyStatus:
    def test_reports_true_when_key_available(self, api_client, monkeypatch):
        import claude_narrative
        monkeypatch.setattr(claude_narrative, "api_key_available", lambda: True)
        resp = api_client.get("/api/settings/claude-key-status")
        assert resp.status_code == 200
        assert resp.json() == {"available": True}

    def test_reports_false_when_key_unavailable(self, api_client, monkeypatch):
        import claude_narrative
        monkeypatch.setattr(claude_narrative, "api_key_available", lambda: False)
        resp = api_client.get("/api/settings/claude-key-status")
        assert resp.status_code == 200
        assert resp.json() == {"available": False}
