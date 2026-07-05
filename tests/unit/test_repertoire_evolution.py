"""Unit tests for the time-sliced repertoire evolution logic
(dashboard/data/openings.py) — the Pro Opening Tree's "What Changed" scan
and Explorer timeline headline.

compute_dominant_move_flips / summarize_position_timeline are pure pandas
over synthetic frames; get_path_to_position gets a minimal in-memory moves
table with REAL zobrist hashes computed by replay, so the verify-by-replay
guard is exercised for genuine matches and genuine mismatches.
"""
import sqlite3

import chess
import pandas as pd
import pytest

from chess_utils import signed_zobrist
from data.openings import (
    compute_dominant_move_flips,
    get_path_to_position,
    summarize_position_timeline,
)

COLS = ["ply", "zobrist_hash", "san", "year", "n_games", "n_wins",
        "cpl_sum", "cpl_n", "fen_before"]


def _frame(rows):
    """rows: (ply, zobrist, san, year, n_games, n_wins, cpl_sum, cpl_n)."""
    return pd.DataFrame(
        [(*r, "fen-stub") for r in rows], columns=COLS)


@pytest.mark.unit
class TestComputeDominantMoveFlips:
    def test_detects_flip_with_correct_stats(self):
        stats = _frame([
            (3, 111, "d4", 2019, 10, 6, 300.0, 10),
            (3, 111, "c4", 2019, 2, 1, 80.0, 2),
            (3, 111, "c4", 2023, 8, 5, 160.0, 8),
            (3, 111, "d4", 2023, 1, 0, 50.0, 1),
        ])
        flips = compute_dominant_move_flips(stats, 2022, min_games_each_era=5)
        assert len(flips) == 1
        row = flips.iloc[0]
        assert (row["before_san"], row["after_san"]) == ("d4", "c4")
        assert row["before_total"] == 12 and row["after_total"] == 9
        assert row["before_n"] == 10 and row["after_n"] == 8
        assert row["before_win_pct"] == pytest.approx(60.0)
        assert row["after_win_pct"] == pytest.approx(62.5)
        assert row["before_share"] == pytest.approx(100.0 * 10 / 12)
        # weighted era CPL, not an average of per-year averages
        assert row["before_cpl"] == pytest.approx(30.0)
        assert row["after_cpl"] == pytest.approx(20.0)
        assert row["total_games"] == 21

    def test_no_flip_when_dominant_move_stable(self):
        stats = _frame([
            (3, 111, "d4", 2019, 10, 6, 300.0, 10),
            (3, 111, "c4", 2019, 3, 1, 80.0, 3),
            (3, 111, "d4", 2023, 9, 5, 200.0, 9),
            (3, 111, "c4", 2023, 4, 2, 90.0, 4),
        ])
        assert compute_dominant_move_flips(stats, 2022, 5).empty

    def test_era_floor_excludes_thin_eras(self):
        stats = _frame([
            (3, 111, "d4", 2019, 10, 6, 300.0, 10),
            (3, 111, "c4", 2023, 4, 3, 100.0, 4),  # after era: only 4 games
        ])
        assert compute_dominant_move_flips(stats, 2022, min_games_each_era=5).empty
        # loosening the floor lets the same data through
        assert len(compute_dominant_move_flips(stats, 2022, min_games_each_era=4)) == 1

    def test_single_era_position_excluded(self):
        stats = _frame([
            (3, 111, "d4", 2019, 10, 6, 300.0, 10),
            (3, 111, "c4", 2020, 8, 4, 200.0, 8),
        ])
        # every game is before the split — no "after" era at all
        assert compute_dominant_move_flips(stats, 2024, 5).empty

    def test_tiebreak_is_alphabetical_and_deterministic(self):
        stats = _frame([
            (3, 111, "e4", 2019, 6, 3, 100.0, 6),
            (3, 111, "d4", 2019, 6, 3, 100.0, 6),  # tie: d4 < e4 wins
            (3, 111, "Nf3", 2023, 7, 4, 100.0, 7),
        ])
        flips = compute_dominant_move_flips(stats, 2022, 5)
        assert len(flips) == 1
        assert flips.iloc[0]["before_san"] == "d4"

    def test_unanalyzed_cpl_is_nan_not_crash(self):
        stats = _frame([
            (3, 111, "d4", 2019, 10, 6, 0.0, 0),
            (3, 111, "c4", 2023, 8, 5, 0.0, 0),
        ])
        row = compute_dominant_move_flips(stats, 2022, 5).iloc[0]
        assert pd.isna(row["before_cpl"]) and pd.isna(row["after_cpl"])

    def test_empty_input_returns_empty_with_columns(self):
        out = compute_dominant_move_flips(_frame([]), 2022, 5)
        assert out.empty
        assert "before_san" in out.columns and "after_san" in out.columns

    def test_multiple_positions_sorted_by_total_games(self):
        stats = _frame([
            (3, 111, "d4", 2019, 10, 6, 100.0, 10),
            (3, 111, "c4", 2023, 8, 5, 100.0, 8),
            (5, 222, "g3", 2019, 50, 30, 100.0, 50),
            (5, 222, "Nc3", 2023, 40, 25, 100.0, 40),
        ])
        flips = compute_dominant_move_flips(stats, 2022, 5)
        assert list(flips["zobrist_hash"]) == [222, 111]


@pytest.mark.unit
class TestSummarizePositionTimeline:
    def _year_df(self, rows):
        """rows: (san, year, n_games, n_wins) — get_opening_moves_by_year shape."""
        return pd.DataFrame(
            [(san, year, 1, n, w, 0, n - w, 100.0 * n, n)
             for san, year, n, w in rows],
            columns=["san", "year", "is_player_move", "n_games", "n_wins",
                     "n_draws", "n_losses", "cpl_sum", "cpl_n"])

    def test_finds_switch_and_best_split(self):
        df = self._year_df([
            ("Bb5", 2019, 20, 12), ("Bc4", 2019, 2, 1),
            ("Bb5", 2020, 15, 8),
            ("Bc4", 2021, 18, 11), ("Bb5", 2021, 1, 0),
            ("Bc4", 2022, 12, 7),
        ])
        s = summarize_position_timeline(df, min_games_each_era=5)
        assert s is not None
        assert s["split_year"] == 2021  # the true boundary, not 2020 or 2022
        assert s["before_san"] == "Bb5" and s["after_san"] == "Bc4"
        assert s["before_total"] == 37 and s["after_total"] == 31

    def test_stable_repertoire_returns_none(self):
        df = self._year_df([
            ("Nf3", 2019, 30, 15), ("d4", 2019, 5, 2),
            ("Nf3", 2023, 25, 14), ("d4", 2023, 6, 3),
        ])
        assert summarize_position_timeline(df) is None

    def test_empty_returns_none(self):
        assert summarize_position_timeline(self._year_df([])) is None

    def test_thin_history_returns_none(self):
        df = self._year_df([("Bb5", 2019, 3, 2), ("Bc4", 2020, 3, 1)])
        assert summarize_position_timeline(df, min_games_each_era=5) is None


@pytest.mark.unit
class TestGetPathToPosition:
    def _db_with_game(self, sans, game_id="g1"):
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE moves (game_id TEXT, ply INTEGER, "
                     "san TEXT, zobrist_hash INTEGER)")
        board = chess.Board()
        for i, san in enumerate(sans, start=1):
            z = signed_zobrist(board)  # position BEFORE the ply-i move
            conn.execute("INSERT INTO moves VALUES (?,?,?,?)",
                         (game_id, i, san, z))
            board.push_san(san)
        return conn

    def test_reconstructs_and_verifies_path(self):
        conn = self._db_with_game(["e4", "e5", "Nf3", "Nc6"])
        board = chess.Board()
        for san in ["e4", "e5"]:
            board.push_san(san)
        path = get_path_to_position(conn, signed_zobrist(board), 3)
        assert path == ["e4", "e5"]

    def test_unknown_position_returns_none(self):
        conn = self._db_with_game(["e4", "e5"])
        assert get_path_to_position(conn, 123456789, 3) is None

    def test_gap_in_stored_moves_returns_none(self):
        conn = self._db_with_game(["e4", "e5", "Nf3"])
        conn.execute("DELETE FROM moves WHERE ply = 1")
        board = chess.Board()
        for san in ["e4", "e5"]:
            board.push_san(san)
        assert get_path_to_position(conn, signed_zobrist(board), 3) is None

    def test_zobrist_mismatch_returns_none(self):
        conn = self._db_with_game(["e4", "e5", "Nf3"])
        # corrupt the stored history so replay lands on a different position
        conn.execute("UPDATE moves SET san = 'd5' WHERE ply = 2")
        board = chess.Board()
        for san in ["e4", "e5"]:
            board.push_san(san)
        assert get_path_to_position(conn, signed_zobrist(board), 3) is None
