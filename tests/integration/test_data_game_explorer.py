"""Integration tests for dashboard/data/game_explorer.py -- split from
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
class TestGameExplorerData:
    def test_get_game_explorer_table_on_empty_db(self, migrated_db):
        from data.game_explorer import get_game_explorer_table
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            df = get_game_explorer_table(duck)
            assert df.empty
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def test_get_game_explorer_table_includes_analysis_status(self, migrated_db):
        """analysis_status must survive the header/badge merge -- 4 of the
        5 badges (everything but giant_killing) need engine analysis, so
        badge_count=0 doesn't distinguish "boring" from "never analyzed"
        without this column (see get_game_explorer_table's docstring)."""
        from data.game_explorer import get_game_explorer_table
        migrated_db.execute(
            "INSERT INTO games (id, white, black, analysis_status) "
            "VALUES ('g_done', 'a', 'b', 'done')")
        migrated_db.execute(
            "INSERT INTO games (id, white, black, analysis_status) "
            "VALUES ('g_pending', 'a', 'b', 'pending')")
        migrated_db.commit()
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            df = get_game_explorer_table(duck)
            status = dict(zip(df.game_id, df.analysis_status))
            assert status["g_done"] == "done"
            assert status["g_pending"] == "pending"
        finally:
            duck.close(); disk.close(); os.unlink(tmp)


