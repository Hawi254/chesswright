"""Integration tests for dashboard/data/points.py -- split from
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
        fen_before/is_player_move (color-derived default: white=player,
        matching this game's player_color='white') the scenario needs --
        unlisted fields default to NULL/0, matching a real ingest row
        that never reached a given analysis stage."""
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
                    piece, to_square, is_capture, material_delta, fen_before)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (game_id, ply, (ply + 1) // 2, color, mv.get("san", "e4"),
                  is_player_move, mv.get("win_prob_before"), mv.get("clock_seconds"),
                  mv.get("classification"), mv.get("cpl"), mv.get("eval_mate"),
                  mv.get("best_move_san"), mv.get("piece"), mv.get("to_square"),
                  mv.get("is_capture", 0), mv.get("material_delta"), mv.get("fen_before")))
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

    def test_monthly_points_uses_config_min_sample_size(self, monkeypatch):
        import pandas as pd
        from data import points as points_module
        from data.points import ledger
        monkeypatch.setattr(
            ledger, "get_config",
            lambda config_path=None: {"analytics": {"min_sample_size": 1}})
        classified = pd.DataFrame({
            "game_id": ["g1"], "period": ["2026.01"], "points": [1.0], "leaked": [0.0],
        })
        out = points_module.monthly_points(classified)
        assert len(out) == 1  # 1 game qualifies at min_sample_size=1


@pytest.mark.integration
class TestGetConversionDrillPositions:
    """dashboard/data/points.py's get_conversion_drill_positions -- the
    drill-card counterpart to get_failed_conversion_causes, scoped to
    hung_piece/blown_mate only (the two reasons with an unambiguous
    single ply). Reuses TestPointsData._seed_causes_game, now extended
    to also accept fen_before."""

    _seed_causes_game = TestPointsData._seed_causes_game

    def test_hung_piece_and_blown_mate_produce_positions(self, migrated_db):
        from data import points

        # Same scenarios as test_get_failed_conversion_causes_classifies_reasons,
        # with fen_before/best_move_san added to the qualifying ply of each.
        self._seed_causes_game(migrated_db, "fc_hang", "loss", [
            {"ply": 1, "win_prob_before": 0.50},
            {"ply": 3, "win_prob_before": 0.75},
            {"ply": 5, "win_prob_before": 0.75, "classification": "blunder", "cpl": 250,
             "san": "Qe5", "piece": "Q", "to_square": "e5",
             "fen_before": "fen_fc_hang", "best_move_san": "Nf3"},
            {"ply": 6, "is_player_move": 0, "is_capture": 1, "to_square": "e5",
             "material_delta": 900, "san": "Rxe5"},
            {"ply": 7, "win_prob_before": 0.10},
        ])
        self._seed_causes_game(migrated_db, "fc_mate", "draw", [
            {"ply": 1, "win_prob_before": 0.50},
            {"ply": 3, "win_prob_before": 0.75},
            {"ply": 5, "win_prob_before": 0.75, "eval_mate": 5,
             "san": "Nf3", "best_move_san": "Qxh7#", "fen_before": "fen_fc_mate"},
            {"ply": 7, "win_prob_before": 0.40},
        ])
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            df = points.get_conversion_drill_positions(duck, top_n=20).set_index("game_id")
            assert df.loc["fc_hang"].reason == "hung_piece"
            assert df.loc["fc_hang"].fen_before == "fen_fc_hang"
            assert df.loc["fc_hang"].best_move_san == "Nf3"
            assert df.loc["fc_mate"].reason == "blown_mate"
            assert df.loc["fc_mate"].fen_before == "fen_fc_mate"
            assert df.loc["fc_mate"].best_move_san == "Qxh7#"
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def test_time_pressure_and_other_excluded(self, migrated_db):
        """time_pressure and other failed-conversion games have no clean
        single-ply signal here (unlike get_failed_conversion_causes,
        which still classifies/counts them) -- they must produce NO row
        at all, the deliberate scope exclusion."""
        from data import points

        self._seed_causes_game(migrated_db, "fc_timepressure", "loss", [
            {"ply": 1, "win_prob_before": 0.50},
            {"ply": 3, "win_prob_before": 0.75},
            {"ply": 5, "win_prob_before": 0.70, "clock_seconds": 10},
            {"ply": 7, "win_prob_before": 0.20},
        ])
        self._seed_causes_game(migrated_db, "fc_other", "draw", [
            {"ply": 1, "win_prob_before": 0.50},
            {"ply": 3, "win_prob_before": 0.75},
            {"ply": 5, "win_prob_before": 0.72},
            {"ply": 7, "win_prob_before": 0.40},
        ])
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            df = points.get_conversion_drill_positions(duck, top_n=20)
            assert set(df.game_id) == set()
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def test_hang_beats_blown_mate(self, migrated_db):
        """Both a qualifying hang AND a qualifying blown mate exist after
        the win was reached -- hung_piece must win (same priority as
        get_failed_conversion_causes), and the returned position must be
        the HANG's fen_before/best_move_san, not the mate's."""
        from data import points

        self._seed_causes_game(migrated_db, "fc_priority", "loss", [
            {"ply": 1, "win_prob_before": 0.50},
            {"ply": 3, "win_prob_before": 0.75},
            {"ply": 5, "win_prob_before": 0.75, "eval_mate": 5,
             "san": "Nf3", "best_move_san": "Qxh7#", "fen_before": "fen_mate_ply"},
            {"ply": 7, "win_prob_before": 0.72, "classification": "blunder", "cpl": 250,
             "san": "Qe5", "piece": "Q", "to_square": "e5",
             "fen_before": "fen_hang_ply", "best_move_san": "Rd1"},
            {"ply": 8, "is_player_move": 0, "is_capture": 1, "to_square": "e5",
             "material_delta": 900, "san": "Rxe5"},
            {"ply": 9, "win_prob_before": 0.10},
        ])
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            df = points.get_conversion_drill_positions(duck, top_n=20).set_index("game_id")
            assert df.loc["fc_priority"].reason == "hung_piece"
            assert df.loc["fc_priority"].fen_before == "fen_hang_ply"
            assert df.loc["fc_priority"].best_move_san == "Rd1"
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def test_empty_ledger_returns_empty_dataframe(self, migrated_db):
        from data import points

        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            df = points.get_conversion_drill_positions(duck, top_n=20)
            assert df.empty
            assert list(df.columns) == [
                "game_id", "fen_before", "best_move_san", "actual_move_san", "reason"]
        finally:
            duck.close(); disk.close(); os.unlink(tmp)


@pytest.mark.integration
class TestGetDefenseDrillPositions:
    """dashboard/data/points.py's get_defense_drill_positions -- the
    Defense Trainer's drill-card source: the worst mistake/blunder (by
    cpl) made while win_prob_before <= EVEN_WP (0.45), scoped to games in
    the failed_hold/missed_swindle buckets. A different signal shape from
    get_conversion_drill_positions (raw cpl, not a hang/mate cause-ladder)
    but the same self-contained ledger-computation pattern, so reuses
    TestPointsData._seed_causes_game (ply-indexed win_prob_before/
    classification/cpl/fen_before/best_move_san rows)."""

    _seed_causes_game = TestPointsData._seed_causes_game

    def test_failed_hold_bucket_produces_qualifying_row(self, migrated_db):
        from data import points

        # Held even (wp 0.48 >= EVEN_WP at move 15) then a real blunder at
        # wp 0.30 (<= EVEN_WP, "already worse") before fading to a loss.
        # peak_wp stays < WINNING_WP (not conversion); never recovers from
        # <= LOST_WP so post_lost_peak_wp stays NULL (not swindle) ->
        # failed_hold.
        self._seed_causes_game(migrated_db, "def_hold", "loss", [
            {"ply": 1, "win_prob_before": 0.50},
            {"ply": 29, "win_prob_before": 0.48},   # move 15
            {"ply": 33, "win_prob_before": 0.30, "classification": "blunder", "cpl": 150,
             "san": "Re1", "fen_before": "fen_def_hold", "best_move_san": "Rd1"},
            {"ply": 41, "win_prob_before": 0.10},
        ])
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            classified = points.classify_points_ledger(points.get_points_ledger(duck))
            assert classified.set_index("game_id").loc["def_hold"].bucket == "failed_hold"

            df = points.get_defense_drill_positions(duck, top_n=20).set_index("game_id")
            row = df.loc["def_hold"]
            assert row.fen_before == "fen_def_hold"
            assert row.best_move_san == "Rd1"
            assert row.actual_move_san == "Re1"
            assert row.cpl == 150
            assert row.opening == "Test Opening"
            assert row.move_number == 17
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def test_missed_swindle_bucket_produces_qualifying_row(self, migrated_db):
        from data import points

        # Drops to wp 0.10 (<= LOST_WP), blunders again at wp 0.40 (<=
        # EVEN_WP, still "already worse"), then is handed a real chance
        # (wp 0.55 >= SWINDLE_CHANCE_WP, with a prior min <= LOST_WP) and
        # still loses -> missed_swindle.
        self._seed_causes_game(migrated_db, "def_swindle", "loss", [
            {"ply": 1, "win_prob_before": 0.50},
            {"ply": 11, "win_prob_before": 0.10},   # move 6, triggers prior_min <= LOST_WP
            {"ply": 15, "win_prob_before": 0.40, "classification": "blunder", "cpl": 180,
             "san": "Nb1", "fen_before": "fen_def_swindle", "best_move_san": "Nc3"},
            {"ply": 25, "win_prob_before": 0.55},   # the swindle chance
            {"ply": 35, "win_prob_before": 0.05},
        ])
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            classified = points.classify_points_ledger(points.get_points_ledger(duck))
            assert classified.set_index("game_id").loc["def_swindle"].bucket == "missed_swindle"

            df = points.get_defense_drill_positions(duck, top_n=20).set_index("game_id")
            row = df.loc["def_swindle"]
            assert row.fen_before == "fen_def_swindle"
            assert row.best_move_san == "Nc3"
            assert row.cpl == 180
            assert row.opening == "Test Opening"
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def test_non_qualifying_bucket_excluded_despite_low_wp_mistake(self, migrated_db):
        """A plain loss (never held even, never recovers into swindle
        range -> bucket 'none') must be excluded even though it has a
        low-win-prob (<= EVEN_WP) blunder somewhere in its curve."""
        from data import points

        self._seed_causes_game(migrated_db, "def_none", "loss", [
            {"ply": 1, "win_prob_before": 0.50},
            {"ply": 9, "win_prob_before": 0.30, "classification": "blunder", "cpl": 300,
             "san": "Qd3", "fen_before": "fen_def_none", "best_move_san": "Qd2"},
            {"ply": 19, "win_prob_before": 0.05},
            {"ply": 39, "win_prob_before": 0.02},
        ])
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            classified = points.classify_points_ledger(points.get_points_ledger(duck))
            assert classified.set_index("game_id").loc["def_none"].bucket == "none"

            df = points.get_defense_drill_positions(duck, top_n=20)
            assert "def_none" not in set(df.game_id)
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def test_multiple_qualifying_mistakes_highest_cpl_wins(self, migrated_db):
        """Two qualifying (win_prob_before <= EVEN_WP, mistake/blunder)
        rows in the same failed_hold game -- the higher-cpl one must win
        (rn=1 behavior), not the later or earlier one."""
        from data import points

        self._seed_causes_game(migrated_db, "def_multi", "loss", [
            {"ply": 1, "win_prob_before": 0.50},
            {"ply": 29, "win_prob_before": 0.48},   # move 15, held even
            {"ply": 33, "win_prob_before": 0.30, "classification": "blunder", "cpl": 150,
             "san": "Re1", "fen_before": "fen_def_multi_high", "best_move_san": "Rd1"},
            {"ply": 37, "win_prob_before": 0.20, "classification": "mistake", "cpl": 80,
             "san": "Qc3", "fen_before": "fen_def_multi_low", "best_move_san": "Qc2"},
            {"ply": 41, "win_prob_before": 0.10},
        ])
        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            classified = points.classify_points_ledger(points.get_points_ledger(duck))
            assert classified.set_index("game_id").loc["def_multi"].bucket == "failed_hold"

            df = points.get_defense_drill_positions(duck, top_n=20)
            matching = df[df.game_id == "def_multi"]
            assert len(matching) == 1
            assert matching.iloc[0].fen_before == "fen_def_multi_high"
            assert matching.iloc[0].cpl == 150
        finally:
            duck.close(); disk.close(); os.unlink(tmp)

    def test_empty_when_no_defense_games(self, migrated_db):
        from data import points

        duck, disk, tmp = _duck_from_conn(migrated_db)
        try:
            df = points.get_defense_drill_positions(duck, top_n=20)
            assert df.empty
            assert list(df.columns) == [
                "game_id", "fen_before", "best_move_san", "actual_move_san",
                "move_number", "opening", "cpl"]
        finally:
            duck.close(); disk.close(); os.unlink(tmp)


