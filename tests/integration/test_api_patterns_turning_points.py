"""Integration tests for the Patterns & Tendencies turning-points endpoint --
split from test_api_patterns.py, see
docs/superpowers/specs/2026-07-17-test-suite-reorg-and-speedup-design.md.
"""
import pathlib
import sqlite3
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
DASHBOARD_DIR = REPO_ROOT / "dashboard"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(DASHBOARD_DIR))


@pytest.mark.integration
class TestPatternsTurningPoints:
    def test_empty_db_returns_zero_filled_shape(self, api_client):
        resp = api_client.get("/api/patterns/turning-points")
        assert resp.status_code == 200
        assert resp.json() == {
            "n_losses": 0, "median_move": None, "most_common_phase": None,
            "by_move_bucket": [], "by_phase": [], "by_clock_bucket": [], "n_no_clock_data": 0,
        }

    def _insert_loss_game(self, db_path, game_id, base_seconds=180):
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO games (id, white, black, outcome_for_player, base_seconds) "
            "VALUES (?, 'W', 'B', 'loss', ?)", [game_id, base_seconds])
        conn.commit()
        conn.close()

    def _insert_decisive_move(self, db_path, game_id, ply, move_number, win_prob_before,
                               win_prob_after, clock_seconds=None):
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO moves (game_id, ply, move_number, color, san, is_player_move, "
            "win_prob_before, win_prob_after, clock_seconds) "
            "VALUES (?, ?, ?, 'w', 'e4', 1, ?, ?, ?)",
            [game_id, ply, move_number, win_prob_before, win_prob_after, clock_seconds])
        conn.commit()
        conn.close()

    def test_bundles_real_data(self, api_client, migrated_db_path):
        self._insert_loss_game(migrated_db_path, "g1", base_seconds=180)
        self._insert_decisive_move(migrated_db_path, "g1", ply=15, move_number=8,
                                    win_prob_before=0.60, win_prob_after=0.20, clock_seconds=90)
        self._insert_loss_game(migrated_db_path, "g2", base_seconds=180)
        self._insert_decisive_move(migrated_db_path, "g2", ply=41, move_number=21,
                                    win_prob_before=0.55, win_prob_after=0.35, clock_seconds=None)

        resp = api_client.get("/api/patterns/turning-points")
        assert resp.status_code == 200
        body = resp.json()
        assert body["n_losses"] == 2
        assert body["median_move"] == 14
        assert body["most_common_phase"] == "middlegame"
        assert {"bucket": "6–10", "n_losses": 1} in body["by_move_bucket"]
        assert {"bucket": "21–25", "n_losses": 1} in body["by_move_bucket"]
        assert body["by_clock_bucket"] == [{"bucket": "comfortable (30-60%)", "n_losses": 1}]
        assert body["n_no_clock_data"] == 1

    def test_ttl_cache_reset_between_tests(self, api_client, migrated_db_path, monkeypatch):
        from data.patterns import correlations
        call_count = {"n": 0}
        real = correlations.get_decisive_moments

        def _counting(*args, **kwargs):
            call_count["n"] += 1
            return real(*args, **kwargs)
        # get_decisive_moments_breakdown calls get_decisive_moments as a
        # module-local name inside data/patterns/correlations.py, not via
        # data.get_decisive_moments -- patching the package re-export
        # wouldn't intercept that call.
        monkeypatch.setattr(correlations, "get_decisive_moments", _counting)

        api_client.get("/api/patterns/turning-points")
        api_client.get("/api/patterns/turning-points")
        assert call_count["n"] == 1

        import api.main as api_main
        api_main.reset_caches()
        api_client.get("/api/patterns/turning-points")
        assert call_count["n"] == 2
