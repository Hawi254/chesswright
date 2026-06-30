"""
Integration tests for dashboard/data/*.py query functions.

Uses the populated_db fixture (in-memory SQLite + a temp file for DuckDB).
Each test class covers one domain module.
"""
import os
import pathlib
import sqlite3
import sys
import tempfile
import pytest

REPO_ROOT = pathlib.Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "dashboard"))


def _duck_from_conn(sqlite_conn):
    """
    Copy the in-memory SQLite connection to a temp file and attach it to
    a fresh DuckDB connection.  Returns (duck_conn, disk_conn, tmp_path)
    — callers must close all three and delete the temp file.
    """
    import duckdb
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    disk = sqlite3.connect(tmp.name)
    for line in sqlite_conn.iterdump():
        try:
            disk.execute(line)
        except Exception:
            pass
    disk.commit()
    duck = duckdb.connect(":memory:")
    duck.execute(f"ATTACH '{tmp.name}' AS db (TYPE SQLITE, READ_ONLY TRUE)")
    return duck, disk, tmp.name


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


@pytest.mark.integration
class TestOpeningsData:
    def test_get_openings_table_on_empty_db(self, migrated_db):
        from data.openings import get_openings_table
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            df = get_openings_table(duck, migrated_db, min_games=1)
            assert df is not None
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def test_get_most_repeated_positions_empty_is_safe(self, migrated_db):
        """Phase A bug fix: empty IN clause must not raise on a fresh DB."""
        from data.openings import get_most_repeated_positions
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            df = get_most_repeated_positions(duck, min_games=9999)
            assert df is not None
            assert len(df) == 0
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def test_get_most_repeated_positions_with_populated_db(self, populated_db):
        from data.openings import get_most_repeated_positions
        duck, disk, tmp = _duck_from_conn(populated_db)
        try:
            df = get_most_repeated_positions(duck, min_games=1)
            assert df is not None
        finally:
            duck.close(); disk.close(); os.unlink(tmp)


@pytest.mark.integration
class TestMatchupsData:
    def test_get_giant_killing_counts_on_empty_db(self, migrated_db):
        from data.matchups import get_giant_killing_counts
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            df = get_giant_killing_counts(duck)
            assert df is not None
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def test_get_comeback_collapse_counts_on_empty_db(self, migrated_db):
        from data.matchups import get_comeback_collapse_counts
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            result = get_comeback_collapse_counts(duck)
            assert result is not None
        finally:
            duck.close(); disk.close(); os.unlink(tmp)


@pytest.mark.integration
class TestTacticalData:
    def test_get_motif_breakdown_on_empty_db(self, migrated_db):
        from data.tactical import get_motif_breakdown
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            df = get_motif_breakdown(duck)
            assert df is not None
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def test_get_brilliant_candidates_on_empty_db(self, migrated_db):
        from data.tactical import get_brilliant_candidates
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            df = get_brilliant_candidates(duck)
            assert df is not None
        finally:
            duck.close(); disk.close(); os.unlink(tmp)


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


@pytest.mark.integration
class TestSharedHelpers:
    def test_bucket_acpl_blunder_rate_empty_df(self):
        import pandas as pd
        from data._shared import bucket_acpl_blunder_rate, TIME_PRESSURE_BUCKETS
        df = pd.DataFrame({"clock_fraction": [], "cpl": pd.Series([], dtype=float),
                           "classification": []})
        result = bucket_acpl_blunder_rate(df, "clock_fraction", TIME_PRESSURE_BUCKETS)
        assert len(result) == 0

    def test_bucket_acpl_blunder_rate_computes_correctly(self):
        import pandas as pd
        from data._shared import bucket_acpl_blunder_rate
        buckets = [("low", 0, 0.5), ("high", 0.5, 1.0)]
        df = pd.DataFrame({
            "val": [0.1, 0.2, 0.7, 0.8],
            "cpl": [10.0, 20.0, 50.0, 100.0],
            "classification": ["good", "inaccuracy", "mistake", "blunder"],
        })
        result = bucket_acpl_blunder_rate(df, "val", buckets)
        assert len(result) == 2
        low = result[result.bucket == "low"]
        high = result[result.bucket == "high"]
        assert low.iloc[0]["blunder_rate"] == 0.0
        assert high.iloc[0]["blunder_rate"] == 50.0


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
