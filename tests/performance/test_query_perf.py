"""
Performance benchmarks using pytest-benchmark.

Run explicitly:  pytest -m perf --benchmark-only

These tests measure:
1. Individual data-layer query functions against a synthetic 1000-game DB
2. The Insights combined query vs the old 4-scan equivalent
3. Migration time for a fresh DB

They are excluded from the normal test run (marked `perf`) to keep CI fast.
Each benchmark asserts an upper-bound time limit using benchmark.pedantic() —
the limits are intentionally generous (5–10× the expected fast-path time) so
the tests pass on developer hardware without being so tight they flake on CI.
"""
import os
import pathlib
import sqlite3
import sys
import tempfile
import time
import pytest

REPO_ROOT = pathlib.Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "dashboard"))


# ---------------------------------------------------------------------------
# Synthetic 1000-game DB fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def large_db(tmp_path_factory):
    """
    An on-disk SQLite DB with 1000 synthetic games and 30 moves each.
    Scope=module so it's built once and reused across all perf tests.
    """
    import migrate as migrate_mod
    tmp = tmp_path_factory.mktemp("perf") / "perf_test.db"
    migrate_mod.migrate(str(tmp))
    conn = sqlite3.connect(str(tmp))
    conn.execute("PRAGMA journal_mode = WAL")

    # Insert 1000 games
    games = []
    for i in range(1000):
        gid = f"perf{i:06d}"
        color = "white" if i % 2 == 0 else "black"
        outcome = ["win", "loss", "draw"][i % 3]
        tc = ["blitz", "rapid", "bullet"][i % 3]
        base = [180, 600, 60][i % 3]
        opening = ["Italian Game", "Sicilian Defense", "French Defense",
                   "English Opening", "Queen's Gambit"][i % 5]
        games.append((
            gid, "TestPlayer", "Opponent", outcome, color,
            1500 + (i % 100), 1480 + (i % 80), 5 if outcome == "win" else -5,
            60, f"{base}+0", tc, opening, "done",
            f"2025-{(i % 12)+1:02d}-01", 2025, (i % 12) + 1,
        ))
    conn.executemany("""
        INSERT INTO games (id, white, black, outcome_for_player, player_color,
                           player_rating, opponent_rating, player_rating_change, num_plies,
                           time_control_raw, time_control_category, opening_family,
                           analysis_status, utc_date, year, month)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, games)

    # Insert 30 moves per game (30,000 total)
    moves = []
    classifications = ["best", "excellent", "good", "inaccuracy", "mistake", "blunder"]
    pieces = ["P", "N", "B", "R", "Q", "K"]
    for i, (gid, *_) in enumerate(games):
        for ply in range(1, 31):
            clk = max(0, 180 - ply * 5)
            time_spent = 5.0
            is_player = 1 if ply % 2 == (1 if games[i][4] == "white" else 0) else 0
            cpl = (ply * 3) % 50
            cls = classifications[cpl % len(classifications)]
            piece = pieces[ply % len(pieces)]
            wp = 0.5 + (cpl / 200.0) * (1 if is_player else -1)
            moves.append((
                gid, ply, (ply + 1) // 2,
                "w" if ply % 2 == 1 else "b",
                "e4", "e2e4",
                0, 20, cpl, cls,
                min(1.0, max(0.0, wp)), min(1.0, max(0.0, wp - 0.01)),
                piece, is_player,
                clk, time_spent,
                i % 20,          # sharpness INTEGER column
                i % 10,          # material_delta INTEGER column
            ))
    conn.executemany("""
        INSERT INTO moves (game_id, ply, move_number, color, san, uci,
                           eval_cp, eval_mate, cpl, classification,
                           win_prob_before, win_prob_after,
                           piece, is_player_move,
                           clock_seconds, time_spent_seconds,
                           sharpness, material_delta)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, moves)

    conn.commit()
    conn.close()
    return str(tmp)


def _duck(db_path):
    import duckdb
    duck = duckdb.connect(":memory:")
    duck.execute(f"ATTACH '{db_path}' AS db (TYPE SQLITE, READ_ONLY TRUE)")
    return duck


def _sqlite(db_path):
    return sqlite3.connect(db_path)


# ---------------------------------------------------------------------------
# Query benchmarks
# ---------------------------------------------------------------------------

@pytest.mark.perf
class TestQueryPerformance:

    def test_get_openings_table_under_500ms(self, large_db, benchmark):
        from data.openings import get_openings_table
        duck = _duck(large_db)
        conn = _sqlite(large_db)

        def _run():
            df = get_openings_table(duck, conn, min_games=1)
            assert df is not None

        result = benchmark.pedantic(_run, rounds=5, warmup_rounds=1)
        assert benchmark.stats["mean"] < 0.5, \
            f"get_openings_table mean={benchmark.stats['mean']:.3f}s > 500ms limit"

    def test_get_most_repeated_positions_under_500ms(self, large_db, benchmark):
        # Takes sqlite_conn since the 2026-07-04 materialization -- reads
        # repeated_positions_cache, built once here the way the view layer's
        # ensure_* call does (with the test's own min_games floor).
        from data.openings import get_most_repeated_positions
        import analytics
        conn = _sqlite(large_db)
        analytics.ensure_repeated_positions_cache(conn, min_games=1)

        def _run():
            df = get_most_repeated_positions(conn, min_games=1)
            return df

        benchmark.pedantic(_run, rounds=5, warmup_rounds=1)
        assert benchmark.stats["mean"] < 0.5

    def test_get_motif_breakdown_under_200ms(self, large_db, benchmark):
        # takes sqlite_conn since migration 0031 (partial motif index)
        from data.tactical import get_motif_breakdown
        conn = _sqlite(large_db)

        def _run():
            df = get_motif_breakdown(conn)
            return df

        benchmark.pedantic(_run, rounds=5, warmup_rounds=1)
        assert benchmark.stats["mean"] < 0.2

    def test_get_progress_by_month_under_500ms(self, large_db, benchmark):
        from data.overview import get_progress_by_month
        duck = _duck(large_db)

        def _run():
            df = get_progress_by_month(duck)
            return df

        benchmark.pedantic(_run, rounds=5, warmup_rounds=1)
        assert benchmark.stats["mean"] < 0.5

    def test_insights_combined_query_under_2s(self, large_db, benchmark):
        """The Insights combined query (4 correlations in 1 scan) must stay < 2s.

        This was the bottleneck fixed in §6b: the old 4-scan version took 10-12s
        against 1,497 analyzed games; the new combined version should be well
        under 2s even on the 1000-game test DB.
        """
        from data.insights import _fetch_move_correlates
        duck = _duck(large_db)

        def _run():
            df = _fetch_move_correlates(duck)
            return df

        benchmark.pedantic(_run, rounds=5, warmup_rounds=1)
        assert benchmark.stats["mean"] < 2.0, \
            f"Insights combined query mean={benchmark.stats['mean']:.3f}s > 2s limit"


@pytest.mark.perf
class TestMigrationPerformance:
    def test_all_migrations_under_500ms(self, benchmark):
        """22 migrations on a fresh in-memory DB must run in < 500ms."""
        def _run():
            conn = sqlite3.connect(":memory:")
            for sql_file in sorted((REPO_ROOT / "migrations").glob("*.sql")):
                conn.executescript(sql_file.read_text())
            conn.commit()
            conn.close()

        benchmark.pedantic(_run, rounds=10, warmup_rounds=2)
        assert benchmark.stats["mean"] < 0.5


@pytest.mark.perf
class TestAnnotationPerformance:
    def test_annotate_100_games_under_10s(self, tmp_path, benchmark):
        """annotate.run() over 100 games with mock evals (no engine) < 10s.

        The bottleneck is the per-game SQL: each game needs O(moves) reads
        and writes.  With 100 games × 30 moves = 3000 operations, 10s is
        a very generous limit (expect < 2s on modern hardware).
        """
        import ingest
        import annotate

        import migrate as migrate_mod
        db_path = str(tmp_path / "bench_annotate.db")
        migrate_mod.migrate(db_path)
        conn = sqlite3.connect(db_path)

        games = [(f"ann{i:04d}", "TestPlayer", "Opp", "win", "white",
                  1500, 1480, 5, 60, "180+0", "blitz", "Italian Game", "done",
                  "2025-01-01", 2025, 1)
                 for i in range(100)]
        conn.executemany("""
            INSERT INTO games (id, white, black, outcome_for_player, player_color,
                               player_rating, opponent_rating, player_rating_change, num_plies,
                               time_control_raw, time_control_category, opening_family,
                               analysis_status, utc_date, year, month)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, games)

        moves = []
        for gid, *_ in games:
            for ply in range(1, 31):
                moves.append((gid, ply, (ply + 1) // 2,
                               "w" if ply % 2 == 1 else "b",
                               "e4", "e2e4", 10, None,
                               1 if ply % 2 == (1 if True else 0) else 0))
        conn.executemany("""
            INSERT INTO moves (game_id, ply, move_number, color, san, uci,
                               eval_cp, eval_mate, is_player_move)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, moves)
        conn.commit()
        conn.close()

        def _run():
            annotate.run(
                db_path=db_path,
                mate_cap=1500,
                thresholds={"excellent": 0.02, "good": 0.05, "inaccuracy": 0.10,
                            "mistake": 0.20, "blunder": 0.30},
                brilliant_threshold=None,
                puzzle_cfg={},
                streak_cfg={},
                game_id=None,
            )

        benchmark.pedantic(_run, rounds=1, warmup_rounds=0)
        assert benchmark.stats["mean"] < 10.0, \
            f"annotate.run(100 games) mean={benchmark.stats['mean']:.3f}s > 10s limit"
