"""Integration tests for the Board Chat endpoints -- list/resume/turn/feedback.
See docs/superpowers/specs/2026-07-14-game-detail-slice6-board-chat-design.md.
"""
import pathlib
import sqlite3
import shutil
import sys

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
DASHBOARD_DIR = REPO_ROOT / "dashboard"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(DASHBOARD_DIR))


def _insert_game(db_path, game_id, opponent_name="kingslayer99", utc_date="2026-07-14"):
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO games (id, white, black, opponent_name, utc_date) VALUES (?, 'W', 'B', ?, ?)",
        [game_id, opponent_name, utc_date])
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


@pytest.mark.integration
class TestListBoardChatConversations:
    def test_empty_when_no_conversations(self, api_client, migrated_db_path):
        _insert_game(migrated_db_path, "game_1")
        resp = api_client.get("/api/games/game_1/board-chat/conversations")
        assert resp.status_code == 200
        assert resp.json() == {"conversations": []}

    def test_populated_list(self, api_client, migrated_db_path):
        _insert_game(migrated_db_path, "game_1")
        from data import board_chat as data_board_chat
        from api.db import get_db_connections
        sqlite_conn, _ = get_db_connections()
        cid = data_board_chat.start_conversation(sqlite_conn, "game_1")
        data_board_chat.add_turn(sqlite_conn, cid, "user", "hi")

        resp = api_client.get("/api/games/game_1/board-chat/conversations")
        assert resp.status_code == 200
        body = resp.json()["conversations"]
        assert len(body) == 1
        assert body[0]["id"] == cid
        assert body[0]["turn_count"] == 1


@pytest.mark.integration
class TestResumeBoardChatConversation:
    def test_returns_display_history_arrows_and_highlights(self, api_client, migrated_db_path):
        _insert_game(migrated_db_path, "game_1")
        from data import board_chat as data_board_chat
        from api.db import get_db_connections
        sqlite_conn, _ = get_db_connections()
        cid = data_board_chat.start_conversation(sqlite_conn, "game_1")
        data_board_chat.add_turn(sqlite_conn, cid, "user", "best move?")
        import json as _json
        directives = _json.dumps([
            {"tool": "show_arrow", "from_square": "g1", "to_square": "f3", "style": "player_move"},
        ])
        data_board_chat.add_turn(sqlite_conn, cid, "assistant", "Nf3.", directives)

        resp = api_client.get(
            f"/api/games/game_1/board-chat/conversations/{cid}",
            params={"current_fen": "some-fen"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert [e["role"] for e in body["display_history"]] == ["user", "assistant"]
        assert body["arrows"] and body["arrows"][0]["from"] == "g1"
        assert body["directive_fen"] == "some-fen"

    def test_501_when_chesswright_pro_not_importable(self, api_client, migrated_db_path, monkeypatch):
        _insert_game(migrated_db_path, "game_1")
        from data import board_chat as data_board_chat
        from api.db import get_db_connections
        sqlite_conn, _ = get_db_connections()
        cid = data_board_chat.start_conversation(sqlite_conn, "game_1")

        monkeypatch.setitem(sys.modules, "chesswright_pro", None)
        resp = api_client.get(
            f"/api/games/game_1/board-chat/conversations/{cid}",
            params={"current_fen": "some-fen"},
        )
        assert resp.status_code == 501


@pytest.mark.integration
class TestPostBoardChatTurn:
    def test_happy_path_starts_a_new_conversation(self, api_client, migrated_db_path, monkeypatch):
        _insert_game(migrated_db_path, "game_1")
        import pro_gate
        monkeypatch.setattr(pro_gate, "is_pro_active", lambda: True)
        from chesswright_pro import board_chat

        def _fake_run_chat_turn(duck_conn, sqlite_conn, game_id, conversation_id, question, current_fen):
            return {"turn_id": 99, "answer_text": "Play e4.",
                    "arrows": [{"from": "e2", "to": "e4", "color": "#6FA98C"}], "highlights": []}
        monkeypatch.setattr(board_chat, "run_chat_turn", _fake_run_chat_turn)

        resp = api_client.post("/api/games/game_1/board-chat/turns", json={
            "conversation_id": None, "question": "what now?", "current_fen": "some-fen",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["turn_id"] == 99
        assert body["answer_text"] == "Play e4."
        assert isinstance(body["conversation_id"], int)

    def test_403_when_not_licensed(self, api_client, monkeypatch):
        import pro_gate
        monkeypatch.setattr(pro_gate, "is_pro_active", lambda: False)
        resp = api_client.post("/api/games/game_1/board-chat/turns", json={
            "question": "hi?", "current_fen": "some-fen",
        })
        assert resp.status_code == 403

    def test_501_when_chesswright_pro_not_importable(self, api_client, monkeypatch):
        import pro_gate
        monkeypatch.setattr(pro_gate, "is_pro_active", lambda: True)
        monkeypatch.setitem(sys.modules, "chesswright_pro", None)
        resp = api_client.post("/api/games/game_1/board-chat/turns", json={
            "question": "hi?", "current_fen": "some-fen",
        })
        assert resp.status_code == 501

    def test_503_on_missing_api_key(self, api_client, migrated_db_path, monkeypatch):
        _insert_game(migrated_db_path, "game_1")
        import pro_gate
        monkeypatch.setattr(pro_gate, "is_pro_active", lambda: True)
        import claude_narrative
        from chesswright_pro import board_chat

        def _raise(*args, **kwargs):
            raise claude_narrative.MissingApiKeyError("No Anthropic API key configured.")
        monkeypatch.setattr(board_chat, "run_chat_turn", _raise)

        resp = api_client.post("/api/games/game_1/board-chat/turns", json={
            "question": "hi?", "current_fen": "some-fen",
        })
        assert resp.status_code == 503
        assert "API key" in resp.json()["detail"]

    def test_502_on_generic_claude_failure(self, api_client, migrated_db_path, monkeypatch):
        _insert_game(migrated_db_path, "game_1")
        import pro_gate
        monkeypatch.setattr(pro_gate, "is_pro_active", lambda: True)
        from chesswright_pro import board_chat

        def _raise(*args, **kwargs):
            raise RuntimeError("connection reset")
        monkeypatch.setattr(board_chat, "run_chat_turn", _raise)

        resp = api_client.post("/api/games/game_1/board-chat/turns", json={
            "question": "hi?", "current_fen": "some-fen",
        })
        assert resp.status_code == 502
        assert "connection reset" in resp.json()["detail"]


@pytest.mark.integration
class TestPostBoardChatFeedback:
    def test_thumbs_up(self, api_client, migrated_db_path):
        _insert_game(migrated_db_path, "game_1")
        from data import board_chat as data_board_chat
        from api.db import get_db_connections
        sqlite_conn, _ = get_db_connections()
        cid = data_board_chat.start_conversation(sqlite_conn, "game_1")
        data_board_chat.add_turn(sqlite_conn, cid, "user", "hi")
        turn_id = data_board_chat.add_turn(sqlite_conn, cid, "assistant", "Nf3.")

        resp = api_client.post(f"/api/board-chat/turns/{turn_id}/feedback", json={"feedback": 1})
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

    def test_thumbs_down_with_question_summary_also_writes_a_capability_gap(self, api_client, migrated_db_path):
        _insert_game(migrated_db_path, "game_1")
        from data import board_chat as data_board_chat
        from api.db import get_db_connections
        sqlite_conn, _ = get_db_connections()
        cid = data_board_chat.start_conversation(sqlite_conn, "game_1")
        data_board_chat.add_turn(sqlite_conn, cid, "user", "best move?")
        turn_id = data_board_chat.add_turn(sqlite_conn, cid, "assistant", "Nf3.")

        resp = api_client.post(f"/api/board-chat/turns/{turn_id}/feedback", json={
            "feedback": -1, "question_summary": "best move?",
        })
        assert resp.status_code == 200

        gaps = data_board_chat.get_capability_gaps(sqlite_conn)
        assert len(gaps) == 1
        assert gaps[0]["turn_id"] == turn_id
        assert gaps[0]["question_summary"] == "best move?"
        assert gaps[0]["missing_data_description"] == "player marked this answer unhelpful"

    def test_404_for_unknown_turn_id(self, api_client):
        resp = api_client.post("/api/board-chat/turns/999999/feedback", json={"feedback": 1})
        assert resp.status_code == 404

    def test_400_for_feedback_on_a_non_assistant_turn(self, api_client, migrated_db_path):
        _insert_game(migrated_db_path, "game_1")
        from data import board_chat as data_board_chat
        from api.db import get_db_connections
        sqlite_conn, _ = get_db_connections()
        cid = data_board_chat.start_conversation(sqlite_conn, "game_1")
        user_turn_id = data_board_chat.add_turn(sqlite_conn, cid, "user", "hi")

        resp = api_client.post(f"/api/board-chat/turns/{user_turn_id}/feedback", json={"feedback": 1})
        assert resp.status_code == 400

    def test_400_for_invalid_feedback_value(self, api_client, migrated_db_path):
        _insert_game(migrated_db_path, "game_1")
        from data import board_chat as data_board_chat
        from api.db import get_db_connections
        sqlite_conn, _ = get_db_connections()
        cid = data_board_chat.start_conversation(sqlite_conn, "game_1")
        data_board_chat.add_turn(sqlite_conn, cid, "user", "hi")
        turn_id = data_board_chat.add_turn(sqlite_conn, cid, "assistant", "Nf3.")

        resp = api_client.post(f"/api/board-chat/turns/{turn_id}/feedback", json={"feedback": 5})
        assert resp.status_code == 400
