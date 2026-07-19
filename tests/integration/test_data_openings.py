"""Integration tests for dashboard/data/openings.py -- split from
test_data_layer.py (TestOpeningsData, TestGetRepresentativePathForFamily,
plus the local _disk_from_conn/_insert_game/_insert_move helpers those two
classes use and no other destination file needs), see
docs/superpowers/specs/2026-07-17-test-suite-reorg-and-speedup-design.md.
"""
import os
import pathlib
import sqlite3
import sys
import tempfile

import pytest

from tests.conftest import _duck_from_conn

REPO_ROOT = pathlib.Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "dashboard"))


def _disk_from_conn(sqlite_conn):
    """
    Like _duck_from_conn but without the DuckDB attach -- for functions
    that open a second sqlite connection to the same database BY PATH
    (analytics' cache builders resolve it via PRAGMA database_list), which
    an in-memory fixture can't satisfy.  Returns (disk_conn, tmp_path) --
    caller must close the connection and delete the temp file.
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    disk = sqlite3.connect(tmp.name)
    for line in sqlite_conn.iterdump():
        try:
            disk.execute(line)
        except Exception:
            pass
    disk.commit()
    return disk, tmp.name


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

    def test_get_openings_table_uses_config_min_sample_size(self, migrated_db, monkeypatch):
        from data import openings as openings_module
        monkeypatch.setattr(
            openings_module.config, "load_config",
            lambda *a, **kw: {"analytics": {"min_sample_size": 1}})
        migrated_db.execute(
            "INSERT INTO games (id, white, black, outcome_for_player, "
            "opening_family, player_color) VALUES "
            "('g1', 'W', 'B', 'win', 'Sicilian', 'white')")
        migrated_db.commit()
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            df = openings_module.get_openings_table(duck, migrated_db)
            assert "Sicilian" in df.opening_family.values  # 1 game qualifies at min_sample_size=1
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def test_get_most_repeated_positions_empty_is_safe(self, migrated_db):
        """Phase A bug fix shape, preserved: a fresh DB must not raise.
        Takes sqlite_conn since the 2026-07-04 materialization -- reads
        repeated_positions_cache (created empty by migration 0030), so the
        in-memory migrated fixture can be queried directly."""
        from data.openings import get_most_repeated_positions
        df = get_most_repeated_positions(migrated_db, min_games=9999)
        assert df is not None
        assert len(df) == 0

    def test_get_most_repeated_positions_with_populated_db(self, populated_db):
        """Builds repeated_positions_cache first, the way the view layer's
        ensure_* call does. The cache builder opens a second connection to
        the same database BY PATH (analytics._open_write_connection), so
        the in-memory fixture must be dumped to a real file first."""
        from data.openings import get_most_repeated_positions
        import analytics
        disk, tmp = _disk_from_conn(populated_db)
        try:
            analytics.ensure_repeated_positions_cache(disk, min_games=1)
            df = get_most_repeated_positions(disk, min_games=1)
            assert df is not None
        finally:
            disk.close(); os.unlink(tmp)


def _insert_game(db_path, game_id, opening_family="Sicilian Defense", player_color="white"):
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO games (id, white, black, opening_family, player_color) "
        "VALUES (?, 'W', 'B', ?, ?)",
        [game_id, opening_family, player_color])
    conn.commit()
    conn.close()


def _insert_move(db_path, game_id, ply, san):
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO moves (game_id, ply, move_number, color, san) VALUES (?, ?, ?, ?, ?)",
        [game_id, ply, (ply + 1) // 2, "w" if ply % 2 == 1 else "b", san])
    conn.commit()
    conn.close()


@pytest.mark.integration
class TestGetRepresentativePathForFamily:
    def test_returns_most_common_path_among_family_games(self, migrated_db_path, migrated_db):
        from data.openings import get_representative_path_for_family
        _insert_game(migrated_db_path, "g1", opening_family="Sicilian Defense", player_color="white")
        _insert_game(migrated_db_path, "g2", opening_family="Sicilian Defense", player_color="white")
        _insert_game(migrated_db_path, "g3", opening_family="Sicilian Defense", player_color="white")
        for gid in ("g1", "g2"):
            _insert_move(migrated_db_path, gid, 1, "e4")
            _insert_move(migrated_db_path, gid, 2, "c5")
        _insert_move(migrated_db_path, "g3", 1, "e4")
        _insert_move(migrated_db_path, "g3", 2, "e6")  # minority path

        path = get_representative_path_for_family(migrated_db, "Sicilian Defense", "w")

        assert path == ["e4", "c5"]

    def test_returns_none_when_no_games_match_color(self, migrated_db_path, migrated_db):
        from data.openings import get_representative_path_for_family
        _insert_game(migrated_db_path, "g1", opening_family="Sicilian Defense", player_color="black")
        _insert_move(migrated_db_path, "g1", 1, "e4")

        assert get_representative_path_for_family(migrated_db, "Sicilian Defense", "w") is None

    def test_returns_none_when_family_unknown(self, migrated_db):
        from data.openings import get_representative_path_for_family
        assert get_representative_path_for_family(migrated_db, "Not A Real Opening", "w") is None


