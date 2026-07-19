"""Integration tests for the Patterns & Tendencies comparisons endpoint --
split from test_api_patterns.py, see
docs/superpowers/specs/2026-07-17-test-suite-reorg-and-speedup-design.md.
"""
import pathlib
import sqlite3
import sys

import pytest

from tests.conftest import _seed_rating_bucket_game

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
DASHBOARD_DIR = REPO_ROOT / "dashboard"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(DASHBOARD_DIR))


def _seed_clock_pressure_game(db_path, game_id, clock_seconds, base_seconds=180, cpl=20,
                               classification="good", rating_diff=None, outcome=None,
                               player_color=None, opening_family=None):
    """One game + one analyzed, clocked player move -- shared seed shape
    for all 4 of get_clock_pressure_by_{rating_bucket,outcome,color,opening}
    (each crosses TIME_PRESSURE_BUCKETS with a different game-level
    dimension column, all optional here so one helper covers all 4)."""
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO games (id, white, black, base_seconds, rating_diff, outcome_for_player, "
        "player_color, opening_family) VALUES (?, 'W', 'B', ?, ?, ?, ?, ?)",
        (game_id, base_seconds, rating_diff, outcome, player_color, opening_family))
    conn.execute(
        "INSERT INTO moves (game_id, ply, move_number, color, san, is_player_move, cpl, "
        "classification, clock_seconds) VALUES (?, 1, 1, 'w', 'e4', 1, ?, ?, ?)",
        (game_id, cpl, classification, clock_seconds))
    conn.commit()
    conn.close()


@pytest.mark.integration
class TestPatternsComparisons:
    def test_empty_db_returns_zero_filled_shape(self, api_client):
        resp = api_client.get("/api/patterns/comparisons")
        assert resp.status_code == 200
        body = resp.json()
        assert body["favorite_underdog"] == {"win": [], "acpl": []}
        assert body["clock_pressure_by_rating_bucket"] == []
        assert body["openings_by_rating_bucket"] == []
        assert body["clock_pressure_by_outcome"] == []
        assert body["clock_pressure_by_color"] == []
        assert body["clock_pressure_by_opening"] == []

    def test_favorite_underdog_bundles_win_and_acpl(self, api_client, migrated_db_path):
        # underdog_max=-100, favorite_min=100 (config.yaml's real
        # rating_diff_buckets) -- -150 is underdog, +150 is favorite.
        _seed_rating_bucket_game(migrated_db_path, "u1", -150, "win", cpl=10)
        _seed_rating_bucket_game(migrated_db_path, "u2", -150, "loss")  # no cpl -- unanalyzed
        _seed_rating_bucket_game(migrated_db_path, "f1", 150, "loss", cpl=90)

        resp = api_client.get("/api/patterns/comparisons")
        assert resp.status_code == 200
        body = resp.json()
        win_lookup = {r["bucket"]: r for r in body["favorite_underdog"]["win"]}
        assert win_lookup["underdog"]["n_games"] == 2
        assert win_lookup["underdog"]["win_pct"] == pytest.approx(50.0)
        assert win_lookup["favorite"]["n_games"] == 1
        assert win_lookup["favorite"]["win_pct"] == pytest.approx(0.0)

        acpl_lookup = {r["bucket"]: r for r in body["favorite_underdog"]["acpl"]}
        # Only u1 has cpl -- u2 (no cpl) contributes to win_pct but not acpl.
        assert acpl_lookup["underdog"]["n_games"] == 1
        assert acpl_lookup["underdog"]["acpl"] == pytest.approx(10.0)
        assert acpl_lookup["favorite"]["acpl"] == pytest.approx(90.0)

    def test_clock_pressure_by_rating_bucket_splits_by_bucket(self, api_client, migrated_db_path):
        _seed_clock_pressure_game(migrated_db_path, "u1", clock_seconds=5, cpl=150,
                                   classification="blunder", rating_diff=-150)
        _seed_clock_pressure_game(migrated_db_path, "f1", clock_seconds=170, cpl=10,
                                   classification="good", rating_diff=150)

        resp = api_client.get("/api/patterns/comparisons")
        body = resp.json()
        rows = {(r["rating_bucket"], r["time_bucket"]): r for r in body["clock_pressure_by_rating_bucket"]}
        assert rows[("underdog", "critical (<5%)")]["acpl"] == pytest.approx(150.0)
        assert rows[("underdog", "critical (<5%)")]["blunder_rate"] == pytest.approx(100.0)
        assert rows[("favorite", "plenty (60-100%)")]["acpl"] == pytest.approx(10.0)

    def test_openings_by_rating_bucket_returns_complete_families(self, api_client, migrated_db_path):
        # min_games_per_group=5 (config.yaml) -- get_openings_by_rating_bucket
        # only surfaces a (family, bucket) pair with >= 5 games, and only
        # keeps families present in EVERY rating_bucket actually in the data.
        for i in range(5):
            _seed_rating_bucket_game(migrated_db_path, f"u{i}", -150, "win",
                                      opening_family="Sicilian Defense")
        for i in range(5):
            _seed_rating_bucket_game(migrated_db_path, f"f{i}", 150, "loss",
                                      opening_family="Sicilian Defense")

        resp = api_client.get("/api/patterns/comparisons")
        body = resp.json()
        rows = {r["rating_bucket"]: r for r in body["openings_by_rating_bucket"]}
        assert rows["underdog"]["opening_family"] == "Sicilian Defense"
        assert rows["underdog"]["n_games"] == 5
        assert rows["underdog"]["win_pct"] == pytest.approx(100.0)
        assert rows["favorite"]["win_pct"] == pytest.approx(0.0)

    def test_clock_pressure_by_outcome_splits_win_loss(self, api_client, migrated_db_path):
        _seed_clock_pressure_game(migrated_db_path, "w1", clock_seconds=170, cpl=10, outcome="win")
        _seed_clock_pressure_game(migrated_db_path, "l1", clock_seconds=5, cpl=150, outcome="loss")

        resp = api_client.get("/api/patterns/comparisons")
        body = resp.json()
        rows = {(r["outcome"], r["time_bucket"]): r for r in body["clock_pressure_by_outcome"]}
        assert rows[("win", "plenty (60-100%)")]["acpl"] == pytest.approx(10.0)
        assert rows[("loss", "critical (<5%)")]["acpl"] == pytest.approx(150.0)

    def test_clock_pressure_by_color_splits_white_black(self, api_client, migrated_db_path):
        _seed_clock_pressure_game(migrated_db_path, "w1", clock_seconds=170, cpl=10,
                                   player_color="white")
        _seed_clock_pressure_game(migrated_db_path, "b1", clock_seconds=5, cpl=150,
                                   player_color="black")

        resp = api_client.get("/api/patterns/comparisons")
        body = resp.json()
        rows = {(r["color"], r["time_bucket"]): r for r in body["clock_pressure_by_color"]}
        assert rows[("white", "plenty (60-100%)")]["acpl"] == pytest.approx(10.0)
        assert rows[("black", "critical (<5%)")]["acpl"] == pytest.approx(150.0)

    def test_clock_pressure_by_opening_returns_rows(self, api_client, migrated_db_path):
        _seed_clock_pressure_game(migrated_db_path, "c1", clock_seconds=5, cpl=150,
                                   opening_family="Queen's Gambit")
        _seed_clock_pressure_game(migrated_db_path, "p1", clock_seconds=170, cpl=10,
                                   opening_family="Queen's Gambit")

        resp = api_client.get("/api/patterns/comparisons")
        body = resp.json()
        rows = {(r["opening_family"], r["time_bucket"]): r for r in body["clock_pressure_by_opening"]}
        assert rows[("Queen's Gambit", "critical (<5%)")]["acpl"] == pytest.approx(150.0)
        assert rows[("Queen's Gambit", "plenty (60-100%)")]["acpl"] == pytest.approx(10.0)

    def test_ttl_cache_reset_between_tests(self, api_client, migrated_db_path, monkeypatch):
        import data
        call_count = {"n": 0}
        real = data.get_favorite_underdog_performance

        def _counting(*args, **kwargs):
            call_count["n"] += 1
            return real(*args, **kwargs)
        monkeypatch.setattr(data, "get_favorite_underdog_performance", _counting)

        api_client.get("/api/patterns/comparisons")
        api_client.get("/api/patterns/comparisons")
        assert call_count["n"] == 1

        import api.main as api_main
        api_main.reset_caches()
        api_client.get("/api/patterns/comparisons")
        assert call_count["n"] == 2
