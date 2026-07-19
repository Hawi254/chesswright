"""Integration tests for dashboard/data/prep.py -- split from
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
class TestOpponentPrepData:
    def test_get_repertoire_on_empty_db(self, migrated_db):
        from data.prep import get_repertoire
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            df = get_repertoire(duck)
            assert df.empty
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def test_get_repertoire_n_games_and_score_pct_not_move_count_weighted(self, migrated_db):
        """Same regression this file's old get_recent_form test guarded:
        three games, same opponent color/opening, DELIBERATELY different
        move counts (1, 3, 2) so n_games/score_pct only come out right if
        the merge aggregates games and moves at separate grains before
        combining -- see get_repertoire's docstring for the exact bug
        this prevents (295 "games" for 11 real games, found live)."""
        from data.prep import get_repertoire
        conn = migrated_db
        conn.execute(
            "INSERT INTO games (id, white, black, player_color, opening_family, "
            "outcome_for_player, analysis_status) VALUES "
            "('g1','W','B','white','Italian Game','win','done')")
        conn.execute(
            "INSERT INTO moves (game_id, ply, move_number, color, san, "
            "is_player_move, cpl) VALUES ('g1', 1, 1, 'w', 'e4', 1, 10)")

        conn.execute(
            "INSERT INTO games (id, white, black, player_color, opening_family, "
            "outcome_for_player, analysis_status) VALUES "
            "('g2','W','B','white','Italian Game','loss','done')")
        for ply, cpl in [(1, 20), (3, 30), (5, 40)]:
            conn.execute(
                "INSERT INTO moves (game_id, ply, move_number, color, san, "
                "is_player_move, cpl) VALUES ('g2', ?, ?, 'w', 'e4', 1, ?)",
                (ply, (ply + 1) // 2, cpl))

        conn.execute(
            "INSERT INTO games (id, white, black, player_color, opening_family, "
            "outcome_for_player, analysis_status) VALUES "
            "('g3','W','B','white','Italian Game','win','done')")
        for ply, cpl in [(1, 5), (3, 15)]:
            conn.execute(
                "INSERT INTO moves (game_id, ply, move_number, color, san, "
                "is_player_move, cpl) VALUES ('g3', ?, ?, 'w', 'e4', 1, ?)",
                (ply, (ply + 1) // 2, cpl))
        conn.commit()

        duck, disk, tmp = _duck_from_conn(conn)
        try:
            df = get_repertoire(duck)
            assert len(df) == 1
            row = df.iloc[0]
            assert row.n_games == 3
            assert row.score_pct == pytest.approx(66.7, abs=0.05)
            assert row.avg_cpl == pytest.approx(20.0, abs=0.05)
            assert row.blunder_pct == 0.0
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def test_get_repertoire_blunder_pct(self, migrated_db):
        """blunder_pct is blunder-classified player moves / total analysed
        player moves in that (opening, color) group -- independently
        verifiable against get_repertoire's own NULLIF-guarded formula."""
        from data.prep import get_repertoire
        conn = migrated_db
        for gid in ("g1", "g2", "g3"):
            conn.execute(
                "INSERT INTO games (id, white, black, player_color, opening_family, "
                "outcome_for_player, analysis_status) VALUES "
                f"('{gid}','W','B','black','Sicilian Defense','loss','done')")
        classifications = ["blunder", "mistake", "blunder", "good", "good", "good"]
        i = 0
        for gid in ("g1", "g2", "g3"):
            for _ in range(2):
                conn.execute(
                    "INSERT INTO moves (game_id, ply, move_number, color, san, "
                    "is_player_move, cpl, classification) VALUES (?, ?, ?, 'b', 'e5', 1, 10, ?)",
                    (gid, i + 1, (i + 2) // 2, classifications[i]))
                i += 1
        conn.commit()

        duck, disk, tmp = _duck_from_conn(conn)
        try:
            df = get_repertoire(duck)
            row = df.iloc[0]
            # 2 blunders / 6 total player moves = 33.3%
            assert row.blunder_pct == pytest.approx(33.3, abs=0.05)
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def test_get_scout_summary_on_empty_db(self, migrated_db):
        from data.prep import get_scout_summary
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            summary = get_scout_summary(duck)
            assert summary == {
                "games_analyzed": 0,
                "color_split": {"white": 0, "black": 0},
                "date_range": {"from": None, "to": None},
            }
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def test_get_scout_summary_counts_and_date_range(self, migrated_db):
        from data.prep import get_scout_summary
        conn = migrated_db
        conn.execute(
            "INSERT INTO games (id, white, black, player_color, analysis_status, utc_date) "
            "VALUES ('g1','W','B','white','done','2026-01-01')")
        conn.execute(
            "INSERT INTO games (id, white, black, player_color, analysis_status, utc_date) "
            "VALUES ('g2','W','B','black','done','2026-03-15')")
        conn.execute(
            "INSERT INTO games (id, white, black, player_color, analysis_status, utc_date) "
            "VALUES ('g3','W','B','white','pending','2026-06-01')")
        conn.commit()
        duck, disk, tmp = _duck_from_conn(conn)
        try:
            summary = get_scout_summary(duck)
            assert summary == {
                "games_analyzed": 2,
                "color_split": {"white": 1, "black": 1},
                "date_range": {"from": "2026-01-01", "to": "2026-03-15"},
            }
        finally:
            duck.close(); disk.close(); os.unlink(tmp)


@pytest.mark.integration
class TestListScoutedOpponents:
    def test_empty_when_no_opponents_dir(self, tmp_path):
        from data.prep import list_scouted_opponents
        main_db = tmp_path / "chess.db"
        main_db.touch()
        assert list_scouted_opponents(str(main_db)) == []

    def test_lists_only_dirs_with_games_db(self, tmp_path):
        from data.prep import list_scouted_opponents
        main_db = tmp_path / "chess.db"
        main_db.touch()
        opponents_dir = tmp_path / "opponents"
        (opponents_dir / "alice").mkdir(parents=True)
        (opponents_dir / "alice" / "games.db").touch()
        (opponents_dir / "bob_incomplete").mkdir(parents=True)  # no games.db yet
        assert list_scouted_opponents(str(main_db)) == ["alice"]


