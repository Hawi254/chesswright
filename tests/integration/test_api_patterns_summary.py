"""Integration tests for the Patterns & Tendencies summary endpoint --
split from test_api_patterns.py, see
docs/superpowers/specs/2026-07-17-test-suite-reorg-and-speedup-design.md.
"""
import pathlib
import sqlite3
import sys

import pytest

from tests.conftest import (
    _insert_game, _insert_move, _insert_full_game, _insert_full_move,
    _seed_rating_bucket_game, _seed_session_game,
)

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
DASHBOARD_DIR = REPO_ROOT / "dashboard"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(DASHBOARD_DIR))


@pytest.mark.integration
class TestPatternsSummary:
    def test_empty_db_returns_empty_list(self, api_client):
        resp = api_client.get("/api/patterns/summary")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_insufficient_data_omits_the_card(self, api_client, migrated_db_path):
        _insert_game(migrated_db_path, "g1", base_seconds=180, time_control_category="blitz")
        # Only 5 moves per bucket -- below MIN_BUCKET_MOVES (20), so both
        # buckets stay "insufficient" and the card is omitted, not sent
        # with a misleadingly thin sample.
        for i in range(5):
            _insert_move(migrated_db_path, "g1", ply=i + 1, move_number=i + 1, cpl=10,
                         classification="good", clock_seconds=170, time_spent_seconds=5)
        for i in range(5, 10):
            _insert_move(migrated_db_path, "g1", ply=i + 1, move_number=i + 1, cpl=200,
                         classification="blunder", clock_seconds=5, time_spent_seconds=5)
        resp = api_client.get("/api/patterns/summary")
        assert resp.json() == []

    def test_returns_clock_time_headline_card(self, api_client, migrated_db_path):
        _insert_game(migrated_db_path, "g1", base_seconds=180, time_control_category="blitz")
        # 20 moves per bucket clears MIN_BUCKET_MOVES (the "low" confidence
        # tier's cutoff) exactly at the boundary.
        for i in range(20):
            _insert_move(migrated_db_path, "g1", ply=i + 1, move_number=i + 1, cpl=10,
                         classification="good", clock_seconds=170, time_spent_seconds=5)
        for i in range(20, 40):
            _insert_move(migrated_db_path, "g1", ply=i + 1, move_number=i + 1, cpl=200,
                         classification="blunder", clock_seconds=5, time_spent_seconds=5)

        resp = api_client.get("/api/patterns/summary")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["tab_id"] == "clock-time"
        assert body[0]["label"] == "Clock & Time"
        assert "critical" in body[0]["headline"]
        assert "plenty" in body[0]["detail"]

    def test_returns_turning_points_headline_card(self, api_client, migrated_db_path):
        conn = sqlite3.connect(migrated_db_path)
        conn.execute(
            "INSERT INTO games (id, white, black, outcome_for_player, base_seconds) "
            "VALUES ('g1', 'W', 'B', 'loss', 180)")
        conn.execute(
            "INSERT INTO moves (game_id, ply, move_number, color, san, is_player_move, "
            "win_prob_before, win_prob_after) VALUES ('g1', 15, 8, 'w', 'e4', 1, 0.60, 0.20)")
        conn.commit()
        conn.close()

        resp = api_client.get("/api/patterns/summary")
        assert resp.status_code == 200
        body = resp.json()
        card = next(c for c in body if c["tab_id"] == "turning-points")
        assert card["label"] == "Turning Points"
        assert "move 8" in card["headline"]
        assert "opening" in card["headline"]
        assert "1 losses" in card["detail"]

    def test_returns_all_three_cards_in_order(self, api_client, migrated_db_path):
        conn = sqlite3.connect(migrated_db_path)
        conn.execute(
            "INSERT INTO games (id, white, black, base_seconds, time_control_category, "
            "outcome_for_player) VALUES ('g1', 'W', 'B', 180, 'blitz', 'loss')")
        for i in range(20):
            conn.execute(
                "INSERT INTO moves (game_id, ply, move_number, color, san, is_player_move, cpl, "
                "classification, clock_seconds, time_spent_seconds) "
                "VALUES ('g1', ?, ?, 'w', 'e4', 1, 10, 'good', 170, 5)", [i + 1, i + 1])
        for i in range(20, 40):
            conn.execute(
                "INSERT INTO moves (game_id, ply, move_number, color, san, is_player_move, cpl, "
                "classification, clock_seconds, time_spent_seconds) "
                "VALUES ('g1', ?, ?, 'w', 'e4', 1, 200, 'blunder', 5, 5)", [i + 1, i + 1])
        conn.execute(
            "INSERT INTO moves (game_id, ply, move_number, color, san, is_player_move, "
            "win_prob_before, win_prob_after) VALUES ('g1', 81, 41, 'w', 'e4', 1, 0.55, 0.20)")
        for i in range(20):
            conn.execute(
                "INSERT INTO moves (game_id, ply, move_number, color, san, is_player_move, cpl, "
                "classification, piece) VALUES ('g1', ?, ?, 'w', 'Qd4', 1, 10, 'good', 'Q')",
                [100 + i, 100 + i])
        for i in range(20):
            conn.execute(
                "INSERT INTO moves (game_id, ply, move_number, color, san, is_player_move, cpl, "
                "classification, piece) VALUES ('g1', ?, ?, 'w', 'Rd4', 1, 200, 'blunder', 'R')",
                [200 + i, 200 + i])
        conn.commit()
        conn.close()

        resp = api_client.get("/api/patterns/summary")
        assert resp.status_code == 200
        body = resp.json()
        assert [c["tab_id"] for c in body] == ["clock-time", "turning-points", "piece-handling"]

    def test_ttl_cache_reset_between_tests(self, api_client, migrated_db_path, monkeypatch):
        import data
        call_count = {"n": 0}
        real = data.get_blunder_rate_by_time_pressure

        def _counting(*args, **kwargs):
            call_count["n"] += 1
            return real(*args, **kwargs)
        monkeypatch.setattr(data, "get_blunder_rate_by_time_pressure", _counting)

        api_client.get("/api/patterns/summary")
        api_client.get("/api/patterns/summary")
        assert call_count["n"] == 1

        import api.main as api_main
        api_main.reset_caches()
        api_client.get("/api/patterns/summary")
        assert call_count["n"] == 2

    def test_returns_positions_headline_card(self, api_client, migrated_db_path):
        _insert_full_game(migrated_db_path, "g1")
        # 20 moves per bucket clears MIN_BUCKET_MOVES (20) exactly at the
        # boundary, same seed shape as test_returns_clock_time_headline_card.
        for i in range(20):
            _insert_full_move(migrated_db_path, "g1", ply=i + 1, move_number=i + 1,
                               is_player_move=1, cpl=10, classification="good", sharpness=2)
        for i in range(20, 40):
            _insert_full_move(migrated_db_path, "g1", ply=i + 1, move_number=i + 1,
                               is_player_move=1, cpl=200, classification="blunder", sharpness=250)

        resp = api_client.get("/api/patterns/summary")
        assert resp.status_code == 200
        body = resp.json()
        card = next(c for c in body if c["tab_id"] == "positions")
        assert card["label"] == "Positions"
        assert "forcing (200cp+)" in card["headline"]
        assert "flat (<5cp gap)" in card["detail"]

    def test_returns_game_context_headline_card(self, api_client, migrated_db_path):
        _insert_full_game(migrated_db_path, "g1")
        # See test_bundles_phase_accuracy's comment -- get_phase_accuracy
        # INNER JOINs structure_ctx, which needs >=1 material_sig-bearing
        # move to emit a row for this game at all.
        _insert_full_move(migrated_db_path, "g1", ply=1, move_number=1,
                           is_player_move=1, cpl=10, classification="good",
                           material_sig="Q1R2B2N2P8vQ1R2B2N2P8")
        _insert_full_move(migrated_db_path, "g1", ply=30, move_number=15,
                           is_player_move=1, cpl=200, classification="blunder")

        resp = api_client.get("/api/patterns/summary")
        assert resp.status_code == 200
        body = resp.json()
        card = next(c for c in body if c["tab_id"] == "game-context")
        assert card["label"] == "Game Context"
        assert "middlegame" in card["headline"]
        assert "200" in card["headline"]
        assert "opening" in card["detail"]

    def test_returns_comparisons_headline_card(self, api_client, migrated_db_path):
        _seed_rating_bucket_game(migrated_db_path, "u1", -150, "win")
        _seed_rating_bucket_game(migrated_db_path, "u2", -150, "win")
        _seed_rating_bucket_game(migrated_db_path, "u3", -150, "loss")
        _seed_rating_bucket_game(migrated_db_path, "f1", 150, "loss")
        _seed_rating_bucket_game(migrated_db_path, "f2", 150, "loss")
        _seed_rating_bucket_game(migrated_db_path, "f3", 150, "win")

        resp = api_client.get("/api/patterns/summary")
        assert resp.status_code == 200
        body = resp.json()
        card = next(c for c in body if c["tab_id"] == "comparisons")
        assert card["label"] == "Comparisons"
        assert "underdog" in card["headline"]
        assert "66.7" in card["headline"]
        assert "33.3" in card["detail"]

    def test_returns_sessions_headline_card(self, api_client, migrated_db_path):
        # 20 moves per bucket clears MIN_BUCKET_MOVES (20) exactly at the
        # boundary, same seed shape as test_returns_positions_headline_card.
        _seed_session_game(migrated_db_path, "g1", "2026.01.01", "10:00:00", "win",
                            n_moves=20, cpl=10)
        _seed_session_game(migrated_db_path, "g2", "2026.01.01", "10:05:00", "loss",
                            n_moves=20, cpl=200)

        resp = api_client.get("/api/patterns/summary")
        assert resp.status_code == 200
        body = resp.json()
        card = next(c for c in body if c["tab_id"] == "sessions")
        assert card["label"] == "Playing Sessions"
        assert "after a win" in card["headline"]
        assert "200" in card["headline"]
        assert "first_game_of_session" in card["detail"]
