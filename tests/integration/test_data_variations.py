"""Integration tests for dashboard/data/variations.py -- split from
test_data_layer.py, see
docs/superpowers/specs/2026-07-17-test-suite-reorg-and-speedup-design.md.
"""
import os
import pathlib
import sqlite3
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "dashboard"))


@pytest.mark.integration
class TestVariationsData:
    def test_save_list_roundtrip(self, migrated_db):
        from data.variations import save_variation, list_variations
        STARTING_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
        migrated_db.execute(
            "INSERT INTO games (id, white, black) VALUES ('gtest1', 'W', 'B')")
        migrated_db.commit()
        vid = save_variation(migrated_db, "gtest1", 0, STARTING_FEN, ["e2e4"])
        rows = list_variations(migrated_db, "gtest1")
        assert len(rows) == 1
        assert rows[0].moves == ["e2e4"]

    def test_delete_cascades_annotations(self, migrated_db):
        from data.variations import save_variation, delete_variation
        from data.variations import upsert_annotation, get_variation_annotations
        STARTING_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
        migrated_db.execute(
            "INSERT INTO games (id, white, black) VALUES ('gtest2', 'W', 'B')")
        migrated_db.commit()
        vid = save_variation(migrated_db, "gtest2", 0, STARTING_FEN, ["e2e4"])
        upsert_annotation(migrated_db, vid, 1, glyph="!")
        delete_variation(migrated_db, vid)
        assert len(get_variation_annotations(migrated_db, vid)) == 0


