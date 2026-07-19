"""Integration tests for dashboard/data's DB-import helpers -- split from
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
class TestDbImport:
    def test_validate_source_rejects_incompatible_games_table(self, tmp_path):
        import db_import
        bad_db = tmp_path / "bad.db"
        conn = sqlite3.connect(str(bad_db))
        conn.execute("CREATE TABLE games (id TEXT, unrelated TEXT)")
        conn.commit()
        conn.close()
        with pytest.raises(db_import.DatabaseImportError):
            db_import.validate_source(bad_db)

    def test_validate_source_accepts_compatible_db(self, tmp_path):
        import db_import
        good_db = tmp_path / "good.db"
        conn = sqlite3.connect(str(good_db))
        # Must include all REQUIRED_GAMES_COLUMNS
        conn.execute("""
            CREATE TABLE games (
                id TEXT PRIMARY KEY,
                white TEXT,
                black TEXT,
                result TEXT,
                analysis_status TEXT
            )
        """)
        conn.commit()
        conn.close()
        db_import.validate_source(good_db)  # should not raise

    def test_validate_source_rejects_non_sqlite_file(self, tmp_path):
        import db_import
        bad_file = tmp_path / "not_a_db.txt"
        bad_file.write_text("this is not sqlite")
        with pytest.raises(db_import.DatabaseImportError):
            db_import.validate_source(bad_file)


