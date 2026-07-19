"""Integration tests for dashboard/data/evolution.py -- split from
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
class TestEvolutionData:
    def test_get_family_acpl_by_period_on_empty_db(self, migrated_db):
        from data.evolution import get_family_acpl_by_period
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            df = get_family_acpl_by_period(duck, "Test Opening", "white")
            assert df.empty
            assert list(df.columns) == [
                "label", "n_moves", "n_games", "acpl", "n_total_games", "coverage_pct"]
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def _seed_game(self, conn, game_id, year, month, n_analyzed_moves):
        conn.execute(
            "INSERT INTO games (id, white, black, opening_family, "
            "player_color, year, month) "
            "VALUES (?, 'a', 'b', 'Test Opening', 'white', ?, ?)",
            (game_id, year, month))
        for ply in range(1, n_analyzed_moves + 1):
            conn.execute("""
                INSERT INTO moves (game_id, ply, move_number, color, san,
                    is_player_move, cpl)
                VALUES (?, ?, ?, 'w', 'e4', 1, 10)
            """, (game_id, ply * 2 - 1, ply))
        conn.commit()

    def test_get_family_acpl_by_period_coverage_pct(self, migrated_db):
        """coverage_pct is n_games-with-analyzed-moves / n_total_games in
        that quarter for this family/color -- NOT the analyzed-move count
        itself, and NOT scoped to games with zero analysis (those don't
        appear in the moves-table scan at all but still count toward the
        quarter's total). Verified live on the real dev DB (2026-07-07):
        White's English Opening has quarters ranging from 0% to 76.3%
        analyzed coverage -- exactly the gap this column discloses."""
        from data.evolution import get_family_acpl_by_period
        # Q1 2024 (Jan-Mar): 2 total games, 1 analyzed (3 moves) -> 50%.
        self._seed_game(migrated_db, "g1", 2024, 2, n_analyzed_moves=3)
        migrated_db.execute(
            "INSERT INTO games (id, white, black, opening_family, "
            "player_color, year, month) "
            "VALUES ('g2', 'a', 'b', 'Test Opening', 'white', 2024, 2)")
        # Q2 2024 (Apr-Jun): 1 total game, fully analyzed (2 moves) -> 100%.
        self._seed_game(migrated_db, "g3", 2024, 5, n_analyzed_moves=2)
        migrated_db.commit()
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            df = get_family_acpl_by_period(
                duck, "Test Opening", "white", min_moves_per_quarter=1)
            by_label = df.set_index("label")
            assert by_label.loc["2024 Q1", "n_games"] == 1
            assert by_label.loc["2024 Q1", "n_total_games"] == 2
            assert by_label.loc["2024 Q1", "coverage_pct"] == pytest.approx(50.0)
            assert by_label.loc["2024 Q2", "n_total_games"] == 1
            assert by_label.loc["2024 Q2", "coverage_pct"] == pytest.approx(100.0)
        finally:
            duck.close(); disk.close(); os.unlink(tmp)


