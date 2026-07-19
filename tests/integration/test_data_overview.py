"""Integration tests for dashboard/data/overview.py -- split from
test_data_layer.py, see
docs/superpowers/specs/2026-07-17-test-suite-reorg-and-speedup-design.md.
"""
import os
import pathlib
import sqlite3
import sys

import pytest

from tests.conftest import _duck_from_conn

REPO_ROOT = pathlib.Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "dashboard"))


@pytest.mark.integration
class TestOverviewData:
    def test_get_progress_by_month_on_empty_db(self, migrated_db):
        from data.overview import get_progress_by_month
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            df = get_progress_by_month(duck)
            assert df is not None
            assert len(df) == 0
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def test_get_rating_trajectory_on_empty_db(self, migrated_db):
        from data.overview import get_rating_trajectory
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            df = get_rating_trajectory(duck)
            assert df is not None
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def test_get_rating_snapshot_on_empty_db(self, migrated_db):
        from data.overview import get_rating_snapshot
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            result = get_rating_snapshot(duck)
            assert result == {"current_rating": None, "peak_rating": None}
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def test_get_rating_snapshot_returns_most_recent_and_peak(self, migrated_db):
        migrated_db.execute(
            "INSERT INTO games (id, player_rating, utc_date, utc_time, outcome_for_player) "
            "VALUES ('g1', 1500, '2026.01.01', '10:00:00', 'win')")
        migrated_db.execute(
            "INSERT INTO games (id, player_rating, utc_date, utc_time, outcome_for_player) "
            "VALUES ('g2', 1650, '2026.03.01', '10:00:00', 'win')")
        migrated_db.execute(
            "INSERT INTO games (id, player_rating, utc_date, utc_time, outcome_for_player) "
            "VALUES ('g3', 1600, '2026.06.01', '10:00:00', 'loss')")
        migrated_db.commit()
        from data.overview import get_rating_snapshot
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            result = get_rating_snapshot(duck)
            assert result == {"current_rating": 1600, "peak_rating": 1650}
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def test_get_current_streak_on_empty_db(self, migrated_db):
        from data.overview import get_current_streak
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            result = get_current_streak(duck)
            assert result == {"outcome": None, "length": 0}
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def test_get_current_streak_counts_consecutive_same_outcome(self, migrated_db):
        rows = [
            ("g1", "win", "2026.01.01"),
            ("g2", "loss", "2026.01.02"),
            ("g3", "win", "2026.01.03"),
            ("g4", "win", "2026.01.04"),
            ("g5", "win", "2026.01.05"),
        ]
        for game_id, outcome, date in rows:
            migrated_db.execute(
                "INSERT INTO games (id, outcome_for_player, utc_date, utc_time) "
                "VALUES (?, ?, ?, '10:00:00')", (game_id, outcome, date))
        migrated_db.commit()
        from data.overview import get_current_streak
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            result = get_current_streak(duck)
            assert result == {"outcome": "win", "length": 3}
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def test_get_recent_form_returns_last_n_games_newest_first(self, migrated_db):
        rows = [
            ("g1", "win", "Alice", "2026.01.01", 8),
            ("g2", "loss", "Bob", "2026.01.02", -6),
            ("g3", "draw", "Carol", "2026.01.03", 1),
        ]
        for game_id, outcome, opponent, date, delta in rows:
            migrated_db.execute(
                "INSERT INTO games (id, outcome_for_player, opponent_name, utc_date, utc_time, "
                "player_rating_change) VALUES (?, ?, ?, ?, '10:00:00', ?)",
                (game_id, outcome, opponent, date, delta))
        migrated_db.commit()
        from data.overview import get_recent_form_snapshot
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            df = get_recent_form_snapshot(duck, n=2)
            assert len(df) == 2
            assert df.iloc[0]["opponent_name"] == "Carol"
            assert df.iloc[0]["player_rating_change"] == 1
            assert df.iloc[1]["opponent_name"] == "Bob"
        finally:
            duck.close(); disk.close(); os.unlink(tmp)


