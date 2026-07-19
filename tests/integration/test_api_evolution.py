"""Integration tests for the Repertoire Evolution endpoints -- see
docs/superpowers/specs/2026-07-15-repertoire-evolution-page-design.md.
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


def _insert_game(db_path, game_id, opening_family="Sicilian Defense",
                  player_color="white", outcome_for_player="win",
                  year=2024, month=1, time_control_category="blitz", eco="B20"):
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO games (id, white, black, opening_family, player_color, "
        "outcome_for_player, year, month, time_control_category, eco) "
        "VALUES (?, 'W', 'B', ?, ?, ?, ?, ?, ?, ?)",
        [game_id, opening_family, player_color, outcome_for_player,
         year, month, time_control_category, eco])
    conn.commit()
    conn.close()


def _insert_move(db_path, game_id, ply, move_number, cpl):
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO moves (game_id, ply, move_number, color, san, is_player_move, cpl) "
        "VALUES (?, ?, ?, 'w', 'Nf3', 1, ?)",
        [game_id, ply, move_number, cpl])
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
class TestEvolutionSummary:
    def test_empty_db_returns_zeroed_shape(self, api_client):
        resp = api_client.get("/api/evolution/summary", params={"color": "white"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_games"] == 0
        assert body["n_periods"] == 0
        assert body["composition"]["shares"] == []
        assert body["composition"]["top"] == []
        assert body["ledger"] == []
        assert body["strips"] == []

    def test_returns_populated_ledger_and_strips(self, api_client, migrated_db_path):
        # 20 games clears MIN_FAMILY_GAMES (20); cycling through 8 distinct
        # quarters (not one game per quarter) keeps n_periods at exactly 8
        # while still giving both the early and late 4-quarter windows a
        # non-zero total, so the ledger isn't returned empty.
        for i in range(20):
            q = i % 8
            year = 2018 + q // 4
            month = 1 + 3 * (q % 4)
            _insert_game(migrated_db_path, f"game_{i}", opening_family="Sicilian Defense",
                        player_color="white", year=year, month=month)
        resp = api_client.get("/api/evolution/summary", params={"color": "white"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_games"] == 20
        assert body["n_periods"] == 8
        assert "Sicilian Defense" in {row["family"] for row in body["ledger"]}
        assert "Sicilian Defense" in {row["family"] for row in body["strips"]}

    def test_filters_by_color(self, api_client, migrated_db_path):
        _insert_game(migrated_db_path, "game_1", player_color="white")
        _insert_game(migrated_db_path, "game_2", player_color="black")
        resp = api_client.get("/api/evolution/summary", params={"color": "white"})
        assert resp.json()["total_games"] == 1

    def test_filters_by_time_control(self, api_client, migrated_db_path):
        _insert_game(migrated_db_path, "game_1", time_control_category="blitz")
        _insert_game(migrated_db_path, "game_2", time_control_category="rapid")
        resp = api_client.get("/api/evolution/summary",
                              params={"color": "white", "time_control": "blitz"})
        assert resp.json()["total_games"] == 1

    def test_grouping_eco_collapses_to_eco_section(self, api_client, migrated_db_path):
        _insert_game(migrated_db_path, "game_1", opening_family="Sicilian Defense", eco="B20")
        resp = api_client.get("/api/evolution/summary",
                              params={"color": "white", "grouping": "eco"})
        body = resp.json()
        assert body["composition"]["shares"][0]["family"] == "B — Semi-open games"

    def test_ledger_nan_win_rate_serializes_as_null_not_500(self, api_client, migrated_db_path):
        # An "adopted" family (absent early, present late) has win_early
        # == NaN in classify_evolution's output -- must serialize as null,
        # not crash the response (the bug this endpoint fixes vs. the
        # spec's literal sample).
        for i in range(20):
            _insert_game(migrated_db_path, f"anchor_{i}", opening_family="Anchor",
                        player_color="white", year=2018 + i // 4, month=1 + 3 * (i % 4))
        for i in range(20):
            _insert_game(migrated_db_path, f"new_{i}", opening_family="New Line",
                        player_color="white", year=2025, month=1 + 3 * (i % 4))
        resp = api_client.get("/api/evolution/summary", params={"color": "white"})
        assert resp.status_code == 200
        new_line = next(r for r in resp.json()["ledger"] if r["family"] == "New Line")
        assert new_line["status"] == "adopted"
        assert new_line["win_early"] is None

    def test_ttl_cache_reset_between_tests(self, api_client, migrated_db_path, monkeypatch):
        import data
        call_count = {"n": 0}
        real_get_family_period_counts = data.get_family_period_counts

        def _counting(*args, **kwargs):
            call_count["n"] += 1
            return real_get_family_period_counts(*args, **kwargs)
        monkeypatch.setattr(data, "get_family_period_counts", _counting)

        api_client.get("/api/evolution/summary", params={"color": "white"})
        api_client.get("/api/evolution/summary", params={"color": "white"})
        assert call_count["n"] == 1  # served from _evolution_counts_cache

        import api.main as api_main
        api_main.reset_caches()
        api_client.get("/api/evolution/summary", params={"color": "white"})
        assert call_count["n"] == 2


@pytest.mark.integration
class TestEvolutionFamilyTrend:
    def test_unknown_family_returns_empty_list(self, api_client, migrated_db_path):
        _insert_game(migrated_db_path, "game_1", opening_family="Sicilian Defense")
        resp = api_client.get("/api/evolution/family-trend",
                              params={"family": "Nonexistent", "color": "white"})
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_win_pct_per_quarter(self, api_client, migrated_db_path):
        for i in range(6):
            _insert_game(migrated_db_path, f"game_{i}", opening_family="Sicilian Defense",
                        player_color="white", year=2024, month=1,
                        outcome_for_player="win" if i < 4 else "loss")
        resp = api_client.get("/api/evolution/family-trend",
                              params={"family": "Sicilian Defense", "color": "white"})
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["win_pct"] == pytest.approx(100.0 * 4 / 6)


@pytest.mark.integration
class TestEvolutionFamilyAcpl:
    def test_no_moves_returns_empty_list(self, api_client, migrated_db_path):
        _insert_game(migrated_db_path, "game_1", opening_family="Sicilian Defense")
        resp = api_client.get("/api/evolution/family-acpl",
                              params={"family": "Sicilian Defense", "color": "white"})
        assert resp.status_code == 200
        assert resp.json() == []

    def test_below_min_moves_per_quarter_dropped(self, api_client, migrated_db_path):
        _insert_game(migrated_db_path, "game_1", opening_family="Sicilian Defense",
                    player_color="white", year=2024, month=1)
        for ply in range(10):  # below the 30-move floor
            _insert_move(migrated_db_path, "game_1", ply, ply // 2 + 1, cpl=20)
        resp = api_client.get("/api/evolution/family-acpl",
                              params={"family": "Sicilian Defense", "color": "white"})
        assert resp.json() == []

    def test_returns_acpl_with_coverage_when_moves_clear_floor(self, api_client, migrated_db_path):
        _insert_game(migrated_db_path, "game_1", opening_family="Sicilian Defense",
                    player_color="white", year=2024, month=1)
        for ply in range(32):
            _insert_move(migrated_db_path, "game_1", ply, ply // 2 + 1, cpl=20)
        resp = api_client.get("/api/evolution/family-acpl",
                              params={"family": "Sicilian Defense", "color": "white"})
        body = resp.json()
        assert len(body) == 1
        assert body[0]["acpl"] == pytest.approx(20.0)
        assert body[0]["coverage_pct"] == pytest.approx(100.0)

    def test_acpl_cache_keyed_per_family_not_shared(self, api_client, migrated_db_path):
        _insert_game(migrated_db_path, "game_1", opening_family="Sicilian Defense",
                    player_color="white", year=2024, month=1)
        _insert_game(migrated_db_path, "game_2", opening_family="French Defense",
                    player_color="white", year=2024, month=1)
        for ply in range(32):
            _insert_move(migrated_db_path, "game_1", ply, ply // 2 + 1, cpl=20)
        for ply in range(32):
            _insert_move(migrated_db_path, "game_2", ply, ply // 2 + 1, cpl=80)
        r1 = api_client.get("/api/evolution/family-acpl",
                            params={"family": "Sicilian Defense", "color": "white"})
        r2 = api_client.get("/api/evolution/family-acpl",
                            params={"family": "French Defense", "color": "white"})
        assert r1.json()[0]["acpl"] == pytest.approx(20.0)
        assert r2.json()[0]["acpl"] == pytest.approx(80.0)
