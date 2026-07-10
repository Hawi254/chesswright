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


def _disk_from_conn(sqlite_conn):
    """
    Like _duck_from_conn but without the DuckDB attach -- for functions
    that open a second sqlite connection to the same database BY PATH
    (analytics' cache builders resolve it via PRAGMA database_list), which
    an in-memory fixture can't satisfy.  Returns (disk_conn, tmp_path) —
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
class TestGameEndingsData:
    def test_get_time_forfeit_loss_breakdown_on_empty_db(self, migrated_db):
        from data.game_endings import get_time_forfeit_loss_breakdown
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            material_df, scramble_df, trend_df = get_time_forfeit_loss_breakdown(duck)
            assert material_df.empty and scramble_df.empty and trend_df.empty
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def _seed_time_forfeit_game(self, conn, game_id, year, month, day,
                                 mover_color, material_sig, material_delta,
                                 player_color, opponent_clock):
        """mover_color: color ('w'/'b') that made the FINAL recorded move of
        the game -- inserted at the highest ply so get_time_forfeit_loss_
        breakdown's last_move CTE (ORDER BY ply DESC) picks up ITS
        material_sig/material_delta. The opponent's last clock reading, if
        any, is a LOWER-ply row -- it must not sit at the highest ply, or
        it would shadow the material row (whose material_sig would then be
        NULL) in that same CTE."""
        conn.execute(
            "INSERT INTO games (id, white, black, outcome_for_player, game_end_type, "
            "player_color, year, month, utc_date) VALUES (?, 'W', 'B', 'loss', "
            "'time_forfeit', ?, ?, ?, ?)",
            (game_id, player_color, year, month, f"{year}.{month:02d}.{day:02d}"))
        player_move_color = "w" if player_color == "white" else "b"
        opponent_move_color = "b" if player_color == "white" else "w"
        if opponent_clock is not None:
            conn.execute(
                "INSERT INTO moves (game_id, ply, move_number, color, san, clock_seconds, "
                "is_player_move) VALUES (?, 1, 1, ?, 'Nf3', ?, 0)",
                (game_id, opponent_move_color, opponent_clock))
        is_player = 1 if mover_color == player_move_color else 0
        conn.execute(
            "INSERT INTO moves (game_id, ply, move_number, color, san, material_sig, "
            "material_delta, is_player_move) VALUES (?, 2, 1, ?, 'e5', ?, ?, ?)",
            (game_id, mover_color, material_sig, material_delta, is_player))
        conn.commit()

    def test_get_time_forfeit_loss_breakdown_classifies_material_and_scramble(self, migrated_db):
        from data.game_endings import get_time_forfeit_loss_breakdown
        # White (the player) made the final recorded move in both games.
        # g1: ahead by a rook (+500), opponent had plenty of time
        # (one-sided). g2: level material, opponent also nearly out
        # (mutual scramble).
        self._seed_time_forfeit_game(
            migrated_db, "g1", 2025, 3, 1, mover_color="w",
            material_sig="R2P7vP7", material_delta=0,
            player_color="white", opponent_clock=90)
        self._seed_time_forfeit_game(
            migrated_db, "g2", 2025, 6, 1, mover_color="w",
            material_sig="P7vP7", material_delta=0,
            player_color="white", opponent_clock=5)
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            material_df, scramble_df, trend_df = get_time_forfeit_loss_breakdown(duck)
            material_lookup = dict(zip(material_df.bucket, material_df.n))
            assert material_lookup["ahead by 3+ points"] == 1
            assert material_lookup["roughly level"] == 1
            scramble_lookup = dict(zip(scramble_df.bucket, scramble_df.n))
            assert scramble_lookup["mutual scramble (opponent under 15s)"] == 1
            assert scramble_lookup["opponent comfortable (60s+)"] == 1
            assert trend_df["n_total"].sum() == 2
            # Q1 and Q2 2025 are non-adjacent quarters -- the zero-fill must
            # produce a Q2-only-empty row in between, not skip straight from
            # Q1 to Q2 with nothing.
            assert set(trend_df.label) >= {"2025 Q1", "2025 Q2"}
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def test_get_time_forfeit_loss_breakdown_black_player_orientation(self, migrated_db):
        """Black being ahead must read as 'ahead' from the player's own
        perspective, not White's -- the exact sign bug this classification
        would produce if player_color were ignored."""
        from data.game_endings import get_time_forfeit_loss_breakdown
        self._seed_time_forfeit_game(
            migrated_db, "g3", 2025, 1, 1, mover_color="b",
            material_sig="P7vR2P7", material_delta=0,
            player_color="black", opponent_clock=90)
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            material_df, _scramble_df, _trend_df = get_time_forfeit_loss_breakdown(duck)
            material_lookup = dict(zip(material_df.bucket, material_df.n))
            assert material_lookup["ahead by 3+ points"] == 1
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

    def test_get_nemesis_opponents_all_lichess_gate(self, migrated_db):
        """all_lichess must be 1 only when EVERY game vs an opponent is a
        lichess game -- it gates the Opponent Prep deep link, which scouts
        lichess usernames only (see get_nemesis_opponents' comment)."""
        from data.matchups import get_nemesis_opponents
        rows = [
            # ("all_lichess_foe": every game on lichess -> gate open)
            ("g1", "all_lichess_foe", "loss", "https://lichess.org/aaa"),
            ("g2", "all_lichess_foe", "loss", "https://lichess.org/bbb"),
            ("g3", "all_lichess_foe", "win",  "https://lichess.org/ccc"),
            # ("mixed_foe": one chess.com game -> gate closed even though
            #  the other two are lichess)
            ("g4", "mixed_foe", "loss", "https://lichess.org/ddd"),
            ("g5", "mixed_foe", "draw", "https://lichess.org/eee"),
            ("g6", "mixed_foe", "loss", "https://www.chess.com/game/live/123"),
        ]
        for gid, opp, outcome, site in rows:
            migrated_db.execute(
                "INSERT INTO games (id, white, black, opponent_name, "
                "outcome_for_player, site) VALUES (?, 'W', 'B', ?, ?, ?)",
                (gid, opp, outcome, site))
        migrated_db.commit()
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            df = get_nemesis_opponents(duck, min_games=3)
            gate = dict(zip(df.opponent_name, df.all_lichess))
            assert gate["all_lichess_foe"] == 1
            assert gate["mixed_foe"] == 0
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def test_get_nemesis_opponents_surprise_index(self, migrated_db):
        """expected_score_pct is the average per-game Elo-predicted score
        (logistic, 400-point scale) for rating_diff, NOT the score implied
        by the opponent's average rating_diff -- those differ once
        per-game gaps vary (Jensen's inequality), so this seeds two
        DIFFERENT rating_diff values averaging to the same mean and checks
        against the per-game hand-computed expectation, not a single
        plugged-in average."""
        import math
        from data.matchups import get_nemesis_opponents
        # rating_diff +100 and +300 (avg +200) -- three total games, all
        # losses, to stay above min_games=3.
        rows = [("g1", 100), ("g2", 300), ("g3", 200)]
        for gid, rd in rows:
            migrated_db.execute(
                "INSERT INTO games (id, white, black, opponent_name, "
                "outcome_for_player, rating_diff) VALUES (?, 'W', 'B', 'Foe', 'loss', ?)",
                (gid, rd))
        migrated_db.commit()
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            df = get_nemesis_opponents(duck, min_games=3)
            row = df[df.opponent_name == "Foe"].iloc[0]
            expected_frac = sum(1.0 / (1.0 + 10 ** (-rd / 400.0)) for _, rd in rows) / len(rows)
            assert row.score_pct == 0.0
            assert row.expected_score_pct == pytest.approx(100.0 * expected_frac)
            assert row.surprise_pct == pytest.approx(0.0 - 100.0 * expected_frac)
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def test_get_giant_killing_collapse_causes_on_empty_db(self, migrated_db):
        from data.matchups import get_giant_killing_collapse_causes
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            reason_df, piece_df, mate_df = get_giant_killing_collapse_causes(duck)
            assert reason_df.empty and piece_df.empty and mate_df.empty
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def _seed_collapse_game(self, conn, game_id, num_plies, moves, rating_diff=300):
        """moves: list of dicts, one per ply, color/is_player_move derived
        the same way TestPointsData._seed_causes_game does (player is
        White). num_plies drives the "near the end" window
        (hallucination_max_moves_to_resign*2 plies, default 6)."""
        conn.execute(
            "INSERT INTO games (id, white, black, outcome_for_player, "
            "rating_diff, num_plies) VALUES (?, 'W', 'B', 'loss', ?, ?)",
            (game_id, rating_diff, num_plies))
        for mv in moves:
            ply = mv["ply"]
            color = "w" if ply % 2 == 1 else "b"
            is_player_move = mv.get("is_player_move", 1 if color == "w" else 0)
            conn.execute("""
                INSERT INTO moves (game_id, ply, move_number, color, san,
                    is_player_move, classification, cpl, eval_cp, eval_mate,
                    clock_seconds, is_capture, material_delta, to_square, piece)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (game_id, ply, (ply + 1) // 2, color, mv.get("san", "e4"),
                  is_player_move, mv.get("classification"), mv.get("cpl"),
                  mv.get("eval_cp"), mv.get("eval_mate"), mv.get("clock_seconds"),
                  mv.get("is_capture", 0), mv.get("material_delta"), mv.get("to_square"),
                  mv.get("piece")))
        conn.commit()

    def test_get_giant_killing_collapse_causes_classifies_reasons(self, migrated_db):
        from data.matchups import get_giant_killing_collapse_causes
        # num_plies=10, window=6 plies -> ply>=4 counts as "near the end".
        self._seed_collapse_game(migrated_db, "gk_hang", 10, [
            {"ply": 7, "classification": "blunder", "cpl": 250,
             "san": "Qe5", "piece": "Q", "to_square": "e5"},
            {"ply": 8, "is_player_move": 0, "is_capture": 1, "to_square": "e5",
             "material_delta": 900, "san": "Rxe5"},
        ])
        self._seed_collapse_game(migrated_db, "gk_mate", 10, [
            {"ply": 7, "eval_mate": -4, "san": "Nf3"},
        ])
        self._seed_collapse_game(migrated_db, "gk_timepressure", 10, [
            {"ply": 7, "clock_seconds": 10},
            {"ply": 8, "is_player_move": 0, "clock_seconds": 90},
        ])
        self._seed_collapse_game(migrated_db, "gk_other", 10, [
            {"ply": 3, "eval_cp": 50, "cpl": 10, "classification": "good"},
        ])
        self._seed_collapse_game(migrated_db, "gk_not_analyzed", 10, [
            {"ply": 3, "san": "Nf3"},
        ])
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            reason_df, piece_df, mate_df = get_giant_killing_collapse_causes(duck)
            reason_lookup = dict(zip(reason_df.reason, reason_df.n))
            assert reason_lookup["hung_piece"] == 1
            assert reason_lookup["faced_mate"] == 1
            assert reason_lookup["time_pressure"] == 1
            assert reason_lookup["other"] == 1
            assert reason_lookup["not_analyzed"] == 1
            assert dict(zip(piece_df.hung_piece, piece_df.n)) == {"Q": 1}
            assert mate_df.iloc[0]["bucket"] == "Mate in 3-5"  # eval_mate=-4
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def test_get_giant_killing_collapse_causes_hang_beats_faced_mate(self, migrated_db):
        """Same priority order as get_resignation_loss_causes: hung_piece
        wins over faced_mate when both signals qualify."""
        from data.matchups import get_giant_killing_collapse_causes
        self._seed_collapse_game(migrated_db, "gk_priority", 10, [
            {"ply": 5, "eval_mate": -4, "san": "Nf3"},
            {"ply": 7, "classification": "blunder", "cpl": 250,
             "san": "Qe5", "piece": "Q", "to_square": "e5"},
            {"ply": 8, "is_player_move": 0, "is_capture": 1, "to_square": "e5",
             "material_delta": 900, "san": "Rxe5"},
        ])
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            reason_df, _piece_df, _mate_df = get_giant_killing_collapse_causes(duck)
            reason_lookup = dict(zip(reason_df.reason, reason_df.n))
            assert reason_lookup["hung_piece"] == 1
            assert reason_lookup.get("faced_mate", 0) == 0
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def test_get_giant_killing_rate_trend_on_empty_db(self, migrated_db):
        from data.matchups import get_giant_killing_rate_trend
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            df = get_giant_killing_rate_trend(duck)
            assert df.empty
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def test_get_giant_killing_rate_trend_zero_fills_and_computes_pct(self, migrated_db):
        from data.matchups import get_giant_killing_rate_trend
        rows = [
            # Q1 2025: one upset win out of one underdog game; one
            # favorite game, no collapse.
            ("g1", 2025, 1, -300, "win"),
            ("g2", 2025, 1, 300, "win"),
            # Q3 2025 (Q2 deliberately skipped -- must zero-fill): one
            # favorite game, one collapse.
            ("g3", 2025, 7, 300, "loss"),
        ]
        for gid, year, month, rd, outcome in rows:
            migrated_db.execute(
                "INSERT INTO games (id, white, black, outcome_for_player, "
                "rating_diff, year, month) VALUES (?, 'W', 'B', ?, ?, ?, ?)",
                (gid, outcome, rd, year, month))
        migrated_db.commit()
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            df = get_giant_killing_rate_trend(duck)
            by_label = df.set_index("label")
            assert by_label.loc["2025 Q1", "n_underdog"] == 1
            assert by_label.loc["2025 Q1", "pct_upset"] == pytest.approx(100.0)
            assert by_label.loc["2025 Q1", "n_favorite"] == 1
            assert by_label.loc["2025 Q1", "pct_collapse"] == pytest.approx(0.0)
            assert by_label.loc["2025 Q3", "n_favorite"] == 1
            assert by_label.loc["2025 Q3", "pct_collapse"] == pytest.approx(100.0)
            # zero-filled gap quarter between Q1 and Q3.
            assert "2025 Q2" in by_label.index
            assert by_label.loc["2025 Q2", "n_favorite"] == 0
        finally:
            duck.close(); disk.close(); os.unlink(tmp)


@pytest.mark.integration
class TestTacticalData:
    def test_get_motif_breakdown_on_empty_db(self, migrated_db):
        # takes sqlite_conn since migration 0031 (partial motif index)
        from data.tactical import get_motif_breakdown
        df = get_motif_breakdown(migrated_db)
        assert df is not None

    def test_get_brilliant_candidates_on_empty_db(self, migrated_db):
        from data.tactical import get_brilliant_candidates
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            df = get_brilliant_candidates(duck)
            assert df is not None
        finally:
            duck.close(); disk.close(); os.unlink(tmp)


@pytest.mark.integration
class TestPatternsData:
    def test_get_instant_move_rate_by_phase_on_empty_db(self, migrated_db):
        from data.patterns import get_instant_move_rate_by_phase
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            df = get_instant_move_rate_by_phase(duck)
            assert df is not None
            assert len(df) == 0
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def test_get_instant_move_rate_by_phase_with_populated_db(self, populated_db):
        """synthetic_games.pgn's first game has a natural zero-time move at
        ply 1 (both colors' first %clk reading equals the base clock) --
        confirms the opening (1-10) bucket picks it up."""
        from data.patterns import get_instant_move_rate_by_phase
        duck, disk, tmp = _duck_from_conn(populated_db)
        try:
            df = get_instant_move_rate_by_phase(duck)
            assert df is not None
            opening = df[df.bucket == "opening (1-10)"]
            assert len(opening) == 1
            assert opening.iloc[0]["n_instant"] > 0
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def test_get_instant_move_accuracy_by_legal_replies_on_empty_db(self, migrated_db):
        from data.patterns import get_instant_move_accuracy_by_legal_replies
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            result_df, n_analyzed, n_total = get_instant_move_accuracy_by_legal_replies(duck)
            assert len(result_df) == 0
            assert n_analyzed == 0
            assert n_total == 0
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def test_get_instant_move_accuracy_by_legal_replies_excludes_opening(self, populated_db):
        """The only zero-time move in the populated fixture is at ply 1
        (opening) -- past the default instant_move_exclude_max_ply=10, no
        candidate moves exist, so this must return safely empty, not raise."""
        from data.patterns import get_instant_move_accuracy_by_legal_replies
        duck, disk, tmp = _duck_from_conn(populated_db)
        try:
            result_df, n_analyzed, n_total = get_instant_move_accuracy_by_legal_replies(duck)
            assert result_df is not None
            assert n_total == 0
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def test_get_day_hour_heatmap_returns_aligned_pivots(self, migrated_db):
        """Returns (win_pct_pivot, avg_rating_diff_pivot) sharing the same
        index/columns shape -- charts.heatmap's hover_extra reindexes the
        second onto the first, so a caller passing a differently-sorted
        frame must still line up cell-for-cell."""
        from data.patterns import get_day_hour_heatmap
        rows = [
            ("g1", 0, 12, "win", 100),
            ("g2", 0, 12, "loss", -50),
            ("g3", 1, 18, "win", 300),
        ]
        for gid, dow, hour, outcome, rd in rows:
            migrated_db.execute(
                "INSERT INTO games (id, white, black, outcome_for_player, "
                "day_of_week, hour_utc, rating_diff) VALUES (?, 'W', 'B', ?, ?, ?, ?)",
                (gid, outcome, dow, hour, rd))
        migrated_db.commit()
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            win_pivot, rating_pivot = get_day_hour_heatmap(duck)
            assert win_pivot.shape == rating_pivot.shape
            assert list(win_pivot.index) == list(rating_pivot.index)
            assert list(win_pivot.columns) == list(rating_pivot.columns)
            assert win_pivot.loc[0, 12] == pytest.approx(50.0)      # 1 win of 2
            assert rating_pivot.loc[0, 12] == pytest.approx(25.0)   # avg(100, -50)
            assert win_pivot.loc[1, 18] == pytest.approx(100.0)
            assert rating_pivot.loc[1, 18] == pytest.approx(300.0)
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


@pytest.mark.integration
class TestPointsData:
    """dashboard/data/points.py -- expected-points decomposition.

    Bucket assignment is exercised end-to-end (SQL primitives via a real
    DuckDB attach, then the pandas classifier) on hand-crafted win-prob
    curves, one per bucket plus the priority and exclusion edge cases.
    """

    # (game_id, outcome, status, [(move_number, player_wp, clock_seconds)])
    SCENARIOS = [
        # peak 0.85 at m20, first winning at m14 (middlegame, clock 200/300),
        # then collapses and loses -> failed_conversion, leak 0.85
        ("g_convloss", "loss", "done",
         [(1, 0.50, None), (5, 0.55, None), (14, 0.72, 200), (20, 0.85, 150),
          (25, 0.30, None), (30, 0.10, None)]),
        # peak 0.95, drew -> failed_conversion, leak 0.45, band 90%+, no clocks
        ("g_convdraw", "draw", "done",
         [(1, 0.50, None), (10, 0.60, None), (16, 0.95, None), (30, 0.55, None)]),
        # lost (0.10 at m10), given 0.60 at m18, lost anyway ->
        # missed_swindle, leak 0.60. Also satisfies the failed_hold
        # condition (0.60 >= EVEN_WP at m18 >= 15) -- priority test.
        ("g_swindle", "loss", "done",
         [(1, 0.50, None), (5, 0.30, None), (10, 0.10, None), (14, 0.20, None),
          (18, 0.60, None), (25, 0.15, None)]),
        # even through m16, drifts to a loss without ever being lost-then-
        # given-a-chance (prior min at m30 is 0.30 > LOST_WP) -> failed_hold
        ("g_hold", "loss", "done",
         [(1, 0.50, None), (10, 0.48, None), (16, 0.50, None), (22, 0.30, None),
          (30, 0.05, None)]),
        # steadily outplayed, never even after move 15, chance after being
        # lost never reaches 0.50 -> none
        ("g_fair", "loss", "done",
         [(1, 0.50, None), (8, 0.40, None), (14, 0.20, None), (20, 0.05, None)]),
        # converted win -> none, leak 0
        ("g_win", "win", "done",
         [(1, 0.50, None), (10, 0.80, None), (20, 0.95, None)]),
        # partially analyzed -> excluded from the ledger entirely
        ("g_pending", "loss", "pending",
         [(1, 0.50, None), (20, 0.90, None)]),
    ]

    def _insert_scenarios(self, conn):
        for gid, outcome, status, curve in self.SCENARIOS:
            conn.execute("""
                INSERT INTO games (id, site, white, black, result,
                    outcome_for_player, analysis_status, utc_date,
                    base_seconds, time_control_category, opening_family,
                    player_color, opponent_name)
                VALUES (?, 'https://lichess.org/' || ?, 'me', 'them', '1-0',
                        ?, ?, '2026.01.05', 300, 'blitz', 'Test Opening',
                        'white', 'them')
            """, (gid, gid, outcome, status))
            for move_number, wp, clock in curve:
                conn.execute("""
                    INSERT INTO moves (game_id, ply, move_number, color, san,
                        is_player_move, win_prob_before, clock_seconds)
                    VALUES (?, ?, ?, 'w', 'e4', 1, ?, ?)
                """, (gid, 2 * move_number - 1, move_number, wp, clock))
        conn.commit()

    def _classified(self, migrated_db):
        from data import points
        self._insert_scenarios(migrated_db)
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            return points.classify_points_ledger(points.get_points_ledger(duck))
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def test_empty_db_is_safe(self, migrated_db):
        from data import points
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            classified = points.classify_points_ledger(points.get_points_ledger(duck))
        finally:
            duck.close(); disk.close(); os.unlink(tmp)
        assert len(classified) == 0
        assert points.summarize_buckets(classified).empty
        assert points.monthly_points(classified).empty
        for dim in ("adv_band", "conv_phase", "conv_clock"):
            assert points.conversion_breakdown(classified, dim).empty

    def test_bucket_assignment(self, migrated_db):
        df = self._classified(migrated_db).set_index("game_id")
        assert "g_pending" not in df.index          # not fully analyzed
        assert df.loc["g_convloss"].bucket == "failed_conversion"
        assert df.loc["g_convdraw"].bucket == "failed_conversion"
        assert df.loc["g_swindle"].bucket == "missed_swindle"  # priority over hold
        assert df.loc["g_hold"].bucket == "failed_hold"
        assert df.loc["g_fair"].bucket == "none"
        assert df.loc["g_win"].bucket == "none"

    def test_leak_amounts(self, migrated_db):
        df = self._classified(migrated_db).set_index("game_id")
        assert df.loc["g_convloss"].leaked == pytest.approx(0.85)  # peak - 0
        assert df.loc["g_convdraw"].leaked == pytest.approx(0.45)  # peak - 0.5
        assert df.loc["g_swindle"].leaked == pytest.approx(0.60)   # the chance given
        assert df.loc["g_hold"].leaked == pytest.approx(0.50)      # even game's half point
        assert df.loc["g_fair"].leaked == 0.0
        assert df.loc["g_win"].leaked == 0.0

    def test_conversion_detail_dimensions(self, migrated_db):
        df = self._classified(migrated_db).set_index("game_id")
        row = df.loc["g_convloss"]
        assert row.first_winning_move == 14
        assert row.conv_phase == "middlegame"
        assert row.adv_band == "winning (80-90%)"
        assert row.conv_clock == "plenty (60-100%)"   # 200s of 300s base
        assert df.loc["g_convdraw"].adv_band == "completely winning (90%+)"
        assert df.loc["g_convdraw"].conv_clock == "no clock data"

    def test_summary_and_monthly(self, migrated_db):
        from data import points
        df = self._classified(migrated_db)
        summary = points.summarize_buckets(df).set_index("bucket")
        assert int(summary.loc["failed_conversion"].n_games) == 2
        assert summary.loc["failed_conversion"].leaked == pytest.approx(1.30)
        monthly = points.monthly_points(df)
        assert len(monthly) == 1                      # all six games in 2026.01
        assert monthly.iloc[0].n_games == 6
        assert monthly.iloc[0].actual == pytest.approx(1.5)    # win + draw
        assert monthly.iloc[0].potential == pytest.approx(3.9)  # + 2.4 leaked
        assert monthly.iloc[0].actual_pct == pytest.approx(25.0)
        assert monthly.iloc[0].potential_pct == pytest.approx(65.0)
        assert monthly.iloc[0].month.strftime("%Y-%m") == "2026-01"

    def _seed_causes_game(self, conn, game_id, outcome, moves):
        """moves: list of dicts, one per ply, with whichever of
        win_prob_before/classification/cpl/eval_mate/best_move_san/
        piece/to_square/is_capture/material_delta/clock_seconds/
        is_player_move (color-derived default: white=player, matching
        this game's player_color='white') the scenario needs -- unlisted
        fields default to NULL/0, matching a real ingest row that never
        reached a given analysis stage."""
        conn.execute("""
            INSERT INTO games (id, site, white, black, result,
                outcome_for_player, analysis_status, utc_date,
                base_seconds, time_control_category, opening_family,
                player_color, opponent_name)
            VALUES (?, 'https://lichess.org/' || ?, 'me', 'them', '1-0',
                    ?, 'done', '2026.01.05', 300, 'blitz', 'Test Opening',
                    'white', 'them')
        """, (game_id, game_id, outcome))
        for mv in moves:
            ply = mv["ply"]
            color = "w" if ply % 2 == 1 else "b"
            is_player_move = mv.get("is_player_move", 1 if color == "w" else 0)
            conn.execute("""
                INSERT INTO moves (game_id, ply, move_number, color, san,
                    is_player_move, win_prob_before, clock_seconds,
                    classification, cpl, eval_mate, best_move_san,
                    piece, to_square, is_capture, material_delta)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (game_id, ply, (ply + 1) // 2, color, mv.get("san", "e4"),
                  is_player_move, mv.get("win_prob_before"), mv.get("clock_seconds"),
                  mv.get("classification"), mv.get("cpl"), mv.get("eval_mate"),
                  mv.get("best_move_san"), mv.get("piece"), mv.get("to_square"),
                  mv.get("is_capture", 0), mv.get("material_delta")))
        conn.commit()

    def test_get_failed_conversion_causes_on_empty_ledger(self, migrated_db):
        from data import points
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            classified = points.classify_points_ledger(points.get_points_ledger(duck))
            reason_df, piece_df, mate_df = points.get_failed_conversion_causes(duck, classified)
            assert reason_df.empty and piece_df.empty and mate_df.empty
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def test_get_failed_conversion_causes_classifies_reasons(self, migrated_db):
        from data import points
        # Reaches winning (wp>=0.70) at ply 3 in every scenario below --
        # only what happens AT OR AFTER ply 3 should matter to the cause.
        self._seed_causes_game(migrated_db, "fc_hang", "loss", [
            {"ply": 1, "win_prob_before": 0.50},
            {"ply": 3, "win_prob_before": 0.75},
            # Blunders the queen onto e5; opponent recaptures immediately.
            {"ply": 5, "win_prob_before": 0.75, "classification": "blunder", "cpl": 250,
             "san": "Qe5", "piece": "Q", "to_square": "e5"},
            {"ply": 6, "is_player_move": 0, "is_capture": 1, "to_square": "e5",
             "material_delta": 900, "san": "Rxe5"},
            {"ply": 7, "win_prob_before": 0.10},
        ])
        self._seed_causes_game(migrated_db, "fc_mate", "draw", [
            {"ply": 1, "win_prob_before": 0.50},
            {"ply": 3, "win_prob_before": 0.75},
            # Forced mate on the board, deviates from the engine's line.
            {"ply": 5, "win_prob_before": 0.75, "eval_mate": 5,
             "san": "Nf3", "best_move_san": "Qxh7#"},
            {"ply": 7, "win_prob_before": 0.40},
        ])
        self._seed_causes_game(migrated_db, "fc_timepressure", "loss", [
            {"ply": 1, "win_prob_before": 0.50},
            {"ply": 3, "win_prob_before": 0.75},
            # No hang/mate signal, but critically low own clock (10 of
            # 300s base = 3.3%, under the 5% "critical" threshold).
            {"ply": 5, "win_prob_before": 0.70, "clock_seconds": 10},
            {"ply": 7, "win_prob_before": 0.20},
        ])
        self._seed_causes_game(migrated_db, "fc_other", "draw", [
            {"ply": 1, "win_prob_before": 0.50},
            {"ply": 3, "win_prob_before": 0.75},
            # No hang, mate, or critical-clock signal at all.
            {"ply": 5, "win_prob_before": 0.72},
            {"ply": 7, "win_prob_before": 0.40},
        ])
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            classified = points.classify_points_ledger(points.get_points_ledger(duck))
            reason_df, piece_df, mate_df = points.get_failed_conversion_causes(duck, classified)
            reason_lookup = dict(zip(reason_df.reason, reason_df.n))
            assert reason_lookup["hung_piece"] == 1
            assert reason_lookup["blown_mate"] == 1
            assert reason_lookup["time_pressure"] == 1
            assert reason_lookup["other"] == 1
            assert dict(zip(piece_df.hung_piece, piece_df.n)) == {"Q": 1}
            assert mate_df.iloc[0]["bucket"] == "Mate in 3-5"  # eval_mate=5
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def test_get_failed_conversion_causes_hang_beats_blown_mate(self, migrated_db):
        """Both a qualifying hang AND a qualifying blown mate exist after
        the win was reached -- hung_piece must win, same priority order
        as get_resignation_loss_causes (hang > mate > clock > other)."""
        from data import points
        self._seed_causes_game(migrated_db, "fc_priority", "loss", [
            {"ply": 1, "win_prob_before": 0.50},
            {"ply": 3, "win_prob_before": 0.75},
            {"ply": 5, "win_prob_before": 0.75, "eval_mate": 5,
             "san": "Nf3", "best_move_san": "Qxh7#"},
            {"ply": 7, "win_prob_before": 0.72, "classification": "blunder", "cpl": 250,
             "san": "Qe5", "piece": "Q", "to_square": "e5"},
            {"ply": 8, "is_player_move": 0, "is_capture": 1, "to_square": "e5",
             "material_delta": 900, "san": "Rxe5"},
            {"ply": 9, "win_prob_before": 0.10},
        ])
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            classified = points.classify_points_ledger(points.get_points_ledger(duck))
            reason_df, _piece_df, _mate_df = points.get_failed_conversion_causes(duck, classified)
            reason_lookup = dict(zip(reason_df.reason, reason_df.n))
            assert reason_lookup["hung_piece"] == 1
            assert reason_lookup.get("blown_mate", 0) == 0
        finally:
            duck.close(); disk.close(); os.unlink(tmp)


@pytest.mark.integration
class TestSrsEfficacy:
    """dashboard/data/srs.py efficacy readers -- the first SELECTs
    srs_reviews has ever had. Reviews are inserted with controlled
    timestamps (apply_rating stamps now(), useless for before/after
    assertions)."""

    def _seed(self, conn):
        from data import srs as S
        conn.execute("INSERT INTO games (id, white, black, result) "
                     "VALUES ('g1', 'a', 'b', '1-0')")
        conn.execute("""
            INSERT INTO moves (game_id, ply, move_number, color, san,
                is_player_move, motif, fen_before)
            VALUES ('g1', 1, 1, 'w', 'e4', 1, 'fork', 'FEN_FORK')
        """)
        S.add_cards(conn, [
            {"fen": "FEN_FORK", "source": "Missed Tactics", "best_move_san": "Nf3"},
            {"fen": "FEN_HOLE", "source": "Repertoire Hole", "best_move_san": "d4"},
        ])
        ids = {fen: cid for cid, fen in
               conn.execute("SELECT id, fen FROM srs_cards").fetchall()}
        reviews = [
            (ids["FEN_FORK"], "2026-06-01T10:00:00", 0),   # 1st sight: forgot
            (ids["FEN_FORK"], "2026-06-02T10:00:00", 2),   # 2nd: good
            (ids["FEN_FORK"], "2026-06-05T10:00:00", 3),   # 3rd: easy
            (ids["FEN_HOLE"], "2026-06-03T10:00:00", 2),
        ]
        for cid, ts, rating in reviews:
            conn.execute("""
                INSERT INTO srs_reviews (card_id, reviewed_at, rating,
                    interval_days_after) VALUES (?, ?, ?, 1)
            """, (cid, ts, rating))
        conn.commit()
        return ids

    def test_empty_db_is_safe(self, migrated_db):
        from data import srs as S
        history = S.get_review_history(migrated_db)
        assert history.empty
        assert S.weekly_recall(history).empty
        assert S.learning_curve(history).empty
        assert S.recall_by_source(history).empty
        assert S.get_drilled_motifs(migrated_db).empty

    def test_review_history_and_learning_curve(self, migrated_db):
        from data import srs as S
        self._seed(migrated_db)
        history = S.get_review_history(migrated_db)
        assert len(history) == 4
        fork = history[history.source == "Missed Tactics"]
        assert fork.review_index.tolist() == [1, 2, 3]
        curve = S.learning_curve(history).set_index("nth_review")
        assert curve.loc["1st"].recall_pct == pytest.approx(50.0)  # 0 and 2
        assert curve.loc["2nd"].recall_pct == pytest.approx(100.0)
        by_source = S.recall_by_source(history).set_index("source")
        assert by_source.loc["Missed Tactics"].n_reviews == 3

    def test_drilled_motifs_joins_by_fen(self, migrated_db):
        from data import srs as S
        self._seed(migrated_db)
        drilled = S.get_drilled_motifs(migrated_db)
        # only the fork card maps to a motif move; the hole card doesn't
        assert drilled.motif.tolist() == ["fork"]
        row = drilled.iloc[0]
        assert row.n_cards == 1
        assert row.n_reviews == 3
        assert row.first_review == "2026-06-01"

    def test_compute_motif_transfer(self, migrated_db):
        import pandas as pd
        from data import srs as S
        self._seed(migrated_db)
        drilled = S.get_drilled_motifs(migrated_db)
        moves = pd.DataFrame({
            # cutoff day itself (2026-06-01) counts as AFTER
            "d": ["2026-05-20", "2026-06-01", "2026-06-10"],
            "n_moves": [1000, 100, 400]})
        misses = pd.DataFrame({
            "motif": ["fork", "fork", "fork"],
            "d": ["2026-05-20", "2026-06-01", "2026-06-10"],
            "n_misses": [9, 1, 1]})
        t = S.compute_motif_transfer(drilled, moves, misses,
                                     min_moves_after=200)
        row = t.iloc[0]
        assert row.moves_before == 1000 and row.moves_after == 500
        assert row.misses_before == 9 and row.misses_after == 2
        assert row.rate_before == pytest.approx(9.0)
        assert row.rate_after == pytest.approx(4.0)
        assert bool(row.measurable)
        # guard: not enough post-drill moves
        t2 = S.compute_motif_transfer(drilled, moves, misses,
                                      min_moves_after=600)
        assert not bool(t2.iloc[0].measurable)
        # motif with no miss rows at all -> rates land at 0, not NaN/crash
        t3 = S.compute_motif_transfer(drilled, moves,
                                      misses[misses.motif == "pin"],
                                      min_moves_after=200)
        assert t3.iloc[0].misses_after == 0
        assert t3.iloc[0].rate_after == pytest.approx(0.0)


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


@pytest.mark.integration
class TestEvolutionData:
    def test_get_family_acpl_by_period_on_empty_db(self, migrated_db):
        from data.evolution import get_family_acpl_by_period
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            df = get_family_acpl_by_period(duck, "Test Opening", "white")
            assert df.empty
            assert list(df.columns) == [
                "label", "n_moves", "n_games", "acpl", "n_total_games", "coverage_pct"]
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def _seed_game(self, conn, game_id, year, month, n_analyzed_moves):
        conn.execute(
            "INSERT INTO games (id, white, black, opening_family, "
            "player_color, year, month) "
            "VALUES (?, 'a', 'b', 'Test Opening', 'white', ?, ?)",
            (game_id, year, month))
        for ply in range(1, n_analyzed_moves + 1):
            conn.execute("""
                INSERT INTO moves (game_id, ply, move_number, color, san,
                    is_player_move, cpl)
                VALUES (?, ?, ?, 'w', 'e4', 1, 10)
            """, (game_id, ply * 2 - 1, ply))
        conn.commit()

    def test_get_family_acpl_by_period_coverage_pct(self, migrated_db):
        """coverage_pct is n_games-with-analyzed-moves / n_total_games in
        that quarter for this family/color -- NOT the analyzed-move count
        itself, and NOT scoped to games with zero analysis (those don't
        appear in the moves-table scan at all but still count toward the
        quarter's total). Verified live on the real dev DB (2026-07-07):
        White's English Opening has quarters ranging from 0% to 76.3%
        analyzed coverage -- exactly the gap this column discloses."""
        from data.evolution import get_family_acpl_by_period
        # Q1 2024 (Jan-Mar): 2 total games, 1 analyzed (3 moves) -> 50%.
        self._seed_game(migrated_db, "g1", 2024, 2, n_analyzed_moves=3)
        migrated_db.execute(
            "INSERT INTO games (id, white, black, opening_family, "
            "player_color, year, month) "
            "VALUES ('g2', 'a', 'b', 'Test Opening', 'white', 2024, 2)")
        # Q2 2024 (Apr-Jun): 1 total game, fully analyzed (2 moves) -> 100%.
        self._seed_game(migrated_db, "g3", 2024, 5, n_analyzed_moves=2)
        migrated_db.commit()
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            df = get_family_acpl_by_period(
                duck, "Test Opening", "white", min_moves_per_quarter=1)
            by_label = df.set_index("label")
            assert by_label.loc["2024 Q1", "n_games"] == 1
            assert by_label.loc["2024 Q1", "n_total_games"] == 2
            assert by_label.loc["2024 Q1", "coverage_pct"] == pytest.approx(50.0)
            assert by_label.loc["2024 Q2", "n_total_games"] == 1
            assert by_label.loc["2024 Q2", "coverage_pct"] == pytest.approx(100.0)
        finally:
            duck.close(); disk.close(); os.unlink(tmp)


@pytest.mark.integration
class TestPositionCharacterData:
    """Board-position-character + squares drill-down (2026-07-07): open/
    semi-open/closed and symmetric/asymmetric come from one fen_before
    fetch+classify pass at the real config's middlegame_ply=24 checkpoint;
    castling-configuration/action-side and the square heatmap read
    moves.is_castle/is_capture/to_square directly, no FEN needed."""

    def test_get_position_character_performance_on_empty_db(self, migrated_db):
        from data.patterns import get_position_character_performance
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            r = get_position_character_performance(duck)
            assert r["n_classified"] == 0
            assert r["bucket_win"].empty and r["bucket_acpl"].empty
            assert r["central_tension_pct"] is None
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def _seed_checkpoint_game(self, conn, game_id, outcome, fen_at_checkpoint, cpl=None):
        """Inserts one game with a move at ply=24 (the real config.yaml's
        middlegame_ply) carrying the given fen_before, plus one
        is_player_move cpl row when cpl is given -- mirrors
        TestGameEndingsData._seed_time_forfeit_game's shape for this
        feature's own inputs."""
        conn.execute(
            "INSERT INTO games (id, white, black, outcome_for_player, player_color) "
            "VALUES (?, 'W', 'B', ?, 'white')", (game_id, outcome))
        conn.execute(
            "INSERT INTO moves (game_id, ply, move_number, color, san, fen_before) "
            "VALUES (?, 24, 12, 'w', 'Nf3', ?)", (game_id, fen_at_checkpoint))
        if cpl is not None:
            conn.execute(
                "INSERT INTO moves (game_id, ply, move_number, color, san, cpl, "
                "classification, is_player_move) VALUES (?, 1, 1, 'w', 'e4', ?, 'good', 1)",
                (game_id, cpl))
        conn.commit()

    def test_short_games_excluded_from_classification(self, migrated_db):
        """A game with moves but none at ply=24 contributes no row -- same
        'no row for games that never reach the checkpoint' convention as
        analytics.ensure_structure_ctx."""
        from data.patterns import get_position_character_performance
        migrated_db.execute(
            "INSERT INTO games (id, white, black, outcome_for_player, player_color) "
            "VALUES ('g1', 'W', 'B', 'win', 'white')")
        migrated_db.execute(
            "INSERT INTO moves (game_id, ply, move_number, color, san) "
            "VALUES ('g1', 5, 3, 'w', 'Nf3')")
        migrated_db.commit()
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            r = get_position_character_performance(duck)
            assert r["n_classified"] == 0
            assert r["n_total_games"] == 1
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def test_bucket_classification_and_win_rate(self, migrated_db):
        from data.patterns import get_position_character_performance
        # French Advance shape: White d4/e5 vs Black d5/e6, both files
        # locked -- same FEN chess_utils's own unit test uses.
        CLOSED_FEN = "rnbqkbnr/ppp2ppp/4p3/3pP3/3P4/8/PPP2PPP/RNBQKBNR b KQkq - 0 3"
        OPEN_FEN = "4k3/8/8/8/8/8/8/4K3 w - - 0 1"
        self._seed_checkpoint_game(migrated_db, "g1", "win", CLOSED_FEN, cpl=20)
        self._seed_checkpoint_game(migrated_db, "g2", "loss", CLOSED_FEN)
        self._seed_checkpoint_game(migrated_db, "g3", "win", OPEN_FEN)
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            r = get_position_character_performance(duck)
            win_lookup = {row.bucket: (row.n_games, row.win_pct)
                          for row in r["bucket_win"].itertuples()}
            assert win_lookup["closed"] == (2, 50.0)
            assert win_lookup["open"] == (1, 100.0)
            acpl_lookup = {row.bucket: row.n_games for row in r["bucket_acpl"].itertuples()}
            # Only g1 carries a cpl row -- g2 (also closed) has none.
            assert acpl_lookup["closed"] == 1
            assert "open" not in acpl_lookup
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def test_symmetric_asymmetric_and_central_tension(self, migrated_db):
        from data.patterns import get_position_character_performance
        START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
        TENSION_FEN = "4k3/8/8/4p3/3P4/8/8/4K3 w - - 0 1"          # semi-open, asymmetric, tension
        ASYMMETRIC_FEN = "rnbqkbnr/ppp1pppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
        self._seed_checkpoint_game(migrated_db, "g1", "win", START_FEN)        # symmetric, no tension
        self._seed_checkpoint_game(migrated_db, "g2", "win", TENSION_FEN)      # asymmetric, tension
        self._seed_checkpoint_game(migrated_db, "g3", "loss", ASYMMETRIC_FEN)  # asymmetric, no tension
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            r = get_position_character_performance(duck)
            # All 3 are semi-open (untouched or single-pawn-tension center,
            # nothing locked) -- 1 of them (g2) has central tension.
            assert r["central_tension_pct"] == pytest.approx(100.0 / 3)
            sym_lookup = {row.symmetry_label: row.n_games
                          for row in r["symmetric_win"].itertuples()}
            assert sym_lookup["symmetric"] == 1
            assert sym_lookup["asymmetric"] == 2
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def test_get_game_side_performance_on_empty_db(self, migrated_db):
        from data.patterns import get_game_side_performance
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            r = get_game_side_performance(duck)
            assert r["castling_win"].empty and r["action_win"].empty
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def _seed_castle_game(self, conn, game_id, outcome, white_castle_to, black_castle_to,
                          q_caps=0, k_caps=0):
        conn.execute(
            "INSERT INTO games (id, white, black, outcome_for_player, player_color) "
            "VALUES (?, 'W', 'B', ?, 'white')", (game_id, outcome))
        ply = 1
        if white_castle_to:
            conn.execute(
                "INSERT INTO moves (game_id, ply, move_number, color, san, is_castle, to_square) "
                "VALUES (?, ?, ?, 'w', 'O-O', 1, ?)", (game_id, ply, (ply + 1) // 2, white_castle_to))
            ply += 1
        if black_castle_to:
            conn.execute(
                "INSERT INTO moves (game_id, ply, move_number, color, san, is_castle, to_square) "
                "VALUES (?, ?, ?, 'b', 'O-O', 1, ?)", (game_id, ply, (ply + 1) // 2, black_castle_to))
            ply += 1
        for _ in range(q_caps):
            conn.execute(
                "INSERT INTO moves (game_id, ply, move_number, color, san, is_capture, to_square) "
                "VALUES (?, ?, ?, 'w', 'Nxc6', 1, 'c6')", (game_id, ply, (ply + 1) // 2))
            ply += 1
        for _ in range(k_caps):
            conn.execute(
                "INSERT INTO moves (game_id, ply, move_number, color, san, is_capture, to_square) "
                "VALUES (?, ?, ?, 'w', 'Nxf6', 1, 'f6')", (game_id, ply, (ply + 1) // 2))
            ply += 1
        if not white_castle_to and not black_castle_to and q_caps == 0 and k_caps == 0:
            # At least one move row so this game still surfaces in the
            # INNER JOIN (never-castled, action-balanced case).
            conn.execute(
                "INSERT INTO moves (game_id, ply, move_number, color, san) "
                "VALUES (?, 1, 1, 'w', 'a4')", (game_id,))
        conn.commit()

    def test_castling_configuration(self, migrated_db):
        from data.patterns import get_game_side_performance
        self._seed_castle_game(migrated_db, "g1", "win", "g1", "g8")   # same-side (kingside)
        self._seed_castle_game(migrated_db, "g2", "loss", "c1", "g8")  # opposite-side
        self._seed_castle_game(migrated_db, "g3", "win", "g1", None)   # one-side-only
        self._seed_castle_game(migrated_db, "g4", "loss", None, None)  # never-castled
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            r = get_game_side_performance(duck)
            lookup = {row.castling_config: row.n_games
                      for row in r["castling_win"].itertuples()}
            assert lookup["same-side"] == 1
            assert lookup["opposite-side"] == 1
            assert lookup["one-side-only"] == 1
            assert lookup["never-castled"] == 1
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def test_action_side_concentration(self, migrated_db):
        from data.patterns import get_game_side_performance
        self._seed_castle_game(migrated_db, "g1", "win", None, None, q_caps=3, k_caps=0)
        self._seed_castle_game(migrated_db, "g2", "loss", None, None, q_caps=0, k_caps=3)
        # ratio 2:2 = 1.0, below the default 1.5 threshold -> balanced.
        self._seed_castle_game(migrated_db, "g3", "win", None, None, q_caps=2, k_caps=2)
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            r = get_game_side_performance(duck)
            lookup = {row.action_side: row.n_games for row in r["action_win"].itertuples()}
            assert lookup["queenside-heavy"] == 1
            assert lookup["kingside-heavy"] == 1
            assert lookup["balanced"] == 1
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def test_get_square_blunder_heatmap_on_empty_db(self, migrated_db):
        from data.patterns import get_square_blunder_heatmap
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            blunder_pivot, n_moves_pivot, n_analyzed, n_total = get_square_blunder_heatmap(duck)
            assert blunder_pivot is None and n_moves_pivot is None
            assert n_analyzed == 0 and n_total == 0
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def _seed_square_moves(self, conn, game_id, to_square, n_moves, n_blunders):
        conn.execute("INSERT INTO games (id, white, black) VALUES (?, 'W', 'B')", (game_id,))
        for i in range(n_moves):
            classification = "blunder" if i < n_blunders else "good"
            conn.execute(
                "INSERT INTO moves (game_id, ply, move_number, color, san, to_square, "
                "cpl, classification, is_player_move) VALUES (?, ?, ?, 'w', 'e4', ?, ?, ?, 1)",
                (game_id, i + 1, i + 1, to_square, 50, classification))
        conn.commit()

    def test_min_moves_floor_excludes_thin_squares(self, migrated_db):
        """square_heatmap_min_moves=20 (real config.yaml default): e4 clears
        it (25 moves), a1 doesn't (5 moves) -- a1 must be excluded
        entirely, not shown with a noisy small-sample rate."""
        from data.patterns import get_square_blunder_heatmap
        self._seed_square_moves(migrated_db, "g1", "e4", 25, 5)
        self._seed_square_moves(migrated_db, "g2", "a1", 5, 5)
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            blunder_pivot, n_moves_pivot, n_analyzed, n_total = get_square_blunder_heatmap(duck)
            assert blunder_pivot is not None
            assert blunder_pivot.loc[4, "e"] == pytest.approx(20.0)
            assert "a" not in blunder_pivot.columns
            assert n_moves_pivot.loc[4, "e"] == 25
            assert n_analyzed == 30
            assert n_total == 30
        finally:
            duck.close(); disk.close(); os.unlink(tmp)


@pytest.mark.integration
class TestAiCoachData:
    """dashboard/data/ai_coach.py -- AI Coach (Pro feature) CRUD: plain core
    plumbing, no Claude API calls, no tool-set/prompt logic."""

    def test_start_conversation_and_add_turns_in_order(self, migrated_db):
        from data import ai_coach as C
        conv_id = C.start_conversation(migrated_db)
        assert isinstance(conv_id, int)
        t1 = C.add_turn(migrated_db, conv_id, "user", "How's my endgame?")
        t2 = C.add_turn(migrated_db, conv_id, "assistant", "Let's look at your rook endings.")
        assert t2 > t1
        messages = C.get_conversation_messages(migrated_db, conv_id)
        assert messages == [
            {"role": "user", "content": "How's my endgame?"},
            {"role": "assistant", "content": "Let's look at your rook endings."},
        ]

    def test_add_turn_rejects_invalid_role(self, migrated_db):
        from data import ai_coach as C
        conv_id = C.start_conversation(migrated_db)
        with pytest.raises(ValueError):
            C.add_turn(migrated_db, conv_id, "system", "not allowed")

    def test_get_conversation_messages_scoped_to_one_conversation(self, migrated_db):
        from data import ai_coach as C
        conv1 = C.start_conversation(migrated_db)
        conv2 = C.start_conversation(migrated_db)
        C.add_turn(migrated_db, conv1, "user", "conv1 question")
        C.add_turn(migrated_db, conv2, "user", "conv2 question")
        assert len(C.get_conversation_messages(migrated_db, conv1)) == 1
        assert C.get_conversation_messages(migrated_db, conv1)[0]["content"] == "conv1 question"

    def test_record_feedback_on_assistant_turn(self, migrated_db):
        from data import ai_coach as C
        conv_id = C.start_conversation(migrated_db)
        turn_id = C.add_turn(migrated_db, conv_id, "assistant", "Some advice.")
        C.record_feedback(migrated_db, turn_id, -1)
        turns = C.get_all_turns(migrated_db)
        assert turns[0]["feedback"] == -1

    def test_record_feedback_rejects_invalid_turn_id(self, migrated_db):
        from data import ai_coach as C
        with pytest.raises(ValueError):
            C.record_feedback(migrated_db, 999999, 1)

    def test_record_feedback_rejects_non_assistant_turn(self, migrated_db):
        from data import ai_coach as C
        conv_id = C.start_conversation(migrated_db)
        user_turn_id = C.add_turn(migrated_db, conv_id, "user", "hi")
        with pytest.raises(ValueError):
            C.record_feedback(migrated_db, user_turn_id, 1)

    def test_record_feedback_rejects_invalid_value(self, migrated_db):
        from data import ai_coach as C
        conv_id = C.start_conversation(migrated_db)
        turn_id = C.add_turn(migrated_db, conv_id, "assistant", "hi")
        with pytest.raises(ValueError):
            C.record_feedback(migrated_db, turn_id, 2)

    def test_get_all_turns_ordering_and_thumbs_down_filter(self, migrated_db):
        from data import ai_coach as C
        conv_id = C.start_conversation(migrated_db)
        t1 = C.add_turn(migrated_db, conv_id, "user", "q1")
        t2 = C.add_turn(migrated_db, conv_id, "assistant", "bad advice")
        t3 = C.add_turn(migrated_db, conv_id, "assistant", "good advice")
        C.record_feedback(migrated_db, t2, -1)
        C.record_feedback(migrated_db, t3, 1)

        all_turns = C.get_all_turns(migrated_db)
        assert [t["id"] for t in all_turns] == [t1, t2, t3]

        filtered = C.get_all_turns(migrated_db, exclude_thumbs_down=True)
        assert [t["id"] for t in filtered] == [t1, t3]

    def test_get_all_turns_since_timestamp(self, migrated_db):
        from data import ai_coach as C
        conv_id = C.start_conversation(migrated_db)
        migrated_db.execute("""
            INSERT INTO ai_coach_turns (conversation_id, role, content, created_at)
            VALUES (?, 'user', 'old message', '2026-01-01T00:00:00')
        """, [conv_id])
        migrated_db.execute("""
            INSERT INTO ai_coach_turns (conversation_id, role, content, created_at)
            VALUES (?, 'user', 'new message', '2026-06-01T00:00:00')
        """, [conv_id])
        migrated_db.commit()

        since = C.get_all_turns(migrated_db, since="2026-03-01T00:00:00")
        assert [t["content"] for t in since] == ["new message"]

        combined = C.get_all_turns(migrated_db, exclude_thumbs_down=True,
                                    since="2026-03-01T00:00:00")
        assert [t["content"] for t in combined] == ["new message"]

    def test_profile_get_returns_none_before_any_upsert(self, migrated_db):
        from data import ai_coach as C
        assert C.get_profile(migrated_db) is None

    def test_profile_upsert_round_trip(self, migrated_db):
        from data import ai_coach as C
        C.upsert_profile(migrated_db, "Player struggles in rook endings.",
                          12, "2026-06-01T00:00:00", "claude-sonnet-5")
        profile = C.get_profile(migrated_db)
        assert profile == {
            "summary_text": "Player struggles in rook endings.",
            "source_turns": 12,
            "generated_at": "2026-06-01T00:00:00",
            "model": "claude-sonnet-5",
        }
        # upsert again -- always writes back to id=1, replacing the row
        C.upsert_profile(migrated_db, "Updated summary.", 20,
                          "2026-07-01T00:00:00", "claude-sonnet-5")
        profile2 = C.get_profile(migrated_db)
        assert profile2["summary_text"] == "Updated summary."
        assert profile2["source_turns"] == 20
        # still a single row (id=1 singleton, not a second row)
        n_rows = migrated_db.execute(
            "SELECT COUNT(*) FROM ai_coach_profile").fetchone()[0]
        assert n_rows == 1

    def test_count_turns_since_staleness_helper(self, migrated_db):
        from data import ai_coach as C
        conv_id = C.start_conversation(migrated_db)
        migrated_db.execute("""
            INSERT INTO ai_coach_turns (conversation_id, role, content, created_at)
            VALUES (?, 'user', 'old', '2026-01-01T00:00:00')
        """, [conv_id])
        migrated_db.execute("""
            INSERT INTO ai_coach_turns (conversation_id, role, content, created_at)
            VALUES (?, 'user', 'new1', '2026-06-01T00:00:00')
        """, [conv_id])
        migrated_db.execute("""
            INSERT INTO ai_coach_turns (conversation_id, role, content, created_at)
            VALUES (?, 'user', 'new2', '2026-06-02T00:00:00')
        """, [conv_id])
        migrated_db.commit()
        assert C.count_turns_since(migrated_db, "2026-03-01T00:00:00") == 2
        assert C.count_turns_since(migrated_db, "2026-12-31T00:00:00") == 0

    def test_record_and_get_capability_gaps_newest_first(self, migrated_db):
        from data import ai_coach as C
        conv_id = C.start_conversation(migrated_db)
        turn1 = C.add_turn(migrated_db, conv_id, "assistant", "partial answer one")
        turn2 = C.add_turn(migrated_db, conv_id, "assistant", "partial answer two")

        gap1_id = C.record_capability_gap(
            migrated_db, turn1, "average move time by opening",
            "no per-opening move-time aggregation exists")
        assert isinstance(gap1_id, int)
        gap2_id = C.record_capability_gap(
            migrated_db, turn2, "best performing time control",
            "no per-time-control win-rate breakdown exists")
        assert gap2_id > gap1_id

        gaps = C.get_capability_gaps(migrated_db)
        # newest first (created_at DESC) -- gap2 was recorded after gap1.
        assert [g["id"] for g in gaps] == [gap2_id, gap1_id]
        assert gaps[0]["turn_id"] == turn2
        assert gaps[0]["question_summary"] == "best performing time control"
        assert gaps[0]["missing_data_description"] == (
            "no per-time-control win-rate breakdown exists")
        assert gaps[1]["turn_id"] == turn1

    def test_get_capability_gaps_respects_limit(self, migrated_db):
        from data import ai_coach as C
        conv_id = C.start_conversation(migrated_db)
        turn_id = C.add_turn(migrated_db, conv_id, "assistant", "answer")
        for i in range(5):
            C.record_capability_gap(migrated_db, turn_id, f"question {i}", f"missing {i}")
        assert len(C.get_capability_gaps(migrated_db, limit=3)) == 3
        assert len(C.get_capability_gaps(migrated_db)) == 5

    def test_record_capability_gap_requires_real_turn_id(self, migrated_db):
        """ai_coach_capability_gaps.turn_id REFERENCES ai_coach_turns(id) --
        this migrated_db fixture connection runs with foreign_keys ON (see
        conftest.py's migrated_db fixture and db.py's get_connection, which
        both explicitly set this PRAGMA every connection since it's not a
        database-file-level setting in SQLite), so inserting against a
        turn_id that doesn't exist must raise, not silently succeed."""
        from data import ai_coach as C
        with pytest.raises(sqlite3.IntegrityError):
            C.record_capability_gap(
                migrated_db, 999999, "some question", "some missing data")


class TestBoardChatData:
    """dashboard/data/board_chat.py -- Board Chat (Pro feature) CRUD: a
    game-scoped, multi-turn Claude conversation embedded in Game Detail's
    variation explorer. Plain core plumbing, no Claude API calls, no
    tool-set/prompt logic. Mirrors TestAiCoachData's shape for the
    functions shared in spirit with ai_coach.py, plus new tests for
    get_turns_for_display and list_conversations_for_game, which have no
    ai_coach.py analog."""

    def test_start_conversation_and_add_turns_in_order(self, populated_db):
        from data import board_chat as C
        game_id = populated_db.execute("SELECT id FROM games LIMIT 1").fetchone()[0]
        conv_id = C.start_conversation(populated_db, game_id)
        assert isinstance(conv_id, int)
        t1 = C.add_turn(populated_db, conv_id, "user", "What was the best move here?")
        t2 = C.add_turn(populated_db, conv_id, "assistant", "Nf3 was strongest.")
        assert t2 > t1
        messages = C.get_conversation_messages(populated_db, conv_id)
        assert messages == [
            {"role": "user", "content": "What was the best move here?"},
            {"role": "assistant", "content": "Nf3 was strongest."},
        ]

    def test_add_turn_rejects_invalid_role(self, populated_db):
        from data import board_chat as C
        game_id = populated_db.execute("SELECT id FROM games LIMIT 1").fetchone()[0]
        conv_id = C.start_conversation(populated_db, game_id)
        with pytest.raises(ValueError):
            C.add_turn(populated_db, conv_id, "system", "not allowed")

    def test_get_conversation_messages_scoped_to_one_conversation(self, populated_db):
        from data import board_chat as C
        game_id = populated_db.execute("SELECT id FROM games LIMIT 1").fetchone()[0]
        conv1 = C.start_conversation(populated_db, game_id)
        conv2 = C.start_conversation(populated_db, game_id)
        C.add_turn(populated_db, conv1, "user", "conv1 question")
        C.add_turn(populated_db, conv2, "user", "conv2 question")
        assert len(C.get_conversation_messages(populated_db, conv1)) == 1
        assert C.get_conversation_messages(populated_db, conv1)[0]["content"] == "conv1 question"

    def test_get_turns_for_display_board_directives_round_trip(self, populated_db):
        from data import board_chat as C
        import json as json_mod
        game_id = populated_db.execute("SELECT id FROM games LIMIT 1").fetchone()[0]
        conv_id = C.start_conversation(populated_db, game_id)
        t1 = C.add_turn(populated_db, conv_id, "user", "what about e4?")
        directives = json_mod.dumps([
            {"tool": "show_arrow", "from_square": "e2", "to_square": "e4", "style": "player_move"},
        ])
        t2 = C.add_turn(populated_db, conv_id, "assistant", "e4 is fine.",
                         board_directives=directives)

        turns = C.get_turns_for_display(populated_db, conv_id)
        assert [t["id"] for t in turns] == [t1, t2]
        assert turns[0]["role"] == "user"
        assert turns[0]["board_directives"] is None
        assert turns[1]["role"] == "assistant"
        assert turns[1]["board_directives"] == [
            {"tool": "show_arrow", "from_square": "e2", "to_square": "e4", "style": "player_move"},
        ]
        assert turns[1]["content"] == "e4 is fine."
        assert "created_at" in turns[0]

    def test_list_conversations_for_game_newest_first_with_turn_counts(self, populated_db):
        from data import board_chat as C
        game_id = populated_db.execute("SELECT id FROM games LIMIT 1").fetchone()[0]
        conv1 = C.start_conversation(populated_db, game_id)
        C.add_turn(populated_db, conv1, "user", "q1")
        conv2 = C.start_conversation(populated_db, game_id)
        C.add_turn(populated_db, conv2, "user", "q1")
        C.add_turn(populated_db, conv2, "assistant", "a1")
        C.add_turn(populated_db, conv2, "user", "q2")

        conversations = C.list_conversations_for_game(populated_db, game_id)
        # newest first -- conv2 was started after conv1.
        assert [c["id"] for c in conversations] == [conv2, conv1]
        counts = {c["id"]: c["turn_count"] for c in conversations}
        assert counts[conv1] == 1
        assert counts[conv2] == 3
        assert "started_at" in conversations[0]

    def test_list_conversations_for_game_empty_case(self, populated_db):
        from data import board_chat as C
        game_id = populated_db.execute("SELECT id FROM games LIMIT 1").fetchone()[0]
        assert C.list_conversations_for_game(populated_db, game_id) == []

    def test_record_and_get_capability_gaps_newest_first(self, populated_db):
        from data import board_chat as C
        game_id = populated_db.execute("SELECT id FROM games LIMIT 1").fetchone()[0]
        conv_id = C.start_conversation(populated_db, game_id)
        turn1 = C.add_turn(populated_db, conv_id, "assistant", "partial answer one")
        turn2 = C.add_turn(populated_db, conv_id, "assistant", "partial answer two")

        gap1_id = C.record_capability_gap(
            populated_db, turn1, "average move time by opening",
            "no per-opening move-time aggregation exists")
        assert isinstance(gap1_id, int)
        gap2_id = C.record_capability_gap(
            populated_db, turn2, "best performing time control",
            "no per-time-control win-rate breakdown exists")
        assert gap2_id > gap1_id

        gaps = C.get_capability_gaps(populated_db)
        # newest first (created_at DESC) -- gap2 was recorded after gap1.
        assert [g["id"] for g in gaps] == [gap2_id, gap1_id]
        assert gaps[0]["turn_id"] == turn2
        assert gaps[0]["question_summary"] == "best performing time control"
        assert gaps[0]["missing_data_description"] == (
            "no per-time-control win-rate breakdown exists")
        assert gaps[1]["turn_id"] == turn1

    def test_get_capability_gaps_respects_limit(self, populated_db):
        from data import board_chat as C
        game_id = populated_db.execute("SELECT id FROM games LIMIT 1").fetchone()[0]
        conv_id = C.start_conversation(populated_db, game_id)
        turn_id = C.add_turn(populated_db, conv_id, "assistant", "answer")
        for i in range(5):
            C.record_capability_gap(populated_db, turn_id, f"question {i}", f"missing {i}")
        assert len(C.get_capability_gaps(populated_db, limit=3)) == 3
        assert len(C.get_capability_gaps(populated_db)) == 5

    def test_record_capability_gap_requires_real_turn_id(self, populated_db):
        """board_chat_capability_gaps.turn_id REFERENCES board_chat_turns(id)
        -- this populated_db fixture connection runs with foreign_keys ON
        (see conftest.py), so inserting against a turn_id that doesn't
        exist at all must raise, not silently succeed."""
        from data import board_chat as C
        with pytest.raises(sqlite3.IntegrityError):
            C.record_capability_gap(
                populated_db, 999999, "some question", "some missing data")

    def test_record_capability_gap_rejects_ai_coach_turn_id(self, populated_db):
        """Direct regression test for the schema fix in migration 0036 /
        docs/scoping/ai-coach-board-interaction-implementation-plan-
        2026-07-08.md §0.2: board_chat_capability_gaps.turn_id is FK'd to
        board_chat_turns(id), NOT ai_coach_turns(id) -- reusing
        ai_coach_capability_gaps for board-chat gap reports would have let
        a board_chat_turns.id collide with an unrelated ai_coach_turns.id,
        or (correctly, as tested here) simply fail the FK check when the
        id only exists in the OTHER table. A turn_id that is a real,
        valid ai_coach_turns.id (but not a board_chat_turns.id) must still
        raise IntegrityError against board_chat_capability_gaps -- proving
        the FK is real and scoped to the right table, not just present."""
        from data import ai_coach as ai_coach_data
        from data import board_chat as C
        ai_coach_conv_id = ai_coach_data.start_conversation(populated_db)
        ai_coach_turn_id = ai_coach_data.add_turn(
            populated_db, ai_coach_conv_id, "assistant", "an ai coach reply")

        # Sanity check: this id is real, just in the wrong table.
        assert populated_db.execute(
            "SELECT 1 FROM ai_coach_turns WHERE id = ?", [ai_coach_turn_id]
        ).fetchone() is not None
        assert populated_db.execute(
            "SELECT 1 FROM board_chat_turns WHERE id = ?", [ai_coach_turn_id]
        ).fetchone() is None

        with pytest.raises(sqlite3.IntegrityError):
            C.record_capability_gap(
                populated_db, ai_coach_turn_id, "some question", "some missing data")

    def test_record_feedback_on_assistant_turn(self, populated_db):
        from data import board_chat as C
        game_id = populated_db.execute("SELECT id FROM games LIMIT 1").fetchone()[0]
        conv_id = C.start_conversation(populated_db, game_id)
        turn_id = C.add_turn(populated_db, conv_id, "assistant", "Nf3 is strongest.")
        C.record_feedback(populated_db, turn_id, -1)
        row = populated_db.execute(
            "SELECT feedback FROM board_chat_turns WHERE id = ?", [turn_id]).fetchone()
        assert row[0] == -1

    def test_record_feedback_rejects_invalid_turn_id(self, populated_db):
        from data import board_chat as C
        with pytest.raises(ValueError):
            C.record_feedback(populated_db, 999999, 1)

    def test_record_feedback_rejects_non_assistant_turn(self, populated_db):
        from data import board_chat as C
        game_id = populated_db.execute("SELECT id FROM games LIMIT 1").fetchone()[0]
        conv_id = C.start_conversation(populated_db, game_id)
        user_turn_id = C.add_turn(populated_db, conv_id, "user", "what about e4?")
        with pytest.raises(ValueError):
            C.record_feedback(populated_db, user_turn_id, 1)

    def test_record_feedback_rejects_invalid_value(self, populated_db):
        from data import board_chat as C
        game_id = populated_db.execute("SELECT id FROM games LIMIT 1").fetchone()[0]
        conv_id = C.start_conversation(populated_db, game_id)
        turn_id = C.add_turn(populated_db, conv_id, "assistant", "hi")
        with pytest.raises(ValueError):
            C.record_feedback(populated_db, turn_id, 2)

    def test_record_feedback_scoped_to_correct_turn(self, populated_db):
        from data import board_chat as C
        game_id = populated_db.execute("SELECT id FROM games LIMIT 1").fetchone()[0]
        conv_id = C.start_conversation(populated_db, game_id)
        t1 = C.add_turn(populated_db, conv_id, "user", "q1")
        t2 = C.add_turn(populated_db, conv_id, "assistant", "bad advice")
        t3 = C.add_turn(populated_db, conv_id, "assistant", "good advice")
        C.record_feedback(populated_db, t2, -1)
        C.record_feedback(populated_db, t3, 1)

        turns = C.get_turns_for_display(populated_db, conv_id)
        by_id = {t["id"]: t for t in turns}
        assert by_id[t1]["role"] == "user"
        # get_turns_for_display doesn't select feedback (display shape only
        # needs id/role/content/board_directives/created_at) -- confirm the
        # persisted value directly against the table instead.
        assert populated_db.execute(
            "SELECT feedback FROM board_chat_turns WHERE id = ?", [t2]).fetchone()[0] == -1
        assert populated_db.execute(
            "SELECT feedback FROM board_chat_turns WHERE id = ?", [t3]).fetchone()[0] == 1
        assert populated_db.execute(
            "SELECT feedback FROM board_chat_turns WHERE id = ?", [t1]).fetchone()[0] is None
