"""Integration tests for the Patterns & Tendencies clock-time endpoint --
split from test_api_patterns.py, see
docs/superpowers/specs/2026-07-17-test-suite-reorg-and-speedup-design.md.
"""
import pathlib
import sqlite3
import sys

import pytest

from tests.conftest import _insert_game, _insert_move

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
DASHBOARD_DIR = REPO_ROOT / "dashboard"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(DASHBOARD_DIR))


@pytest.mark.integration
class TestPatternsClockTime:
    def test_empty_db_returns_zero_filled_shape(self, api_client):
        resp = api_client.get("/api/patterns/clock-time")
        assert resp.status_code == 200
        body = resp.json()
        assert body["blunder_rate_by_time_pressure"] == []
        assert body["acpl_by_time_control"] == []
        assert body["thinking_time_blunder_correlation"] == []
        assert body["instant_move_rate_by_phase"] == []
        assert body["instant_move_accuracy"] == {
            "rows": [], "n_analyzed": 0, "n_total_in_scope": 0,
        }

    def test_bundles_real_data_across_all_five_queries(self, api_client, migrated_db_path):
        _insert_game(migrated_db_path, "g1", base_seconds=180, time_control_category="blitz")
        _insert_game(migrated_db_path, "g2", base_seconds=600, time_control_category="rapid")
        # plenty clock (170/180=94%), "considered" thinking time, opening ply
        _insert_move(migrated_db_path, "g1", ply=5, cpl=20, classification="good",
                     clock_seconds=170, time_spent_seconds=5)
        # critical clock (5/180=2.8%), instant move, late-middlegame ply,
        # forced-ish (3 legal replies, config's instant_move_low_legal_replies)
        _insert_move(migrated_db_path, "g1", ply=45, cpl=150, classification="blunder",
                     clock_seconds=5, time_spent_seconds=0, legal_reply_count=3)
        # plenty clock (590/600=98%), "quick" thinking time, opening ply
        _insert_move(migrated_db_path, "g2", ply=3, cpl=10, classification="good",
                     clock_seconds=590, time_spent_seconds=2)

        resp = api_client.get("/api/patterns/clock-time")
        assert resp.status_code == 200
        body = resp.json()

        tp_buckets = {r["bucket"]: r for r in body["blunder_rate_by_time_pressure"]}
        assert tp_buckets["critical (<5%)"]["n_moves"] == 1
        assert tp_buckets["critical (<5%)"]["blunder_rate"] == 100.0
        assert tp_buckets["plenty (60-100%)"]["n_moves"] == 2
        assert tp_buckets["plenty (60-100%)"]["blunder_rate"] == 0.0

        tc_rows = {r["time_control"]: r for r in body["acpl_by_time_control"]}
        assert tc_rows["blitz"]["n_games"] == 1
        assert tc_rows["blitz"]["n_moves"] == 2
        assert tc_rows["blitz"]["acpl"] == 85.0
        assert tc_rows["rapid"]["n_moves"] == 1

        think_buckets = {r["bucket"] for r in body["thinking_time_blunder_correlation"]}
        assert "instant (<1s)" in think_buckets
        assert "quick (1-3s)" in think_buckets
        assert "considered (3-10s)" in think_buckets

        phase_buckets = {r["bucket"]: r for r in body["instant_move_rate_by_phase"]}
        assert phase_buckets["opening (1-10)"]["n_moves"] == 2
        assert phase_buckets["opening (1-10)"]["n_instant"] == 0
        assert phase_buckets["late middlegame (31-60)"]["n_instant"] == 1

        accuracy = body["instant_move_accuracy"]
        assert accuracy["n_analyzed"] == 1
        assert accuracy["n_total_in_scope"] == 1
        assert accuracy["rows"][0]["bucket"] == "forced-ish (≤3 legal replies)"

    def test_ttl_cache_reset_between_tests(self, api_client, migrated_db_path, monkeypatch):
        import data
        call_count = {"n": 0}
        real = data.get_blunder_rate_by_time_pressure

        def _counting(*args, **kwargs):
            call_count["n"] += 1
            return real(*args, **kwargs)
        monkeypatch.setattr(data, "get_blunder_rate_by_time_pressure", _counting)

        api_client.get("/api/patterns/clock-time")
        api_client.get("/api/patterns/clock-time")
        assert call_count["n"] == 1  # second call served from _patterns_clock_time_cache

        import api.main as api_main
        api_main.reset_caches()
        api_client.get("/api/patterns/clock-time")
        assert call_count["n"] == 2


