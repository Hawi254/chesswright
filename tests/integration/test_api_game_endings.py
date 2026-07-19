"""Integration tests for the Game Endings ("Ending Tree") endpoints --
see docs/superpowers/specs/2026-07-15-game-endings-page-design.md.
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


def _insert_game(db_path, game_id, outcome_for_player, game_end_type,
                  time_control_category=None, utc_date="2026.01.01", utc_time="10:00:00",
                  player_color="white", year=2026, month=1):
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO games (id, white, black, outcome_for_player, game_end_type, "
        "time_control_category, utc_date, utc_time, player_color, year, month) "
        "VALUES (?, 'W', 'B', ?, ?, ?, ?, ?, ?, ?, ?)",
        [game_id, outcome_for_player, game_end_type, time_control_category,
         utc_date, utc_time, player_color, year, month])
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
class TestEndingTree:
    def test_empty_db_returns_root_only(self, api_client):
        resp = api_client.get("/api/game-endings/tree")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ids"] == ["root"]
        assert body["labels"] == ["All games"]
        assert body["parents"] == [""]
        assert body["values"] == [0]

    def test_win_draw_loss_and_endtype_levels(self, api_client, migrated_db_path):
        _insert_game(migrated_db_path, "g1", "win", "checkmate")
        _insert_game(migrated_db_path, "g2", "loss", "checkmate")
        _insert_game(migrated_db_path, "g3", "draw", "stalemate")
        resp = api_client.get("/api/game-endings/tree")
        assert resp.status_code == 200
        body = resp.json()
        by_id = dict(zip(body["ids"], body["values"]))
        assert by_id["root"] == 3
        assert by_id["win"] == 1
        assert by_id["loss"] == 1
        assert by_id["draw"] == 1
        assert by_id["win/checkmate"] == 1
        assert by_id["loss/checkmate"] == 1
        assert by_id["draw/stalemate"] == 1
        parents_by_id = dict(zip(body["ids"], body["parents"]))
        assert parents_by_id["win/checkmate"] == "win"
        assert parents_by_id["loss/checkmate"] == "loss"

    def test_time_control_filter_narrows_the_tree(self, api_client, migrated_db_path):
        _insert_game(migrated_db_path, "g1", "loss", "checkmate", time_control_category="bullet")
        _insert_game(migrated_db_path, "g2", "loss", "checkmate", time_control_category="blitz")
        resp = api_client.get("/api/game-endings/tree?time_control=bullet")
        assert resp.status_code == 200
        by_id = dict(zip(resp.json()["ids"], resp.json()["values"]))
        assert by_id["loss/checkmate"] == 1
        assert by_id["root"] == 1

    def test_unrecognized_time_control_falls_back_to_all(self, api_client, migrated_db_path):
        _insert_game(migrated_db_path, "g1", "loss", "checkmate", time_control_category="bullet")
        resp = api_client.get("/api/game-endings/tree?time_control=nonsense")
        assert resp.status_code == 200
        by_id = dict(zip(resp.json()["ids"], resp.json()["values"]))
        assert by_id["root"] == 1

    def test_resignation_cause_level_only_appears_under_loss_resignation(self, api_client, migrated_db_path):
        conn = sqlite3.connect(migrated_db_path)
        conn.execute(
            "INSERT INTO games (id, white, black, outcome_for_player, game_end_type, num_plies) "
            "VALUES ('g1', 'W', 'B', 'loss', 'resignation', 10)")
        conn.commit()
        conn.close()
        resp = api_client.get("/api/game-endings/tree")
        body = resp.json()
        cause_ids = [i for i in body["ids"] if i.startswith("loss/resignation/")]
        assert "loss/resignation/not_analyzed" in cause_ids
        # No cause level exists for a checkmate loss (no cause classifier for it).
        assert not any(i.startswith("loss/checkmate/") for i in body["ids"])

    def test_reset_caches_between_tests_ttl_cache(self, api_client, migrated_db_path):
        import data
        call_count = {"n": 0}
        real = data.build_ending_tree

        def _counting(*args, **kwargs):
            call_count["n"] += 1
            return real(*args, **kwargs)
        import api.main as api_main
        original = data.build_ending_tree
        try:
            data.build_ending_tree = _counting
            api_client.get("/api/game-endings/tree")
            api_client.get("/api/game-endings/tree")
            assert call_count["n"] == 1
            api_main.reset_caches()
            api_client.get("/api/game-endings/tree")
            assert call_count["n"] == 2
        finally:
            data.build_ending_tree = original


@pytest.mark.integration
class TestEndingTreeGames:
    def test_result_endtype_path_returns_matching_game_ids(self, api_client, migrated_db_path):
        _insert_game(migrated_db_path, "g1", "loss", "checkmate", utc_date="2026.01.01")
        _insert_game(migrated_db_path, "g2", "loss", "checkmate", utc_date="2026.01.02")
        _insert_game(migrated_db_path, "g3", "win", "checkmate", utc_date="2026.01.01")
        resp = api_client.get("/api/game-endings/games?path=loss/checkmate")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert body["game_ids"] == ["g2", "g1"]  # newest first
        assert body["secondary_chart"] is None

    def test_time_control_filter_applies_to_drilldown_too(self, api_client, migrated_db_path):
        _insert_game(migrated_db_path, "g1", "loss", "checkmate", time_control_category="bullet")
        _insert_game(migrated_db_path, "g2", "loss", "checkmate", time_control_category="blitz")
        resp = api_client.get("/api/game-endings/games?path=loss/checkmate&time_control=bullet")
        assert resp.status_code == 200
        assert resp.json()["game_ids"] == ["g1"]

    def test_resignation_hung_piece_returns_piece_secondary_chart(self, api_client, migrated_db_path):
        conn = sqlite3.connect(migrated_db_path)
        conn.execute(
            "INSERT INTO games (id, white, black, outcome_for_player, game_end_type, num_plies) "
            "VALUES ('g1', 'W', 'B', 'loss', 'resignation', 10)")
        conn.execute(
            "INSERT INTO moves (game_id, ply, move_number, color, san, piece, to_square, is_player_move, "
            "classification, cpl) VALUES ('g1', 8, 4, 'w', 'Nf3', 'N', 'f3', 1, 'blunder', 300)")
        conn.execute(
            "INSERT INTO moves (game_id, ply, move_number, color, san, is_capture, to_square, "
            "material_delta, is_player_move) VALUES ('g1', 9, 5, 'b', 'Bxf3', 1, 'f3', 300, 0)")
        conn.commit()
        conn.close()
        resp = api_client.get("/api/game-endings/games?path=loss/resignation/hung_piece")
        assert resp.status_code == 200
        body = resp.json()
        assert body["game_ids"] == ["g1"]
        assert body["secondary_chart_kind"] == "piece"
        assert body["secondary_chart"] == [{"label": "Knight", "n": 1, "pct": 100.0}]

    def test_time_forfeit_bucket_returns_scramble_secondary_chart(self, api_client, migrated_db_path):
        conn = sqlite3.connect(migrated_db_path)
        conn.execute(
            "INSERT INTO games (id, white, black, outcome_for_player, game_end_type, player_color) "
            "VALUES ('g1', 'W', 'B', 'loss', 'time_forfeit', 'white')")
        conn.execute(
            "INSERT INTO moves (game_id, ply, move_number, color, san, clock_seconds, is_player_move) "
            "VALUES ('g1', 1, 1, 'b', 'Nf3', 90, 0)")
        conn.execute(
            "INSERT INTO moves (game_id, ply, move_number, color, san, material_sig, material_delta, "
            "is_player_move) VALUES ('g1', 2, 1, 'w', 'e5', 'R2P7vP7', 0, 1)")
        conn.commit()
        conn.close()
        resp = api_client.get("/api/game-endings/games?path=loss/time_forfeit/ahead")
        assert resp.status_code == 200
        body = resp.json()
        assert body["game_ids"] == ["g1"]
        assert body["secondary_chart_kind"] == "scramble"
        labels = {row["label"] for row in body["secondary_chart"]}
        assert any("comfortable" in label for label in labels)

    def test_unrecognized_path_returns_400(self, api_client):
        resp = api_client.get("/api/game-endings/games?path=nonsense")
        assert resp.status_code == 400


@pytest.mark.integration
class TestEndingSummary:
    def test_empty_db_returns_zeroed_shape(self, api_client):
        resp = api_client.get("/api/game-endings/summary")
        assert resp.status_code == 200
        body = resp.json()
        assert body["hero"] == {
            "total_games": 0, "decisive_pct": None, "draw_pct": None,
            "resignation_explained_pct": None, "flagged_while_ahead_pct": None,
        }
        assert body["endgame_material"] == []
        assert body["resignation_trend"] == []
        assert body["time_forfeit_trend"] == []

    def test_hero_stats_from_populated_db(self, api_client, migrated_db_path):
        _insert_game(migrated_db_path, "g1", "win", "checkmate")
        _insert_game(migrated_db_path, "g2", "loss", "checkmate")
        _insert_game(migrated_db_path, "g3", "draw", "stalemate")
        resp = api_client.get("/api/game-endings/summary")
        assert resp.status_code == 200
        hero = resp.json()["hero"]
        assert hero["total_games"] == 3
        assert round(hero["decisive_pct"]) == 67
        assert round(hero["draw_pct"]) == 33

    def test_reset_caches_between_tests_ttl_cache(self, api_client, migrated_db_path):
        import data
        call_count = {"n": 0}
        real = data.build_ending_summary

        def _counting(*args, **kwargs):
            call_count["n"] += 1
            return real(*args, **kwargs)
        import api.main as api_main
        try:
            data.build_ending_summary = _counting
            api_client.get("/api/game-endings/summary")
            api_client.get("/api/game-endings/summary")
            assert call_count["n"] == 1
            api_main.reset_caches()
            api_client.get("/api/game-endings/summary")
            assert call_count["n"] == 2
        finally:
            data.build_ending_summary = real
