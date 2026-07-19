"""Integration tests for the Patterns & Tendencies sessions endpoint --
split from test_api_patterns.py, see
docs/superpowers/specs/2026-07-17-test-suite-reorg-and-speedup-design.md.
"""
import pathlib
import sqlite3
import sys

import pytest

from tests.conftest import _seed_session_game

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
DASHBOARD_DIR = REPO_ROOT / "dashboard"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(DASHBOARD_DIR))


def _seed_event_game(db_path, game_id, event, outcome, cpl=None):
    """Mirrors tests/integration/test_event_type_performance.py's _seed_game."""
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO games (id, white, black, event, outcome_for_player) "
        "VALUES (?, 'W', 'B', ?, ?)", (game_id, event, outcome))
    conn.execute(
        "INSERT INTO moves (game_id, ply, move_number, color, san, is_player_move, cpl) "
        "VALUES (?, 1, 1, 'w', 'e4', 1, ?)", (game_id, cpl))
    conn.commit()
    conn.close()


@pytest.mark.integration
class TestPatternsSessions:
    def test_empty_db_returns_zero_filled_shape(self, api_client):
        resp = api_client.get("/api/patterns/sessions")
        assert resp.status_code == 200
        body = resp.json()
        assert body["session_rollup"] == []
        assert body["prior_outcome"] == []
        assert body["session_position"] == []
        assert body["event_type"] == []
        assert body["event_name_breakdown"] == []

    def test_session_rollup_computes_win_pct_and_acpl_per_session(self, api_client, migrated_db_path):
        # session_gap_minutes=30 (config.yaml): g1/g2 five minutes apart ->
        # one session; g3 the next day -> a second, separate session.
        _seed_session_game(migrated_db_path, "g1", "2026.01.01", "10:00:00", "win", cpl=10)
        _seed_session_game(migrated_db_path, "g2", "2026.01.01", "10:05:00", "loss")
        _seed_session_game(migrated_db_path, "g3", "2026.01.02", "09:00:00", "win")

        resp = api_client.get("/api/patterns/sessions")
        assert resp.status_code == 200
        body = resp.json()
        rollup = body["session_rollup"]
        assert len(rollup) == 2
        session_a, session_b = rollup[0], rollup[1]  # sorted by session_start ascending
        assert session_a["n_games"] == 2
        assert session_a["win_pct"] == pytest.approx(50.0)
        assert session_a["loss_pct"] == pytest.approx(50.0)
        assert session_a["acpl"] == pytest.approx(10.0)
        assert session_a["n_analyzed"] == 1
        assert session_b["n_games"] == 1
        assert session_b["win_pct"] == pytest.approx(100.0)
        assert session_b["acpl"] is None
        assert session_b["n_analyzed"] == 0

    def test_prior_outcome_performance_bundled(self, api_client, migrated_db_path):
        _seed_session_game(migrated_db_path, "g1", "2026.01.01", "10:00:00", "win", cpl=10)
        _seed_session_game(migrated_db_path, "g2", "2026.01.01", "10:05:00", "loss", cpl=200)

        resp = api_client.get("/api/patterns/sessions")
        body = resp.json()
        lookup = {r["bucket"]: r for r in body["prior_outcome"]}
        assert lookup["first_game_of_session"]["acpl"] == pytest.approx(10.0)
        # g2's prior game (g1) was a win -> g2 falls in the "after a win" bucket.
        assert lookup["after a win"]["acpl"] == pytest.approx(200.0)

    def test_session_position_performance_bundled(self, api_client, migrated_db_path):
        _seed_session_game(migrated_db_path, "g1", "2026.01.01", "10:00:00", "win", cpl=10)
        _seed_session_game(migrated_db_path, "g2", "2026.01.01", "10:05:00", "loss", cpl=200)

        resp = api_client.get("/api/patterns/sessions")
        body = resp.json()
        lookup = {r["position"]: r for r in body["session_position"]}
        assert lookup["game #1"]["acpl"] == pytest.approx(10.0)
        assert lookup["game #2"]["acpl"] == pytest.approx(200.0)

    def test_event_type_performance_two_rows(self, api_client, migrated_db_path):
        _seed_event_game(migrated_db_path, "c1", "Rated Blitz game", "win", cpl=10)
        _seed_event_game(migrated_db_path, "c2", "Rated Blitz game", "loss")
        _seed_event_game(migrated_db_path, "t1", "Weekly Rapid Arena", "win", cpl=50)

        resp = api_client.get("/api/patterns/sessions")
        body = resp.json()
        lookup = {r["category"]: r for r in body["event_type"]}
        assert lookup["Casual"]["n_games"] == 2
        assert lookup["Casual"]["win_pct"] == pytest.approx(50.0)
        assert lookup["Tournament / Arena"]["n_games"] == 1
        assert lookup["Tournament / Arena"]["acpl"] == pytest.approx(50.0)

    def test_event_name_breakdown_gated_by_min_games(self, api_client, migrated_db_path):
        # min_sample_size=5 (config.yaml, get_event_name_breakdown's default
        # min_games) -- 5 "Weekly Rapid Arena" games clear the gate, 1
        # "Titled Tuesday" game doesn't and is excluded entirely.
        for i in range(5):
            _seed_event_game(migrated_db_path, f"arena{i}", "Weekly Rapid Arena", "win", cpl=20)
        _seed_event_game(migrated_db_path, "onceoff", "Titled Tuesday", "loss")

        resp = api_client.get("/api/patterns/sessions")
        body = resp.json()
        events = {r["event"] for r in body["event_name_breakdown"]}
        assert events == {"Weekly Rapid Arena"}
        row = body["event_name_breakdown"][0]
        assert row["n_games"] == 5
        assert row["win_pct"] == pytest.approx(100.0)
        assert row["acpl"] == pytest.approx(20.0)

    def test_ttl_cache_reset_between_tests(self, api_client, migrated_db_path, monkeypatch):
        import data
        call_count = {"n": 0}
        real = data.get_session_rollup

        def _counting(*args, **kwargs):
            call_count["n"] += 1
            return real(*args, **kwargs)
        monkeypatch.setattr(data, "get_session_rollup", _counting)

        api_client.get("/api/patterns/sessions")
        api_client.get("/api/patterns/sessions")
        assert call_count["n"] == 1

        import api.main as api_main
        api_main.reset_caches()
        api_client.get("/api/patterns/sessions")
        assert call_count["n"] == 2


