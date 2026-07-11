"""
Integration tests for data/patterns.py's get_event_type_performance and
get_event_name_breakdown (roadmap §27b, 2026-07-11) -- the "Event Type
Breakdown" section appended to Playing Sessions: a Casual-vs-Tournament/
Arena 2-category summary classified purely from the ingested `event` PGN
field ("Rated <category> game" == casual, anything else == tournament/
arena), plus a named-tournament breakdown gated at a minimum game count.

Deliberately a NEW file, not added to tests/integration/test_data_layer.py --
mirrors tests/integration/test_material_structure.py's structure (same
_duck_from_conn helper, same migrated_db fixture, same sys.path header).
"""
import os
import pathlib
import sqlite3
import sys
import tempfile

import pandas as pd
import pytest

REPO_ROOT = pathlib.Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "dashboard"))


def _duck_from_conn(sqlite_conn):
    """Copy an in-memory/real sqlite connection to a temp file and attach
    it to a fresh DuckDB connection. Returns (duck_conn, disk_conn,
    tmp_path) -- callers must close both and delete the temp file. Mirrors
    tests/integration/test_material_structure.py's helper of the same
    name."""
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


def _seed_game(conn, game_id, event, outcome, cpl=None, classification=None):
    """One game, one moves row -- the single move (ply=1, is_player_move=1)
    doubles as the sole ACPL candidate for that game, same minimal-fixture
    shape as test_material_structure.py's _seed_game."""
    conn.execute(
        "INSERT INTO games (id, white, black, event, outcome_for_player, player_color) "
        "VALUES (?, 'W', 'B', ?, ?, 'white')",
        (game_id, event, outcome))
    conn.execute(
        "INSERT INTO moves (game_id, ply, move_number, color, san, is_player_move, "
        "cpl, classification) VALUES (?, 1, 1, 'w', 'e4', 1, ?, ?)",
        (game_id, cpl, classification))
    conn.commit()


@pytest.mark.integration
class TestGetEventTypePerformance:
    def test_on_empty_db(self, migrated_db):
        from data.patterns import get_event_type_performance
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            df = get_event_type_performance(duck)
            assert df.empty
            assert list(df.columns) == [
                "category", "n_games", "win_pct", "draw_pct", "loss_pct", "acpl", "n_analyzed"]
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def test_casual_vs_tournament_split(self, migrated_db):
        from data.patterns import get_event_type_performance
        # 2 casual games (win, loss), 2 tournament games (win, draw) --
        # deliberately different event NAMES within "casual" (blitz/bullet)
        # to prove the regex, not just a hardcoded string, is doing the
        # classifying.
        _seed_game(migrated_db, "c1", "Rated blitz game", "win", cpl=10, classification="good")
        _seed_game(migrated_db, "c2", "Rated bullet game", "loss")
        _seed_game(migrated_db, "t1", "Hourly SuperBlitz Arena", "win")
        _seed_game(migrated_db, "t2", "Hourly SuperBlitz Arena", "draw")

        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            df = get_event_type_performance(duck)
            assert len(df) == 2
            assert list(df.category) == ["Casual", "Tournament / Arena"]

            casual = df[df.category == "Casual"].iloc[0]
            assert casual.n_games == 2
            assert casual.win_pct == pytest.approx(50.0)
            assert casual.draw_pct == pytest.approx(0.0)
            assert casual.loss_pct == pytest.approx(50.0)
            # c1 has 1 analyzed move (cpl=10), c2 has none.
            assert casual.n_analyzed == 1
            assert casual.acpl == pytest.approx(10.0)

            tourney = df[df.category == "Tournament / Arena"].iloc[0]
            assert tourney.n_games == 2
            assert tourney.win_pct == pytest.approx(50.0)
            assert tourney.draw_pct == pytest.approx(50.0)
            assert tourney.loss_pct == pytest.approx(0.0)
            # Neither tournament game has an analyzed move -- ACPL must be
            # None (Convention #3), not a crash or a silent 0.
            assert tourney.n_analyzed == 0
            assert pd.isna(tourney.acpl)
        finally:
            duck.close(); disk.close(); os.unlink(tmp)


@pytest.mark.integration
class TestGetEventNameBreakdown:
    def test_on_empty_db(self, migrated_db):
        from data.patterns import get_event_name_breakdown
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            df = get_event_name_breakdown(duck)
            assert df.empty
            assert list(df.columns) == [
                "event", "n_games", "win_pct", "draw_pct", "loss_pct", "acpl", "n_analyzed"]
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def test_no_tournament_games_returns_empty(self, migrated_db):
        """All-casual DB -- get_event_name_breakdown must return empty
        (not raise) since every row gets filtered out of the Tournament /
        Arena category before the min_games gate even applies."""
        from data.patterns import get_event_name_breakdown
        for i in range(30):
            _seed_game(migrated_db, f"c{i}", "Rated blitz game", "win")

        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            df = get_event_name_breakdown(duck, min_games=20)
            assert df.empty
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def test_min_games_gate_and_casual_exclusion_and_sort_order(self, migrated_db):
        from data.patterns import get_event_name_breakdown
        # "Hourly SuperBlitz Arena": 25 games -- clears a min_games=20 gate.
        for i in range(25):
            _seed_game(migrated_db, f"hsb{i}", "Hourly SuperBlitz Arena", "win")
        # "Rare Weekend Arena": only 5 games -- must be excluded by the gate.
        for i in range(5):
            _seed_game(migrated_db, f"rwa{i}", "Rare Weekend Arena", "loss")
        # 30 casual games sharing the same "Rated blitz game" event name --
        # would clear the min_games gate on count alone, but must never
        # appear here since it's Casual, not Tournament / Arena.
        for i in range(30):
            _seed_game(migrated_db, f"c{i}", "Rated blitz game", "win")
        # A second, smaller-count tournament event to verify descending sort.
        for i in range(22):
            _seed_game(migrated_db, f"drb{i}", "Daily Rapid Battle", "draw")

        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            df = get_event_name_breakdown(duck, min_games=20)
            assert "Rated blitz game" not in set(df.event)
            assert "Rare Weekend Arena" not in set(df.event)
            assert set(df.event) == {"Hourly SuperBlitz Arena", "Daily Rapid Battle"}
            # Sorted by n_games descending.
            assert list(df.event) == ["Hourly SuperBlitz Arena", "Daily Rapid Battle"]
            assert list(df.n_games) == [25, 22]

            hsb = df[df.event == "Hourly SuperBlitz Arena"].iloc[0]
            assert hsb.win_pct == pytest.approx(100.0)
            assert pd.isna(hsb.acpl)
            assert hsb.n_analyzed == 0
        finally:
            duck.close(); disk.close(); os.unlink(tmp)
