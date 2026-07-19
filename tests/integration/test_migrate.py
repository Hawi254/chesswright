"""Integration tests for migrate.py — DB schema correctness and idempotency."""
import pathlib
import sqlite3
import pytest

from migrate import migrate

REPO_ROOT = pathlib.Path(__file__).parent.parent.parent


@pytest.mark.integration
class TestMigrationApplies:
    def test_all_migrations_run_cleanly(self, tmp_path):
        db_path = str(tmp_path / "fresh.db")
        migrate(db_path)

    def test_idempotent_on_second_run(self, tmp_path):
        """Running migrate() twice must not raise (schema_migrations prevents re-runs)."""
        db_path = str(tmp_path / "idem.db")
        migrate(db_path)
        migrate(db_path)  # should print "Nothing to do" and return cleanly

    def test_games_table_exists(self, migrated_db):
        tables = {r[0] for r in migrated_db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert "games" in tables

    def test_moves_table_exists(self, migrated_db):
        tables = {r[0] for r in migrated_db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert "moves" in tables

    def test_all_expected_tables_exist(self, migrated_db):
        required = {
            "games", "moves", "analysis_runs", "claude_narratives",
            "position_cache", "variations", "variation_annotations",
            "structure_ctx_cache", "session_ctx_cache", "ctx_cache_meta",
            "ai_coach_profile", "ai_coach_conversations", "ai_coach_turns",
        }
        tables = {r[0] for r in migrated_db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        missing = required - tables
        assert not missing, f"Missing tables after migration: {missing}"

    def test_schema_migrations_table_records_all_applied(self, migrated_db_path):
        conn = sqlite3.connect(migrated_db_path)
        n_recorded = conn.execute(
            "SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
        n_files = len(list((REPO_ROOT / "migrations").glob("*.sql")))
        conn.close()
        assert n_recorded == n_files, \
            f"schema_migrations has {n_recorded} entries, expected {n_files}"


@pytest.mark.integration
class TestSchemaColumns:
    def test_moves_has_motif_column(self, migrated_db):
        cols = {r[1] for r in migrated_db.execute("PRAGMA table_info(moves)").fetchall()}
        assert "motif" in cols

    def test_moves_has_is_player_move(self, migrated_db):
        cols = {r[1] for r in migrated_db.execute("PRAGMA table_info(moves)").fetchall()}
        assert "is_player_move" in cols

    def test_position_cache_keyed_on_fen(self, migrated_db):
        cols = {r[1] for r in migrated_db.execute("PRAGMA table_info(position_cache)").fetchall()}
        assert "fen_before" in cols

    def test_variations_has_cascade_fk(self, migrated_db):
        sql = migrated_db.execute(
            "SELECT sql FROM sqlite_master WHERE name='variation_annotations'").fetchone()[0]
        assert "ON DELETE CASCADE" in sql

    def test_games_queue_index_exists(self, migrated_db):
        indexes = {r[1] for r in migrated_db.execute(
            "SELECT * FROM sqlite_master WHERE type='index'").fetchall()}
        assert any("queue" in idx for idx in indexes)


@pytest.mark.integration
class TestForeignKeyEnforcement:
    def test_move_fk_to_game_enforced(self, migrated_db):
        migrated_db.execute("PRAGMA foreign_keys = ON")
        with pytest.raises(Exception):
            migrated_db.execute("""
                INSERT INTO moves (game_id, ply, move_number, color, san)
                VALUES ('nonexistent_game', 1, 1, 'w', 'e4')
            """)
            migrated_db.commit()

    def test_variation_annotation_cascade_delete(self, migrated_db):
        migrated_db.execute("PRAGMA foreign_keys = ON")
        migrated_db.execute(
            "INSERT INTO games (id, white, black) VALUES ('gtest', 'W', 'B')")
        migrated_db.execute("""
            INSERT INTO variations (id, game_id, branch_ply, branch_fen, moves_json)
            VALUES ('vid1', 'gtest', 0, 'startpos', '[]')
        """)
        migrated_db.execute("""
            INSERT INTO variation_annotations (id, variation_id, move_index)
            VALUES ('ann1', 'vid1', 0)
        """)
        migrated_db.commit()
        migrated_db.execute("DELETE FROM variations WHERE id='vid1'")
        migrated_db.commit()
        row = migrated_db.execute(
            "SELECT id FROM variation_annotations WHERE id='ann1'").fetchone()
        assert row is None, "Annotation should have been cascade-deleted"
