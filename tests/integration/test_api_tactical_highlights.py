"""Integration tests for the Tactical Highlights 'Highlight Reel' endpoint --
see docs/superpowers/specs/2026-07-15-tactical-highlights-reel-design.md.
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


def _insert_game(db_path, game_id, opponent_name="Foe", outcome_for_player="win",
                  utc_date="2026.01.01", player_color="white", num_plies=40):
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO games (id, white, black, opponent_name, outcome_for_player, "
        "utc_date, player_color, num_plies) VALUES (?, 'W', 'B', ?, ?, ?, ?, ?)",
        [game_id, opponent_name, outcome_for_player, utc_date, player_color, num_plies])
    conn.commit()
    conn.close()


def _insert_move(db_path, game_id, ply, san="Nf3", move_number=None, color="w",
                  from_square="g1", to_square="f3", fen_before="startpos",
                  is_player_move=1, **flags):
    move_number = move_number if move_number is not None else (ply + 1) // 2
    columns = ["game_id", "ply", "move_number", "color", "san", "from_square",
               "to_square", "fen_before", "is_player_move"]
    values = [game_id, ply, move_number, color, san, from_square, to_square,
              fen_before, is_player_move]
    for k, v in flags.items():
        columns.append(k)
        values.append(v)
    placeholders = ",".join("?" * len(values))
    conn = sqlite3.connect(db_path)
    conn.execute(
        f"INSERT INTO moves ({','.join(columns)}) VALUES ({placeholders})", values)
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
class TestTacticalHighlightsReel:
    def test_empty_db_returns_zero_counts_and_no_moments(self, api_client):
        resp = api_client.get("/api/tactical-highlights/reel")
        assert resp.status_code == 200
        body = resp.json()
        assert body["moments"] == []
        assert body["counts"] == {
            "brilliant": 0, "puzzle_conversion": 0, "best_move_streak": 0,
            "blown_mate": 0, "great_escape": 0,
        }

    def test_brilliant_magnitude_uses_opponent_recapture_not_own_material_delta(
            self, api_client, migrated_db_path):
        _insert_game(migrated_db_path, "g1")
        _insert_move(migrated_db_path, "g1", ply=10, san="Rxf7", move_number=5,
                     material_delta=0, is_brilliant_candidate=1)
        _insert_move(migrated_db_path, "g1", ply=11, san="Kxf7", color="b",
                     is_player_move=0, is_capture=1, to_square="f3",
                     material_delta=500)
        resp = api_client.get("/api/tactical-highlights/reel")
        assert resp.status_code == 200
        rows = [m for m in resp.json()["moments"] if m["category"] == "brilliant"]
        assert len(rows) == 1
        assert rows[0]["magnitude"] == 500.0
        assert rows[0]["magnitude_label"] == "Rook sacrifice"
        assert "a rook" in rows[0]["caption"]

    def test_puzzle_conversion_excludes_player_own_blunders(self, api_client, migrated_db_path):
        _insert_game(migrated_db_path, "g1")
        # Player's own trigger (is_player_move=1) must never appear as puzzle_conversion.
        _insert_move(migrated_db_path, "g1", ply=8, san="Qh5", move_number=4,
                     is_player_move=1, is_puzzle_trigger=1, puzzle_sequence_length=6)
        resp = api_client.get("/api/tactical-highlights/reel")
        assert resp.json()["counts"]["puzzle_conversion"] == 0

    def test_puzzle_conversion_includes_opponent_blunders(self, api_client, migrated_db_path):
        _insert_game(migrated_db_path, "g1", opponent_name="Rival")
        _insert_move(migrated_db_path, "g1", ply=9, san="Qh5??", move_number=5, color="b",
                     is_player_move=0, is_puzzle_trigger=1, puzzle_sequence_length=6)
        resp = api_client.get("/api/tactical-highlights/reel")
        rows = [m for m in resp.json()["moments"] if m["category"] == "puzzle_conversion"]
        assert len(rows) == 1
        assert rows[0]["magnitude"] == 6.0
        assert "Rival blundered on move 5" in rows[0]["caption"]

    def test_blown_mate_excludes_non_losses(self, api_client, migrated_db_path):
        _insert_game(migrated_db_path, "g1", outcome_for_player="win")
        _insert_move(migrated_db_path, "g1", ply=20, san="Kg1", move_number=10,
                     is_player_move=1, eval_mate=4, best_move_san="Qh7#")
        resp = api_client.get("/api/tactical-highlights/reel")
        assert resp.json()["counts"]["blown_mate"] == 0

    def test_blown_mate_includes_losses_with_missed_mate(self, api_client, migrated_db_path):
        _insert_game(migrated_db_path, "g1", outcome_for_player="loss")
        _insert_move(migrated_db_path, "g1", ply=20, san="Kg1", move_number=10,
                     is_player_move=1, eval_mate=4, best_move_san="Qh7#")
        resp = api_client.get("/api/tactical-highlights/reel")
        rows = [m for m in resp.json()["moments"] if m["category"] == "blown_mate"]
        assert len(rows) == 1
        assert rows[0]["magnitude"] == 4.0
        assert rows[0]["magnitude_label"] == "Mate in 4"

    def test_great_escape_excludes_losses(self, api_client, migrated_db_path):
        # A hallucination blunder followed by an immediate recapture, quick resignation.
        _insert_game(migrated_db_path, "g1", outcome_for_player="loss", num_plies=22)
        _insert_move(migrated_db_path, "g1", ply=20, san="Nb4??", move_number=10,
                     to_square="b4", is_player_move=1, classification="blunder", cpl=400)
        _insert_move(migrated_db_path, "g1", ply=21, san="Qxb4", color="b", is_player_move=0,
                     is_capture=1, to_square="b4", material_delta=300)
        resp = api_client.get("/api/tactical-highlights/reel")
        assert resp.json()["counts"]["great_escape"] == 0

    def test_great_escape_includes_survived_hallucinations(self, api_client, migrated_db_path):
        _insert_game(migrated_db_path, "g1", outcome_for_player="win", num_plies=60)
        _insert_move(migrated_db_path, "g1", ply=20, san="Nb4??", move_number=10,
                     to_square="b4", is_player_move=1, classification="blunder", cpl=400)
        _insert_move(migrated_db_path, "g1", ply=21, san="Qxb4", color="b", is_player_move=0,
                     is_capture=1, to_square="b4", material_delta=300)
        resp = api_client.get("/api/tactical-highlights/reel")
        rows = [m for m in resp.json()["moments"] if m["category"] == "great_escape"]
        assert len(rows) == 1
        assert rows[0]["magnitude"] == 40.0  # num_plies(60) - blunder_ply(20)
        assert rows[0]["fen"] is not None
        assert rows[0]["lastmove_from"] is not None and rows[0]["lastmove_to"] is not None

    def test_best_move_streak_orders_and_caps_at_top_15(self, api_client, migrated_db_path):
        _insert_game(migrated_db_path, "g1")
        for i in range(20):
            _insert_move(migrated_db_path, "g1", ply=2 * i + 1, san=f"m{i}", move_number=i + 1,
                         is_player_move=1, is_best_move_streak_trigger=1,
                         best_move_streak_length=i, best_move_streak_unforced_count=1)
        resp = api_client.get("/api/tactical-highlights/reel")
        rows = [m for m in resp.json()["moments"] if m["category"] == "best_move_streak"]
        assert len(rows) == 15
        assert [r["magnitude"] for r in rows] == sorted(
            [r["magnitude"] for r in rows], reverse=True)
        assert min(r["magnitude"] for r in rows) == 5.0  # top 15 of 0..19 -> 19..5

    def test_strength_clamps_at_one_for_out_of_range_magnitude(self, api_client, migrated_db_path):
        _insert_game(migrated_db_path, "g1", outcome_for_player="loss")
        # eval_mate=50 vastly exceeds the blown_mate strength cap of 10.
        _insert_move(migrated_db_path, "g1", ply=20, san="Kg1", move_number=10,
                     is_player_move=1, eval_mate=50, best_move_san="Qh7#")
        resp = api_client.get("/api/tactical-highlights/reel")
        rows = [m for m in resp.json()["moments"] if m["category"] == "blown_mate"]
        assert rows[0]["strength"] == 1.0

    def test_counts_match_moments_length_per_category(self, api_client, migrated_db_path):
        _insert_game(migrated_db_path, "g1", outcome_for_player="loss")
        _insert_move(migrated_db_path, "g1", ply=10, san="Rxf7", move_number=5,
                     material_delta=0, is_brilliant_candidate=1)
        _insert_move(migrated_db_path, "g1", ply=11, san="Kxf7", color="b",
                     is_player_move=0, is_capture=1, to_square="f3", material_delta=500)
        resp = api_client.get("/api/tactical-highlights/reel")
        body = resp.json()
        for category, count in body["counts"].items():
            assert count == len([m for m in body["moments"] if m["category"] == category])
