"""Integration tests for dashboard/data/patterns.py -- split from
test_data_layer.py (TestPatternsData, TestPositionCharacterData,
TestGetDecisiveMomentsBreakdown -- two non-contiguous source ranges),
see docs/superpowers/specs/2026-07-17-test-suite-reorg-and-speedup-design.md.
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

    def test_get_day_hour_heatmap_applies_utc_offset(self, migrated_db, monkeypatch):
        """hour_utc=23 with a +2 offset lands in hour_local=1 (wraps past
        midnight) -- shifts hour only, leaves day_of_week alone, matching
        this app's existing CLI report_by_hour_bucket convention
        (analytics.py) rather than inventing a new cross-adjustment."""
        from data import patterns as patterns_module
        from data.patterns import time_and_session as time_and_session_module
        migrated_db.execute(
            "INSERT INTO games (id, white, black, outcome_for_player, "
            "day_of_week, hour_utc, rating_diff) VALUES ('g1', 'W', 'B', 'win', 3, 23, 0)")
        migrated_db.commit()
        duck, disk, tmp = _duck_from_conn(migrated_db)
        monkeypatch.setattr(
            time_and_session_module, "get_config",
            lambda config_path=None: {"analytics": {"utc_offset_hours": 2}})
        try:
            win_pivot, _ = patterns_module.get_day_hour_heatmap(duck)
            assert 1 in win_pivot.columns
            assert 23 not in win_pivot.columns
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def test_get_event_name_breakdown_uses_config_min_sample_size(self, migrated_db, monkeypatch):
        from data import patterns as patterns_module
        from data.patterns import events as events_module
        monkeypatch.setattr(
            events_module, "get_config",
            lambda config_path=None: {"analytics": {"min_sample_size": 1}})
        migrated_db.execute(
            "INSERT INTO games (id, white, black, outcome_for_player, event) "
            "VALUES ('g1', 'W', 'B', 'win', 'Weekly Rapid Arena')")
        # _event_perf_rows INNER JOINs moves -- a game needs at least one
        # move row to appear in that scan at all.
        migrated_db.execute(
            "INSERT INTO moves (game_id, ply, move_number, color, san) "
            "VALUES ('g1', 1, 1, 'w', 'e4')")
        migrated_db.commit()
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            df = patterns_module.get_event_name_breakdown(duck)
            assert "Weekly Rapid Arena" in df.event.values  # 1 game qualifies at min_sample_size=1
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
class TestGetDecisiveMomentsBreakdown:
    def _seed_loss(self, conn, game_id, move_number, win_prob_before, win_prob_after,
                    base_seconds=180, clock_seconds=None):
        conn.execute(
            "INSERT INTO games (id, white, black, outcome_for_player, base_seconds) "
            "VALUES (?, 'W', 'B', 'loss', ?)", (game_id, base_seconds))
        conn.execute(
            "INSERT INTO moves (game_id, ply, move_number, color, san, is_player_move, "
            "win_prob_before, win_prob_after, clock_seconds) "
            "VALUES (?, ?, ?, 'w', 'e4', 1, ?, ?, ?)",
            (game_id, 2 * move_number - 1, move_number, win_prob_before, win_prob_after, clock_seconds))
        conn.commit()

    def test_empty_db(self, migrated_db):
        from data.patterns import get_decisive_moments_breakdown
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            result = get_decisive_moments_breakdown(duck)
        finally:
            duck.close(); disk.close(); os.unlink(tmp)
        assert result == {
            "n_losses": 0, "median_move": None, "most_common_phase": None,
            "by_move_bucket": [], "by_phase": [], "by_clock_bucket": [], "n_no_clock_data": 0,
        }

    def test_single_loss(self, migrated_db):
        from data.patterns import get_decisive_moments_breakdown
        self._seed_loss(migrated_db, "g1", move_number=8, win_prob_before=0.60,
                         win_prob_after=0.20, clock_seconds=90)
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            result = get_decisive_moments_breakdown(duck)
        finally:
            duck.close(); disk.close(); os.unlink(tmp)
        assert result["n_losses"] == 1
        assert result["median_move"] == 8
        assert result["most_common_phase"] == "opening"
        assert result["by_move_bucket"] == [{"bucket": "6–10", "n_losses": 1}]
        assert result["by_phase"] == [{"phase": "opening", "n_losses": 1}]
        # clock_fraction = 90/180 = 0.5 -> "comfortable (30-60%)"
        assert result["by_clock_bucket"] == [{"bucket": "comfortable (30-60%)", "n_losses": 1}]
        assert result["n_no_clock_data"] == 0

    def test_multi_bucket_and_missing_clock_data(self, migrated_db):
        from data.patterns import get_decisive_moments_breakdown
        self._seed_loss(migrated_db, "g1", move_number=8, win_prob_before=0.60,
                         win_prob_after=0.20, clock_seconds=90)
        self._seed_loss(migrated_db, "g2", move_number=21, win_prob_before=0.55,
                         win_prob_after=0.35, clock_seconds=None)
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            result = get_decisive_moments_breakdown(duck)
        finally:
            duck.close(); disk.close(); os.unlink(tmp)
        assert result["n_losses"] == 2
        assert result["median_move"] == 14  # int(median([8, 21])) == int(14.5)
        assert result["most_common_phase"] == "middlegame"  # tie -> Series.mode() sorts ascending
        buckets = {r["bucket"]: r["n_losses"] for r in result["by_move_bucket"]}
        assert buckets == {"6–10": 1, "21–25": 1}
        phases = {r["phase"]: r["n_losses"] for r in result["by_phase"]}
        assert phases == {"opening": 1, "middlegame": 1}
        assert result["by_clock_bucket"] == [{"bucket": "comfortable (30-60%)", "n_losses": 1}]
        assert result["n_no_clock_data"] == 1


