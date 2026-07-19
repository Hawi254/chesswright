"""Integration tests for the Opening Tree Pro endpoints -- see
docs/superpowers/specs/2026-07-16-opening-tree-pro-design.md.
Mirrors test_api_openings.py's api_client fixture convention (scratch
config.yaml + connections.clear_cache()/api_main.reset_caches(), not an
env-var override -- api/db.py's get_db_connections() routes through
connections.open_connections() -> config.get_config(), there is no
CHESS_APP_DB_PATH hook anywhere in this codebase).
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

import chess
from chess_utils import signed_zobrist

INITIAL_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


def _insert_game(db_path, game_id, opening_family="Sicilian Defense",
                  player_color="white", outcome_for_player="win"):
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO games (id, white, black, opening_family, player_color, outcome_for_player) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [game_id, "W", "B", opening_family, player_color, outcome_for_player])
    conn.commit()
    conn.close()


def _insert_move(db_path, game_id, ply, san, is_player_move=1, fen_before=INITIAL_FEN):
    # zobrist_hash mirrors ingest.py:231 (computed on the board BEFORE the
    # move is pushed) -- get_opening_moves_from_fen's ply<=40 tier reads
    # opening_position_stats_cache, which is built with
    # `WHERE zobrist_hash IS NOT NULL`; without it the cache silently
    # excludes the row and every lookup returns empty.
    zobrist_hash = signed_zobrist(chess.Board(fen_before))
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO moves (game_id, ply, move_number, color, san, is_player_move, fen_before, zobrist_hash) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [game_id, ply, (ply + 1) // 2, "w" if ply % 2 == 1 else "b", san, is_player_move, fen_before, zobrist_hash])
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


class TestOpeningTreeGating:
    def test_moves_403_without_pro(self, api_client, monkeypatch):
        import pro_gate
        monkeypatch.setattr(pro_gate, "is_pro_active", lambda: False)
        r = api_client.get("/api/opening-tree/moves", params={"fen": INITIAL_FEN, "ply": 1, "color": "w"})
        assert r.status_code == 403

    def test_map_403_without_pro(self, api_client, monkeypatch):
        import pro_gate
        monkeypatch.setattr(pro_gate, "is_pro_active", lambda: False)
        r = api_client.get("/api/opening-tree/map", params={"color": "w"})
        assert r.status_code == 403


class TestOpeningTreeMoves:
    def test_returns_moves_when_pro_active(self, api_client, migrated_db_path, monkeypatch):
        import pro_gate
        monkeypatch.setattr(pro_gate, "is_pro_active", lambda: True)
        _insert_game(migrated_db_path, "g1")
        _insert_move(migrated_db_path, "g1", 1, "e4")
        import analytics
        cache_conn = sqlite3.connect(migrated_db_path)
        analytics.ensure_opening_position_stats(cache_conn)
        cache_conn.close()

        r = api_client.get("/api/opening-tree/moves", params={"fen": INITIAL_FEN, "ply": 1, "color": "w", "min_games": 1})

        assert r.status_code == 200
        body = r.json()
        assert body[0]["san"] == "e4"


class TestOpeningTreeJump:
    def test_jump_not_gated_returns_path(self, api_client, migrated_db_path, monkeypatch):
        import pro_gate
        monkeypatch.setattr(pro_gate, "is_pro_active", lambda: False)
        _insert_game(migrated_db_path, "g1", opening_family="Sicilian Defense", player_color="white")
        _insert_move(migrated_db_path, "g1", 1, "e4")
        _insert_move(migrated_db_path, "g1", 2, "c5")

        r = api_client.get("/api/opening-tree/jump", params={"opening_family": "Sicilian Defense", "color": "w"})

        assert r.status_code == 200
        assert r.json()["path"] == ["e4", "c5"]

    def test_jump_404_when_no_games(self, api_client):
        r = api_client.get("/api/opening-tree/jump", params={"opening_family": "Not Real", "color": "w"})
        assert r.status_code == 404


class TestOpeningTreeSrs:
    def test_add_srs_card_not_gated(self, api_client):
        r = api_client.post("/api/opening-tree/srs", json={
            "fen": INITIAL_FEN, "best_move_san": "e4", "context": "e4 e5",
        })
        assert r.status_code == 200
        assert r.json()["added"] == 1
