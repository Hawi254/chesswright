"""Integration tests for GET /api/points/summary -- see
docs/superpowers/specs/2026-07-16-points-page-design.md.
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


def _insert_ledger_game(db_path, game_id, outcome_for_player, moves,
                         time_control_category="blitz", utc_date="2026.01.01", site="?"):
    """moves: list of (ply, move_number, win_prob_before) tuples. Every row
    is inserted as is_player_move=1 -- get_points_ledger's CASE only reads
    player_wp off is_player_move rows directly, so omitting opponent-move
    rows entirely is the simplest way to author an exact win-prob curve."""
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO games (id, white, black, outcome_for_player, analysis_status, "
        "time_control_category, utc_date, site, opponent_name) "
        "VALUES (?, 'W', 'B', ?, 'done', ?, ?, ?, 'Foe')",
        [game_id, outcome_for_player, time_control_category, utc_date, site])
    for ply, move_number, wp in moves:
        conn.execute(
            "INSERT INTO moves (game_id, ply, move_number, color, san, is_player_move, win_prob_before) "
            "VALUES (?, ?, ?, ?, 'e4', 1, ?)",
            [game_id, ply, move_number, "w" if ply % 2 == 1 else "b", wp])
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
class TestPointsSummary:
    def test_empty_db_returns_zero_shape_with_analyzed_games_for_the_message(self, api_client):
        resp = api_client.get("/api/points/summary")
        assert resp.status_code == 200
        body = resp.json()
        assert body["tc_options"] == []
        assert body["n_games"] == 0
        assert body["buckets"] == []
        assert body["costliest_games"] == []
        assert body["analyzed_games"] == 0

    def test_classifies_one_game_into_each_of_the_three_buckets(self, api_client, migrated_db_path):
        _insert_ledger_game(migrated_db_path, "g1", "draw", [(1, 1, 0.95), (3, 2, 0.95)])   # failed_conversion
        _insert_ledger_game(migrated_db_path, "g2", "loss", [(1, 1, 0.10), (3, 3, 0.60)])   # missed_swindle
        _insert_ledger_game(migrated_db_path, "g3", "loss", [(1, 20, 0.50)])                # failed_hold
        resp = api_client.get("/api/points/summary")
        assert resp.status_code == 200
        body = resp.json()
        assert body["n_games"] == 3
        assert body["analyzed_games"] is None
        by_bucket = {b["bucket"]: b for b in body["buckets"]}
        assert by_bucket["failed_conversion"]["n_games"] == 1
        assert round(by_bucket["failed_conversion"]["leaked"], 2) == 0.45
        assert by_bucket["missed_swindle"]["n_games"] == 1
        assert round(by_bucket["missed_swindle"]["leaked"], 2) == 0.60
        assert by_bucket["failed_hold"] == {"bucket": "failed_hold", "n_games": 1, "leaked": 0.5}
        game_ids = {g["game_id"] for g in body["costliest_games"]}
        assert game_ids == {"g1", "g2", "g3"}
        conv_row = next(g for g in body["costliest_games"] if g["game_id"] == "g1")
        assert conv_row["best_chance"] == 0.95
        assert conv_row["bucket"] == "failed_conversion"
        # lichess_game_url only returns None for the literal chess.com site
        # header; any other site string (including "?") is treated as a
        # lichess game and reconstructed from game_id.
        assert conv_row["url"] == "https://lichess.org/g1"

    def test_time_control_filter_narrows_n_games_but_tc_options_stays_unfiltered(self, api_client, migrated_db_path):
        _insert_ledger_game(migrated_db_path, "g1", "draw", [(1, 1, 0.95)], time_control_category="bullet")
        _insert_ledger_game(migrated_db_path, "g2", "draw", [(1, 1, 0.95)], time_control_category="blitz")
        resp = api_client.get("/api/points/summary?time_control=bullet")
        assert resp.status_code == 200
        body = resp.json()
        assert body["n_games"] == 1
        assert body["tc_options"] == ["blitz", "bullet"]

    def test_time_control_with_zero_games_returns_empty_shape_but_keeps_tc_options(self, api_client, migrated_db_path):
        _insert_ledger_game(migrated_db_path, "g1", "draw", [(1, 1, 0.95)], time_control_category="blitz")
        resp = api_client.get("/api/points/summary?time_control=bullet")
        assert resp.status_code == 200
        body = resp.json()
        assert body["n_games"] == 0
        assert body["tc_options"] == ["blitz"]
        assert body["buckets"] == []
        assert body["analyzed_games"] is None

    def test_unrecognized_time_control_falls_back_to_all(self, api_client, migrated_db_path):
        _insert_ledger_game(migrated_db_path, "g1", "draw", [(1, 1, 0.95)], time_control_category="blitz")
        resp = api_client.get("/api/points/summary?time_control=nonsense")
        assert resp.status_code == 200
        assert resp.json()["n_games"] == 1

    def test_games_exist_but_no_leaks_returns_empty_buckets_with_nonzero_n_games(self, api_client, migrated_db_path):
        _insert_ledger_game(migrated_db_path, "g1", "win", [(1, 1, 0.95)])  # converted -- no leak
        resp = api_client.get("/api/points/summary")
        assert resp.status_code == 200
        body = resp.json()
        assert body["n_games"] == 1
        assert body["buckets"] == []
        assert body["costliest_games"] == []

    def test_reset_caches_between_tests_ttl_cache(self, api_client, migrated_db_path):
        _insert_ledger_game(migrated_db_path, "g1", "draw", [(1, 1, 0.95)])
        import data
        call_count = {"n": 0}
        real = data.summarize_buckets

        def _counting(*args, **kwargs):
            call_count["n"] += 1
            return real(*args, **kwargs)
        import api.main as api_main
        try:
            data.summarize_buckets = _counting
            api_client.get("/api/points/summary")
            api_client.get("/api/points/summary")
            assert call_count["n"] == 1
            api_main.reset_caches()
            api_client.get("/api/points/summary")
            assert call_count["n"] == 2
        finally:
            data.summarize_buckets = real
