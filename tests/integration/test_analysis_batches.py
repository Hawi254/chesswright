"""Integration tests for dashboard/data/analysis_batches.py -- the Batch
Impact page's data layer (BRIEF §6u).

The critical thing under test is the before/after run-id boundary itself:
"before" = analysis_run_id IS NULL OR < run_id, "after" = IS NULL OR <=
run_id. Every scenario below seeds THREE analysis runs (1, 2, 3) plus a
handful of legacy NULL-run moves, and always checks a MIDDLE run (run 2)
specifically so a later run's moves (run 3) leaking into "before"/"after"
-- the exact bug the module docstring says the original ephemeral version
had -- would be caught, not just a "does it run" smoke test.
"""
import pathlib
import sqlite3
import sys

import pandas as pd
import pytest

REPO_ROOT = pathlib.Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "dashboard"))


def _insert_run(conn, run_id, games_analyzed=1, plies_analyzed=10):
    conn.execute("""
        INSERT INTO analysis_runs (id, started_at, ended_at, games_analyzed, plies_analyzed)
        VALUES (?, ?, ?, ?, ?)
    """, (run_id, f"2026-07-0{run_id}T10:00:00", f"2026-07-0{run_id}T10:05:00",
          games_analyzed, plies_analyzed))


def _insert_move(conn, game_id, ply, cpl, classification, analysis_run_id,
                  motif=None, is_brilliant=0):
    conn.execute("""
        INSERT INTO moves (game_id, ply, move_number, color, san, is_player_move,
                            cpl, classification, analysis_run_id, motif, is_brilliant_candidate)
        VALUES (?, ?, ?, 'w', 'e4', 1, ?, ?, ?, ?, ?)
    """, (game_id, ply, (ply + 1) // 2, cpl, classification, analysis_run_id,
          motif, is_brilliant))


def _seed_three_runs(conn, game_id="g1"):
    """One row per (phase-agnostic) move at each of NULL/run1/run2/run3 --
    used by the headline-delta tests, which don't need structure_ctx."""
    conn.execute("INSERT INTO games (id, white, black) VALUES (?, 'me', 'them')", (game_id,))
    _insert_move(conn, game_id, 2, 10, "good", None)
    _insert_move(conn, game_id, 4, 20, "inaccuracy", 1)
    _insert_move(conn, game_id, 6, 30, "blunder", 2, motif="fork")
    _insert_move(conn, game_id, 8, 40, "blunder", 3, motif="pin")
    conn.commit()


@pytest.mark.integration
class TestListAnalysisRuns:
    def test_empty_db(self, migrated_db):
        from data.analysis_batches import list_analysis_runs
        df = list_analysis_runs(migrated_db)
        assert df.empty

    def test_orders_most_recent_first(self, migrated_db):
        from data.analysis_batches import list_analysis_runs
        _insert_run(migrated_db, 1)
        _insert_run(migrated_db, 2)
        migrated_db.commit()
        df = list_analysis_runs(migrated_db)
        assert df["id"].tolist() == [2, 1]


@pytest.mark.integration
class TestBatchHeadlineDelta:
    def test_unknown_run_returns_none(self, migrated_db):
        from data.analysis_batches import get_batch_headline_delta
        assert get_batch_headline_delta(migrated_db, 999) is None

    def test_first_run_has_no_before_history(self, migrated_db):
        from data.analysis_batches import get_batch_headline_delta
        _insert_run(migrated_db, 1)
        migrated_db.execute("INSERT INTO games (id, white, black) VALUES ('g1', 'me', 'them')")
        _insert_move(migrated_db, "g1", 2, 20, "good", 1)
        migrated_db.commit()
        delta = get_batch_headline_delta(migrated_db, 1)
        assert delta["before_acpl"] is None
        assert delta["before_blunder_rate"] is None
        assert delta["after_acpl"] == pytest.approx(20.0)

    def test_middle_run_excludes_later_run_from_both_sides(self, migrated_db):
        """The core regression this module exists to fix: picking run 2
        after run 3 has since completed must not let run 3's moves leak
        into "before" (they're not < 2, so a naive != filter would wrongly
        include them) or "after" (a naive unconditional "all current
        moves" would wrongly include them too)."""
        from data.analysis_batches import get_batch_headline_delta
        for rid in (1, 2, 3):
            _insert_run(migrated_db, rid)
        _seed_three_runs(migrated_db)

        delta = get_batch_headline_delta(migrated_db, 2)
        # before = NULL(cpl=10) + run1(cpl=20) -> acpl 15.0, no blunders
        assert delta["before_acpl"] == pytest.approx(15.0)
        assert delta["before_blunder_rate"] == pytest.approx(0.0)
        # after = NULL + run1 + run2(cpl=30, blunder) -> acpl 20.0, 1/3 blunder
        assert delta["after_acpl"] == pytest.approx(20.0)
        assert delta["after_blunder_rate"] == pytest.approx(100.0 / 3)
        # this-run stats: exactly run2's one blunder, run3's blunder must not count
        assert delta["new_blunders"] == 1
        assert delta["top_motif"] == "fork"
        assert delta["annotated_this_run"] == 1  # run2's one cpl-bearing move

    def test_games_analyzed_zero_short_circuits(self, migrated_db):
        from data.analysis_batches import get_batch_headline_delta
        _insert_run(migrated_db, 1, games_analyzed=0)
        migrated_db.commit()
        delta = get_batch_headline_delta(migrated_db, 1)
        assert delta["games_analyzed"] == 0

    def test_not_yet_annotated_run_reports_zero(self, migrated_db):
        """A run can set analysis_run_id (worker.py) before annotate.run()
        ever computes cpl/classification for those same moves -- the real
        gap this field exists to surface (found live-verifying against the
        production DB, where the most recent run had exactly this shape)."""
        from data.analysis_batches import get_batch_headline_delta
        _insert_run(migrated_db, 1, games_analyzed=5)
        migrated_db.execute("INSERT INTO games (id, white, black) VALUES ('g1', 'me', 'them')")
        migrated_db.execute("""
            INSERT INTO moves (game_id, ply, move_number, color, san, is_player_move,
                                cpl, classification, analysis_run_id)
            VALUES ('g1', 2, 1, 'w', 'e4', 1, NULL, NULL, 1)
        """)
        migrated_db.commit()
        delta = get_batch_headline_delta(migrated_db, 1)
        assert delta["annotated_this_run"] == 0
        assert delta["games_analyzed"] == 5


@pytest.mark.integration
class TestMotifBatchDelta:
    def test_empty_db(self, migrated_db):
        from data.analysis_batches import get_motif_batch_delta
        df = get_motif_batch_delta(migrated_db, 1)
        assert df.empty

    def test_before_after_split_and_this_run_delta(self, migrated_db):
        from data.analysis_batches import get_motif_batch_delta
        for rid in (1, 2, 3):
            _insert_run(migrated_db, rid)
        migrated_db.execute("INSERT INTO games (id, white, black) VALUES ('g1', 'me', 'them')")
        _insert_move(migrated_db, "g1", 2, 40, "blunder", None, motif="fork")
        _insert_move(migrated_db, "g1", 4, 45, "mistake", 1, motif="fork")
        _insert_move(migrated_db, "g1", 6, 50, "blunder", 2, motif="fork")
        _insert_move(migrated_db, "g1", 8, 55, "blunder", 3, motif="fork")  # later run
        _insert_move(migrated_db, "g1", 10, 60, "blunder", 2, motif="pin")
        migrated_db.commit()

        df = get_motif_batch_delta(migrated_db, 2).set_index("motif")
        # fork: before = NULL + run1 = 2; after = NULL + run1 + run2 = 3 (run3 excluded)
        assert df.loc["fork"].n_before == 2
        assert df.loc["fork"].n_after == 3
        assert df.loc["fork"].n_this_run == 1
        # pin: only appears in run2 itself
        assert df.loc["pin"].n_before == 0
        assert df.loc["pin"].n_after == 1
        assert df.loc["pin"].n_this_run == 1

    def test_excludes_non_mistake_blunder_classifications(self, migrated_db):
        from data.analysis_batches import get_motif_batch_delta
        _insert_run(migrated_db, 1)
        migrated_db.execute("INSERT INTO games (id, white, black) VALUES ('g1', 'me', 'them')")
        _insert_move(migrated_db, "g1", 2, 5, "good", 1, motif="fork")
        migrated_db.commit()
        df = get_motif_batch_delta(migrated_db, 1)
        assert df.empty


@pytest.mark.integration
class TestNewBlundersThisRun:
    def test_only_this_runs_blunders(self, migrated_db):
        from data.analysis_batches import get_new_blunders_this_run
        _insert_run(migrated_db, 1)
        _insert_run(migrated_db, 2)
        migrated_db.execute("INSERT INTO games (id, white, black) VALUES ('g1', 'me', 'them')")
        _insert_move(migrated_db, "g1", 2, 40, "blunder", 1)
        _insert_move(migrated_db, "g1", 4, 90, "blunder", 1)
        _insert_move(migrated_db, "g1", 6, 999, "blunder", 2)  # different run
        _insert_move(migrated_db, "g1", 8, 500, "mistake", 1)  # not a blunder
        migrated_db.commit()
        df = get_new_blunders_this_run(migrated_db, 1)
        assert len(df) == 2
        assert df["cpl"].tolist() == [90, 40]  # ORDER BY cpl DESC

    def test_empty_when_no_blunders_this_run(self, migrated_db):
        from data.analysis_batches import get_new_blunders_this_run
        _insert_run(migrated_db, 1)
        migrated_db.commit()
        assert get_new_blunders_this_run(migrated_db, 1).empty


def _seed_structure_ctx(conn, rows):
    """rows: list of (game_id, middlegame_sig, endgame_sig, endgame_ply).
    Pre-creating the TEMP TABLE directly (rather than going through
    analytics.ensure_structure_ctx's real compute_structure_context, which
    replays actual games via python-chess) makes structure_ctx fully
    controlled for these tests -- ensure_structure_ctx's own idempotent
    fast path (checks sqlite_temp_master before rebuilding) then skips
    rebuilding it when the batch-delta functions call it."""
    conn.execute("""
        CREATE TEMP TABLE structure_ctx (
            game_id TEXT PRIMARY KEY, middlegame_sig TEXT, endgame_sig TEXT, endgame_ply INTEGER
        )
    """)
    conn.executemany("INSERT INTO structure_ctx VALUES (?,?,?,?)", rows)


@pytest.mark.integration
class TestPhaseAccuracyBatchDelta:
    """middlegame_ply=24 in the real config.yaml (get_config's default) --
    plies below that are 'opening' regardless of structure_ctx."""

    def test_empty_db(self, migrated_db):
        from data.analysis_batches import get_phase_accuracy_batch_delta
        _seed_structure_ctx(migrated_db, [])
        df = get_phase_accuracy_batch_delta(migrated_db, 1)
        assert df.empty

    def test_phase_split_excludes_later_run(self, migrated_db):
        from data.analysis_batches import get_phase_accuracy_batch_delta
        for rid in (1, 2, 3):
            _insert_run(migrated_db, rid)
        migrated_db.execute("INSERT INTO games (id, white, black) VALUES ('g1', 'me', 'them')")
        _seed_structure_ctx(migrated_db, [("g1", None, None, 60)])

        # opening (ply < 24): NULL, run1, run2, run3
        _insert_move(migrated_db, "g1", 2, 10, "good", None)
        _insert_move(migrated_db, "g1", 4, 20, "inaccuracy", 1)
        _insert_move(migrated_db, "g1", 6, 30, "mistake", 2)
        _insert_move(migrated_db, "g1", 8, 40, "blunder", 3)
        # middlegame (24 <= ply < 60)
        _insert_move(migrated_db, "g1", 30, 15, "good", None)
        _insert_move(migrated_db, "g1", 32, 25, "blunder", 1)
        _insert_move(migrated_db, "g1", 34, 35, "good", 2)
        _insert_move(migrated_db, "g1", 36, 45, "blunder", 3)
        # endgame (ply >= 60)
        _insert_move(migrated_db, "g1", 70, 5, "good", None)
        _insert_move(migrated_db, "g1", 72, 50, "blunder", 1)
        _insert_move(migrated_db, "g1", 74, 60, "good", 2)
        _insert_move(migrated_db, "g1", 76, 70, "blunder", 3)
        migrated_db.commit()

        df = get_phase_accuracy_batch_delta(migrated_db, 2).set_index("phase")

        opening = df.loc["opening"]
        assert opening.n_moves_this_run == 1                       # run2's one opening move
        assert opening.before_acpl == pytest.approx(15.0)           # NULL(10) + run1(20)
        assert opening.after_acpl == pytest.approx(20.0)            # + run2(30), run3 excluded
        assert opening.before_blunder_rate == pytest.approx(0.0)
        assert opening.after_blunder_rate == pytest.approx(0.0)     # run2's move is 'mistake'

        middlegame = df.loc["middlegame"]
        assert middlegame.n_moves_this_run == 1
        assert middlegame.before_acpl == pytest.approx(20.0)        # NULL(15) + run1(25)
        assert middlegame.after_acpl == pytest.approx(25.0)         # + run2(35)
        assert middlegame.before_blunder_rate == pytest.approx(50.0)  # run1's move is a blunder
        assert middlegame.after_blunder_rate == pytest.approx(100.0 / 3)

        endgame = df.loc["endgame"]
        assert endgame.n_moves_this_run == 1
        assert endgame.before_acpl == pytest.approx(27.5)           # NULL(5) + run1(50)
        assert endgame.after_acpl == pytest.approx(115.0 / 3)       # + run2(60)


@pytest.mark.integration
class TestEndgameTypeBatchDelta:
    def test_empty_db(self, migrated_db):
        from data.analysis_batches import get_endgame_type_batch_delta
        _seed_structure_ctx(migrated_db, [])
        df = get_endgame_type_batch_delta(migrated_db, 1)
        assert df.empty

    def test_win_loss_not_included_only_acpl(self, migrated_db):
        """Confirms the module's deliberate scope cut: the returned frame
        has no win_pct/draw_pct/loss_pct columns at all (see module
        docstring -- those aren't engine-batch-sensitive)."""
        from data.analysis_batches import get_endgame_type_batch_delta
        for rid in (1, 2):
            _insert_run(migrated_db, rid)
        migrated_db.execute("INSERT INTO games (id, white, black) VALUES ('g1', 'me', 'them')")
        _seed_structure_ctx(migrated_db, [("g1", None, "R1P5vP4", 50)])  # -> "Rook"
        _insert_move(migrated_db, "g1", 50, 20, "good", None)
        _insert_move(migrated_db, "g1", 52, 40, "blunder", 1)
        _insert_move(migrated_db, "g1", 54, 60, "good", 2)
        migrated_db.commit()

        df = get_endgame_type_batch_delta(migrated_db, 1)
        assert list(df.columns) == [
            "endgame_type", "n_moves_this_run", "before_acpl", "after_acpl",
            "before_blunder_rate", "after_blunder_rate",
        ]
        row = df[df.endgame_type == "Rook"].iloc[0]
        assert row.n_moves_this_run == 1
        assert row.before_acpl == pytest.approx(20.0)
        assert row.after_acpl == pytest.approx(30.0)                # NULL(20) + run1(40)
        assert row.before_blunder_rate == pytest.approx(0.0)
        assert row.after_blunder_rate == pytest.approx(50.0)  # 1 of 2 (NULL + run1)

    def test_weighted_across_multiple_sigs_same_broad_type(self, migrated_db):
        """Two different endgame_sig values that both map to 'Rook' must
        be weight-combined (sum/sum), not averaged as two equal buckets."""
        from data.analysis_batches import get_endgame_type_batch_delta
        _insert_run(migrated_db, 1)
        migrated_db.execute("INSERT INTO games (id, white, black) VALUES ('g1', 'me', 'them')")
        migrated_db.execute("INSERT INTO games (id, white, black) VALUES ('g2', 'me', 'them')")
        _seed_structure_ctx(migrated_db, [
            ("g1", None, "R1P5vP4", 50),   # -> Rook
            ("g2", None, "R1P2vR1P1", 50),  # -> Rook
        ])
        _insert_move(migrated_db, "g1", 50, 10, "good", 1)
        _insert_move(migrated_db, "g1", 52, 10, "good", 1)
        _insert_move(migrated_db, "g1", 54, 10, "good", 1)
        _insert_move(migrated_db, "g2", 50, 100, "blunder", 1)
        migrated_db.commit()

        df = get_endgame_type_batch_delta(migrated_db, 1)
        row = df[df.endgame_type == "Rook"].iloc[0]
        # (10+10+10+100) / 4 = 32.5, not (10+100)/2 = 55
        assert row.after_acpl == pytest.approx(32.5)


@pytest.mark.integration
class TestBatchCounter:
    def test_empty_db(self, migrated_db):
        from data.analysis_batches import get_batch_counter
        counter = get_batch_counter(migrated_db)
        assert counter == {"total_batches": 0, "total_games_analyzed": 0}

    def test_sums_across_all_runs_regardless_of_annotation(self, migrated_db):
        """Deliberately independent of any run_id boundary -- unlike every
        other function in this module, this is a lifetime tally, not a
        before/after split, so a run with zero annotated moves still
        counts toward the total (it was still a real batch)."""
        from data.analysis_batches import get_batch_counter
        _insert_run(migrated_db, 1, games_analyzed=20)
        _insert_run(migrated_db, 2, games_analyzed=5)
        _insert_run(migrated_db, 3, games_analyzed=0)  # e.g. a failed/empty run
        migrated_db.commit()
        counter = get_batch_counter(migrated_db)
        assert counter == {"total_batches": 3, "total_games_analyzed": 25}


@pytest.mark.integration
class TestBatchTrend:
    def test_empty_db(self, migrated_db):
        from data.analysis_batches import get_batch_trend
        df = get_batch_trend(migrated_db)
        assert df.empty

    def test_null_baseline_folds_into_first_run(self, migrated_db):
        from data.analysis_batches import get_batch_trend
        _insert_run(migrated_db, 1)
        migrated_db.execute("INSERT INTO games (id, white, black) VALUES ('g1', 'me', 'them')")
        _insert_move(migrated_db, "g1", 2, 10, "good", None)   # pre-migration baseline
        _insert_move(migrated_db, "g1", 4, 30, "good", 1)      # run1's own move
        migrated_db.commit()

        df = get_batch_trend(migrated_db).set_index("run_id")
        assert df.loc[1].this_run_acpl == pytest.approx(30.0)      # run1's own move only
        assert df.loc[1].cumulative_acpl == pytest.approx(20.0)    # NULL(10) + run1(30)

    def test_single_annotated_run_not_enough_for_a_trend_line(self, migrated_db):
        """batch_impact_view._render_trend_section guards on
        len(df.dropna(subset=["cumulative_acpl"])) < 2 before drawing a
        chart -- this is the data-side half of that check: a lone
        annotated run must produce exactly one non-null cumulative row,
        not two, so the view's guard actually fires."""
        from data.analysis_batches import get_batch_trend
        _insert_run(migrated_db, 1)
        migrated_db.execute("INSERT INTO games (id, white, black) VALUES ('g1', 'me', 'them')")
        _insert_move(migrated_db, "g1", 2, 30, "good", 1)
        migrated_db.commit()
        df = get_batch_trend(migrated_db)
        assert len(df.dropna(subset=["cumulative_acpl"])) == 1

    def test_unannotated_run_gets_nan_and_carries_cumulative_forward(self, migrated_db):
        from data.analysis_batches import get_batch_trend
        _insert_run(migrated_db, 1)
        _insert_run(migrated_db, 2)
        migrated_db.execute("INSERT INTO games (id, white, black) VALUES ('g1', 'me', 'them')")
        _insert_move(migrated_db, "g1", 2, 20, "good", 1)
        # run2 has moves attached (worker.py already ran) but not yet annotated
        # -- cpl/classification are NULL until the separate annotate.run() pass.
        migrated_db.execute("""
            INSERT INTO moves (game_id, ply, move_number, color, san, is_player_move,
                                cpl, classification, analysis_run_id)
            VALUES ('g1', 4, 2, 'w', 'e4', 1, NULL, NULL, 2)
        """)
        migrated_db.commit()

        df = get_batch_trend(migrated_db).set_index("run_id")
        # None becomes NaN once inside a numeric DataFrame column -- same
        # None/NaN duality _arrow() already handles for the headline dict.
        assert pd.isna(df.loc[2].this_run_acpl)
        assert pd.isna(df.loc[2].this_run_blunder_rate)
        assert df.loc[2].cumulative_acpl == pytest.approx(20.0)  # unchanged from run1

    def test_multi_run_cumulative_and_isolated_values_dont_leak(self, migrated_db):
        """Mirrors this module's core regression class of bug (§6u): run2's
        this_run_acpl must reflect only run2's own moves, and run1's
        cumulative_acpl must not see run2's or run3's moves at all."""
        from data.analysis_batches import get_batch_trend
        for rid in (1, 2, 3):
            _insert_run(migrated_db, rid)
        migrated_db.execute("INSERT INTO games (id, white, black) VALUES ('g1', 'me', 'them')")
        _insert_move(migrated_db, "g1", 2, 40, "blunder", 1)
        _insert_move(migrated_db, "g1", 4, 20, "good", 2)
        _insert_move(migrated_db, "g1", 6, 10, "good", 2)
        _insert_move(migrated_db, "g1", 8, 100, "blunder", 3)
        migrated_db.commit()

        df = get_batch_trend(migrated_db).set_index("run_id")
        assert df.loc[1].this_run_acpl == pytest.approx(40.0)
        assert df.loc[1].cumulative_acpl == pytest.approx(40.0)
        assert df.loc[2].this_run_acpl == pytest.approx(15.0)          # (20+10)/2, not incl. run1/3
        assert df.loc[2].cumulative_acpl == pytest.approx(70.0 / 3)    # 40+20+10 over 3 moves
        assert df.loc[2].this_run_blunder_rate == pytest.approx(0.0)
        assert df.loc[3].this_run_acpl == pytest.approx(100.0)
        assert df.loc[3].cumulative_blunder_rate == pytest.approx(50.0)  # 2 of 4 moves are blunders

    def test_ascending_order_regardless_of_list_analysis_runs_default(self, migrated_db):
        from data.analysis_batches import get_batch_trend
        _insert_run(migrated_db, 1)
        _insert_run(migrated_db, 2)
        migrated_db.commit()
        df = get_batch_trend(migrated_db)
        assert df["run_id"].tolist() == [1, 2]


@pytest.mark.integration
class TestBatchRecordFlags:
    def test_first_annotated_run_is_not_a_record(self, migrated_db):
        from data.analysis_batches import get_batch_record_flags
        _insert_run(migrated_db, 1)
        migrated_db.execute("INSERT INTO games (id, white, black) VALUES ('g1', 'me', 'them')")
        _insert_move(migrated_db, "g1", 2, 30, "good", 1)
        migrated_db.commit()
        flags = get_batch_record_flags(migrated_db, 1)
        assert flags["is_best_acpl"] is False
        assert flags["is_best_blunder_rate"] is False

    def test_strictly_better_second_run_is_a_record(self, migrated_db):
        from data.analysis_batches import get_batch_record_flags
        _insert_run(migrated_db, 1)
        _insert_run(migrated_db, 2)
        migrated_db.execute("INSERT INTO games (id, white, black) VALUES ('g1', 'me', 'them')")
        _insert_move(migrated_db, "g1", 2, 30, "good", 1)
        _insert_move(migrated_db, "g1", 4, 10, "good", 2)
        migrated_db.commit()

        flags = get_batch_record_flags(migrated_db, 2)
        assert flags["is_best_acpl"] is True
        assert flags["prior_best_acpl"] == pytest.approx(30.0)
        assert flags["prior_best_acpl_run_id"] == 1

    def test_worse_second_run_is_not_a_record(self, migrated_db):
        from data.analysis_batches import get_batch_record_flags
        _insert_run(migrated_db, 1)
        _insert_run(migrated_db, 2)
        migrated_db.execute("INSERT INTO games (id, white, black) VALUES ('g1', 'me', 'them')")
        _insert_move(migrated_db, "g1", 2, 10, "good", 1)
        _insert_move(migrated_db, "g1", 4, 30, "good", 2)
        migrated_db.commit()

        flags = get_batch_record_flags(migrated_db, 2)
        assert flags["is_best_acpl"] is False

    def test_reopening_old_run_unaffected_by_later_runs(self, migrated_db):
        """The same boundary discipline as every before/after split in this
        module: run2's own record status must be judged only against runs
        <= 2, even though run3 (not yet completed when run2 finished) is
        an even bigger improvement."""
        from data.analysis_batches import get_batch_record_flags
        for rid in (1, 2, 3):
            _insert_run(migrated_db, rid)
        migrated_db.execute("INSERT INTO games (id, white, black) VALUES ('g1', 'me', 'them')")
        _insert_move(migrated_db, "g1", 2, 30, "good", 1)
        _insert_move(migrated_db, "g1", 4, 10, "good", 2)   # beats run1
        _insert_move(migrated_db, "g1", 6, 1, "good", 3)    # beats run2, shouldn't count here
        migrated_db.commit()

        flags = get_batch_record_flags(migrated_db, 2)
        assert flags["is_best_acpl"] is True
        assert flags["prior_best_acpl"] == pytest.approx(30.0)  # only run1, not run3's 1

    def test_acpl_and_blunder_rate_records_are_independent(self, migrated_db):
        """A run can set a personal-best ACPL without also setting a
        personal-best blunder rate (or vice versa) -- two separate flags,
        not one combined "improved" boolean."""
        from data.analysis_batches import get_batch_record_flags
        _insert_run(migrated_db, 1)
        _insert_run(migrated_db, 2)
        migrated_db.execute("INSERT INTO games (id, white, black) VALUES ('g1', 'me', 'them')")
        # run1: one big non-blunder mistake -> high ACPL, 0% blunder rate
        _insert_move(migrated_db, "g1", 2, 80, "mistake", 1)
        # run2: lower ACPL overall, but includes an actual blunder
        _insert_move(migrated_db, "g1", 4, 20, "good", 2)
        _insert_move(migrated_db, "g1", 6, 20, "blunder", 2)
        migrated_db.commit()

        flags = get_batch_record_flags(migrated_db, 2)
        assert flags["this_run_acpl"] == pytest.approx(20.0)
        assert flags["is_best_acpl"] is True             # 20 < 80
        assert flags["is_best_blunder_rate"] is False     # 50% > run1's 0%
