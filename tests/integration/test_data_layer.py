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
