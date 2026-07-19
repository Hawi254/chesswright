"""Tests for the new single-position annotation lookups added in
Game Detail Slice 4. See
docs/superpowers/specs/2026-07-14-game-detail-slice4-annotations-design.md.
"""
import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
DASHBOARD_DIR = REPO_ROOT / "dashboard"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(DASHBOARD_DIR))

STARTING_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


@pytest.mark.integration
class TestGetVariationAnnotation:
    def test_returns_none_when_unannotated(self, migrated_db):
        from data.variations import save_variation, get_variation_annotation
        migrated_db.execute(
            "INSERT INTO games (id, white, black) VALUES ('g1', 'W', 'B')")
        migrated_db.commit()
        vid = save_variation(migrated_db, "g1", 0, STARTING_FEN, ["e2e4"])
        assert get_variation_annotation(migrated_db, vid, 1) is None

    def test_returns_the_annotation_for_that_move_index_only(self, migrated_db):
        from data.variations import (
            save_variation, upsert_annotation, get_variation_annotation,
        )
        migrated_db.execute(
            "INSERT INTO games (id, white, black) VALUES ('g1', 'W', 'B')")
        migrated_db.commit()
        vid = save_variation(migrated_db, "g1", 0, STARTING_FEN, ["e2e4", "e7e5"])
        upsert_annotation(migrated_db, vid, 1, glyph="!", comment="Good move")
        upsert_annotation(migrated_db, vid, 2, glyph="?")

        found = get_variation_annotation(migrated_db, vid, 1)
        assert found is not None
        assert found.glyph == "!"
        assert found.comment == "Good move"
        assert found.variation_id == vid
        assert found.game_id is None

        other = get_variation_annotation(migrated_db, vid, 2)
        assert other.glyph == "?"


@pytest.mark.integration
class TestGameAnnotations:
    def test_upsert_then_get_single(self, migrated_db):
        from data.annotations import upsert_game_annotation, get_game_annotation
        migrated_db.execute(
            "INSERT INTO games (id, white, black) VALUES ('g2', 'W', 'B')")
        migrated_db.commit()
        upsert_game_annotation(migrated_db, "g2", 4, glyph="!!", comment="Nice shot")

        found = get_game_annotation(migrated_db, "g2", 4)
        assert found is not None
        assert found.glyph == "!!"
        assert found.comment == "Nice shot"
        assert found.game_id == "g2"
        assert found.variation_id is None
        assert found.move_index == 4

    def test_get_single_returns_none_when_unannotated(self, migrated_db):
        from data.annotations import get_game_annotation
        migrated_db.execute(
            "INSERT INTO games (id, white, black) VALUES ('g2', 'W', 'B')")
        migrated_db.commit()
        assert get_game_annotation(migrated_db, "g2", 4) is None

    def test_get_all_returns_dict_keyed_by_ply(self, migrated_db):
        from data.annotations import upsert_game_annotation, get_game_annotations
        migrated_db.execute(
            "INSERT INTO games (id, white, black) VALUES ('g2', 'W', 'B')")
        migrated_db.commit()
        upsert_game_annotation(migrated_db, "g2", 2, glyph="!")
        upsert_game_annotation(migrated_db, "g2", 4, glyph="?")

        all_ann = get_game_annotations(migrated_db, "g2")
        assert set(all_ann.keys()) == {2, 4}
        assert all_ann[2].glyph == "!"
        assert all_ann[4].glyph == "?"

    def test_upsert_only_overwrites_supplied_fields(self, migrated_db):
        from data.annotations import upsert_game_annotation, get_game_annotation
        migrated_db.execute(
            "INSERT INTO games (id, white, black) VALUES ('g2', 'W', 'B')")
        migrated_db.commit()
        upsert_game_annotation(migrated_db, "g2", 4, glyph="!", comment="First note")
        upsert_game_annotation(migrated_db, "g2", 4, ai_comment="Claude says hi", ai_model="claude-sonnet-4-6")

        found = get_game_annotation(migrated_db, "g2", 4)
        assert found.glyph == "!"
        assert found.comment == "First note"
        assert found.ai_comment == "Claude says hi"
        assert found.ai_model == "claude-sonnet-4-6"
        assert found.generated_at is not None

    def test_upsert_is_scoped_to_game_id(self, migrated_db):
        from data.annotations import upsert_game_annotation, get_game_annotation
        migrated_db.execute(
            "INSERT INTO games (id, white, black) VALUES ('g3', 'W', 'B'), ('g4', 'W', 'B')")
        migrated_db.commit()
        upsert_game_annotation(migrated_db, "g3", 4, glyph="!")
        assert get_game_annotation(migrated_db, "g4", 4) is None
