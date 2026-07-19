"""Integration tests for the Patterns & Tendencies game-context endpoint --
split from test_api_patterns.py, see
docs/superpowers/specs/2026-07-17-test-suite-reorg-and-speedup-design.md.
"""
import pathlib
import sqlite3
import sys

import pytest

from tests.conftest import _insert_full_game, _insert_full_move

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
DASHBOARD_DIR = REPO_ROOT / "dashboard"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(DASHBOARD_DIR))


@pytest.mark.integration
class TestPatternsGameContext:
    def test_empty_db_returns_zero_filled_shape(self, api_client):
        resp = api_client.get("/api/patterns/game-context")
        assert resp.status_code == 200
        body = resp.json()
        assert body["phase_accuracy"] == []
        # config.yaml's real analytics.utc_offset_hours is 0 -- api_client
        # copies the real repo config.yaml verbatim (see its fixture).
        assert body["day_hour_heatmap"] == {"cells": [], "utc_offset_hours": 0}

    def test_bundles_phase_accuracy(self, api_client, migrated_db_path):
        _insert_full_game(migrated_db_path, "g1")
        # ply=1 < middlegame_ply(24) -> opening; ply=30 >= 24, no
        # endgame_sig seeded -> middlegame (see get_phase_accuracy's CASE).
        # get_phase_accuracy INNER JOINs structure_ctx, so the game needs at
        # least one material_sig-bearing move for compute_structure_context
        # to emit a row at all -- full-material sig (14 non-pawn pieces,
        # over endgame_max_pieces=6) so endgame_ply stays NULL, same as the
        # bishop-ending seed helper's non-checkpoint plies do implicitly.
        _insert_full_move(migrated_db_path, "g1", ply=1, move_number=1,
                           is_player_move=1, cpl=10, classification="good",
                           material_sig="Q1R2B2N2P8vQ1R2B2N2P8")
        _insert_full_move(migrated_db_path, "g1", ply=30, move_number=15,
                           is_player_move=1, cpl=200, classification="blunder")
        resp = api_client.get("/api/patterns/game-context")
        assert resp.status_code == 200
        body = resp.json()
        lookup = {r["phase"]: r for r in body["phase_accuracy"]}
        assert lookup["opening"]["acpl"] == pytest.approx(10.0)
        assert lookup["middlegame"]["acpl"] == pytest.approx(200.0)

    def test_day_hour_heatmap_cells_use_mon_sun_labels_and_signed_rating_display(
            self, api_client, migrated_db_path):
        conn = sqlite3.connect(migrated_db_path)
        rows = [
            ("g1", 0, 12, "win", 100),
            ("g2", 0, 12, "loss", -50),
            ("g3", 1, 18, "win", 300),
        ]
        for gid, dow, hour, outcome, rd in rows:
            conn.execute(
                "INSERT INTO games (id, white, black, outcome_for_player, "
                "day_of_week, hour_utc, rating_diff) VALUES (?, 'W', 'B', ?, ?, ?, ?)",
                [gid, outcome, dow, hour, rd])
        conn.commit()
        conn.close()

        resp = api_client.get("/api/patterns/game-context")
        body = resp.json()
        cells = {(c["day"], c["hour_local"]): c for c in body["day_hour_heatmap"]["cells"]}
        assert cells[("Mon", 12)]["win_pct"] == pytest.approx(50.0)
        assert cells[("Mon", 12)]["rating_diff_display"] == "+25"
        assert cells[("Tue", 18)]["win_pct"] == pytest.approx(100.0)
        assert cells[("Tue", 18)]["rating_diff_display"] == "+300"
        assert body["day_hour_heatmap"]["utc_offset_hours"] == 0

    def test_ttl_cache_reset_between_tests(self, api_client, migrated_db_path, monkeypatch):
        import data
        call_count = {"n": 0}
        real = data.get_phase_accuracy

        def _counting(*args, **kwargs):
            call_count["n"] += 1
            return real(*args, **kwargs)
        monkeypatch.setattr(data, "get_phase_accuracy", _counting)

        api_client.get("/api/patterns/game-context")
        api_client.get("/api/patterns/game-context")
        assert call_count["n"] == 1

        import api.main as api_main
        api_main.reset_caches()
        api_client.get("/api/patterns/game-context")
        assert call_count["n"] == 2

