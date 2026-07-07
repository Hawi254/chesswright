"""Integration tests for backfill_batch_eval_cache.py -- the one-time
backfill that seeds `batch_eval_cache` (migrations/0033) from `moves` rows
analyzed before the eval-reuse-cache feature existed (see worker.py's
fetch_cached_eval()/store_cached_eval() and REUSE_EVAL_MAX_PLY, and
tests/integration/test_eval_reuse_cache.py for the forward-path tests).

Reuses test_eval_reuse_cache.py's fixtures/helpers (FakeAnalysisEngine,
_with_runs, _insert_game_with_moves, _game_row, _moves_row) rather than
reinventing them, and follows test_pipeline.py's
`import backfill_mod; backfill_mod.backfill(db_path)` pattern for testing
a standalone backfill script directly.
"""
import json
import pathlib
import sqlite3
import sys

import chess
import chess.engine
import pytest

REPO_ROOT = pathlib.Path(__file__).parent.parent.parent
FIXTURES = pathlib.Path(__file__).parent.parent / "fixtures"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "dashboard"))

import worker
from worker import lines_payload_from_engine_lines
import backfill_batch_eval_cache as backfill_mod

from tests.integration.test_eval_reuse_cache import (
    FakeAnalysisEngine,
    _with_runs,
    _insert_game_with_moves,
    _game_row,
    _moves_row,
)


def _populate_fen_before(conn, game_id):
    """_insert_game_with_moves() (borrowed from test_eval_reuse_cache.py) is a
    fast stand-in for ingest.py and, like analyze_game() itself, never reads or
    writes the `moves.fen_before` column -- analyze_game() derives fen_before
    from its own in-memory `board`, not the DB column. In real production data
    ingest.py always populates fen_before before analysis ever runs; the
    backfill script (unlike analyze_game()) depends on that persisted column,
    so tests using the fake insert helper must populate it explicitly, the
    same way ingest.py would have."""
    board = chess.Board()
    rows = conn.execute(
        "SELECT id, san FROM moves WHERE game_id=? ORDER BY ply", (game_id,)).fetchall()
    for move_id, san in rows:
        conn.execute("UPDATE moves SET fen_before=? WHERE id=?", (board.fen(), move_id))
        board.push_san(san)
    conn.commit()


@pytest.mark.integration
class TestBackfillIdempotency:
    def test_running_twice_is_a_no_op(self, migrated_db_path):
        conn = sqlite3.connect(migrated_db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        conn = _with_runs(conn)
        # _with_runs() only sets started_at -- the backfill's cache-key join
        # needs analysis_runs.depth/multipv populated too (matching the
        # depth=6, multipv=1 this test's analyze_game() calls use below).
        conn.execute("UPDATE analysis_runs SET depth=6, multipv=1 WHERE id=1")
        conn.commit()
        _insert_game_with_moves(conn, "g1", ["e4", "e5", "Nf3"])
        _insert_game_with_moves(conn, "g2", ["e4", "e5", "Nf3"])  # exact repeat line
        _populate_fen_before(conn, "g1")
        _populate_fen_before(conn, "g2")
        engine = FakeAnalysisEngine()
        worker.analyze_game(conn, engine, _game_row(conn, "g1"), depth=6, multipv=1, pv_max_len=10,
                             commit_every_n_moves=1, engine_version="FakeEngine", run_id=1,
                             reuse_evals=False)
        worker.analyze_game(conn, engine, _game_row(conn, "g2"), depth=6, multipv=1, pv_max_len=10,
                             commit_every_n_moves=1, engine_version="FakeEngine", run_id=1,
                             reuse_evals=False)
        conn.close()

        first_stats = backfill_mod.backfill(migrated_db_path)
        conn = sqlite3.connect(migrated_db_path)
        first_pass = conn.execute(
            "SELECT fen_before, engine_version, requested_depth, multipv, lines_json "
            "FROM batch_eval_cache ORDER BY fen_before, engine_version, requested_depth, multipv"
        ).fetchall()
        first_count = len(first_pass)
        assert first_count > 0
        conn.close()

        # Returned stats must match what backfill() actually did on this
        # first (non-idempotent) pass: every group seen was newly inserted.
        assert first_stats.groups_seen == first_count
        assert first_stats.inserted == first_count
        assert first_stats.already_present == 0
        assert first_stats.candidates_seen > 0

        second_stats = backfill_mod.backfill(migrated_db_path)
        conn = sqlite3.connect(migrated_db_path)
        second_pass = conn.execute(
            "SELECT fen_before, engine_version, requested_depth, multipv, lines_json "
            "FROM batch_eval_cache ORDER BY fen_before, engine_version, requested_depth, multipv"
        ).fetchall()
        conn.close()
        assert second_pass == first_pass
        assert len(second_pass) == first_count

        # Second (idempotent) pass: same groups seen, but nothing new
        # inserted -- all already present from the first pass.
        assert second_stats.groups_seen == first_stats.groups_seen
        assert second_stats.candidates_seen == first_stats.candidates_seen
        assert second_stats.inserted == 0
        assert second_stats.already_present == second_stats.groups_seen


@pytest.mark.integration
class TestReshapeCorrectness:
    def test_backfilled_payload_matches_lines_payload_from_engine_lines_shape(self, migrated_db_path):
        """Builds a synthetic moves+move_lines+analysis_runs fixture with known
        values (bypassing analyze_game() entirely) and confirms the backfilled
        lines_json round-trips to exactly what
        lines_payload_from_engine_lines() would have produced for the same
        engine output."""
        conn = sqlite3.connect(migrated_db_path)
        conn.execute("PRAGMA foreign_keys = ON")

        conn.execute("INSERT INTO analysis_runs (id, started_at, depth, multipv) VALUES (1, 't0', 8, 2)")
        conn.execute("""
            INSERT INTO games (id, white, black, num_plies, last_analyzed_ply, analysis_status, queue_order)
            VALUES ('g1', 'W', 'B', 1, 1, 'done', 0)
        """)
        board = chess.Board()
        fen_before = board.fen()
        conn.execute("""
            INSERT INTO moves (id, game_id, ply, move_number, color, san, fen_before, engine_version,
                                analysis_run_id, eval_source)
            VALUES (1, 'g1', 1, 1, 'white', 'e4', ?, 'Stockfish 16', 1, 'engine')
        """, (fen_before,))

        # Build known engine-shaped `lines` and derive the expected payload the
        # SAME way the forward path does, via lines_payload_from_engine_lines().
        legal = list(board.legal_moves)
        lines = [
            {"score": chess.engine.PovScore(chess.engine.Cp(35), board.turn), "pv": [legal[0]]},
            {"score": chess.engine.PovScore(chess.engine.Cp(20), board.turn), "pv": [legal[1]]},
        ]
        expected_payload = lines_payload_from_engine_lines(lines, board, board.turn, pv_max_len=10)

        for entry in expected_payload:
            conn.execute("""
                INSERT INTO move_lines (move_id, pv_rank, eval_cp, eval_mate, move_san, pv_json, score_is_exact)
                VALUES (1, ?, ?, ?, ?, ?, ?)
            """, (entry["pv_rank"], entry["eval_cp"], entry["eval_mate"], entry["move_san"],
                  json.dumps(entry["pv_san"]), entry["score_is_exact"]))
        conn.commit()
        conn.close()

        backfill_mod.backfill(migrated_db_path)

        conn = sqlite3.connect(migrated_db_path)
        row = conn.execute("""
            SELECT lines_json FROM batch_eval_cache
            WHERE fen_before=? AND engine_version='Stockfish 16' AND requested_depth=8 AND multipv=2
        """, (fen_before,)).fetchone()
        conn.close()
        assert row is not None
        backfilled_payload = json.loads(row[0])
        assert backfilled_payload == expected_payload


@pytest.mark.integration
class TestPlyCutoffRespected:
    def test_move_past_cutoff_is_not_backfilled(self, migrated_db_path):
        conn = sqlite3.connect(migrated_db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("INSERT INTO analysis_runs (id, started_at, depth, multipv) VALUES (1, 't0', 8, 1)")
        conn.execute("""
            INSERT INTO games (id, white, black, num_plies, last_analyzed_ply, analysis_status, queue_order)
            VALUES ('g1', 'W', 'B', 1, 1, 'done', 0)
        """)
        over_cutoff_ply = worker.REUSE_EVAL_MAX_PLY + 1
        board = chess.Board()
        fen_before = board.fen()
        conn.execute("""
            INSERT INTO moves (id, game_id, ply, move_number, color, san, fen_before, engine_version,
                                analysis_run_id, eval_source)
            VALUES (1, 'g1', ?, 1, 'white', 'e4', ?, 'Stockfish 16', 1, 'engine')
        """, (over_cutoff_ply, fen_before))
        conn.execute("""
            INSERT INTO move_lines (move_id, pv_rank, eval_cp, eval_mate, move_san, pv_json, score_is_exact)
            VALUES (1, 1, 35, NULL, 'e4', '["e4"]', 1)
        """)
        conn.commit()
        conn.close()

        backfill_mod.backfill(migrated_db_path)

        conn = sqlite3.connect(migrated_db_path)
        count = conn.execute("SELECT COUNT(*) FROM batch_eval_cache").fetchone()[0]
        conn.close()
        assert count == 0, "a move past REUSE_EVAL_MAX_PLY must never produce a cache row"


@pytest.mark.integration
class TestDeterministicFirstWins:
    def test_lower_id_wins_and_holds_across_repeated_runs(self, migrated_db_path):
        """Two moves rows analyzed under the identical (fen_before,
        engine_version, depth, multipv) key but with different eval_cp/
        best_move (simulating lazy-SMP nondeterminism) -- the backfilled
        cache row must always match the LOWER id's data, both on first run
        and after a second (idempotent) run."""
        conn = sqlite3.connect(migrated_db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("INSERT INTO analysis_runs (id, started_at, depth, multipv) VALUES (1, 't0', 8, 1)")
        conn.execute("""
            INSERT INTO games (id, white, black, num_plies, last_analyzed_ply, analysis_status, queue_order)
            VALUES ('g1', 'W', 'B', 1, 1, 'done', 0), ('g2', 'W', 'B', 1, 1, 'done', 0)
        """)
        board = chess.Board()
        fen_before = board.fen()
        # move id 1 (lower, "wins"): eval_cp=35, best move e4
        conn.execute("""
            INSERT INTO moves (id, game_id, ply, move_number, color, san, fen_before, engine_version,
                                analysis_run_id, eval_source)
            VALUES (1, 'g1', 1, 1, 'white', 'e4', ?, 'Stockfish 16', 1, 'engine')
        """, (fen_before,))
        conn.execute("""
            INSERT INTO move_lines (move_id, pv_rank, eval_cp, eval_mate, move_san, pv_json, score_is_exact)
            VALUES (1, 1, 35, NULL, 'e4', '["e4"]', 1)
        """)
        # move id 2 (higher, "loses"): different eval_cp/best_move -- simulated
        # lazy-SMP nondeterminism for the identical FEN/engine_version/depth/multipv key.
        conn.execute("""
            INSERT INTO moves (id, game_id, ply, move_number, color, san, fen_before, engine_version,
                                analysis_run_id, eval_source)
            VALUES (2, 'g2', 1, 1, 'white', 'd4', ?, 'Stockfish 16', 1, 'engine')
        """, (fen_before,))
        conn.execute("""
            INSERT INTO move_lines (move_id, pv_rank, eval_cp, eval_mate, move_san, pv_json, score_is_exact)
            VALUES (2, 1, 50, NULL, 'd4', '["d4"]', 1)
        """)
        conn.commit()
        conn.close()

        def cached_payload():
            conn = sqlite3.connect(migrated_db_path)
            row = conn.execute("""
                SELECT lines_json FROM batch_eval_cache
                WHERE fen_before=? AND engine_version='Stockfish 16' AND requested_depth=8 AND multipv=1
            """, (fen_before,)).fetchone()
            conn.close()
            assert row is not None
            return json.loads(row[0])

        backfill_mod.backfill(migrated_db_path)
        payload1 = cached_payload()
        assert payload1[0]["eval_cp"] == 35
        assert payload1[0]["move_san"] == "e4"

        backfill_mod.backfill(migrated_db_path)  # repeat run
        payload2 = cached_payload()
        assert payload2 == payload1


@pytest.mark.integration
class TestLiveProofViaFakeEngine:
    def test_backfilled_cache_serves_a_fresh_game_without_calling_the_engine(self, migrated_db_path):
        """Analyzes g1 with reuse_evals=False (so no batch_eval_cache rows
        get written by the forward path itself), simulating "already-
        analyzed games from before the feature existed." Then runs the
        backfill against that DB. Then analyzes a brand-new game g2 that
        exact-FEN-repeats g1's opening with reuse_evals=True, and confirms
        it gets eval_source='reuse' matching the backfilled data, without
        the engine ever being called for that ply -- i.e. a cache hit
        sourced from the backfill, not from anything analyzed earlier in
        the same run."""
        conn = sqlite3.connect(migrated_db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        conn = _with_runs(conn)
        conn.execute("UPDATE analysis_runs SET depth=6, multipv=1 WHERE id=1")
        conn.commit()
        _insert_game_with_moves(conn, "g1", ["e4", "e5", "Nf3"])
        _populate_fen_before(conn, "g1")
        engine = FakeAnalysisEngine()
        worker.analyze_game(conn, engine, _game_row(conn, "g1"), depth=6, multipv=1, pv_max_len=10,
                             commit_every_n_moves=1, engine_version="FakeEngine", run_id=1,
                             reuse_evals=False)
        assert conn.execute("SELECT COUNT(*) FROM batch_eval_cache").fetchone()[0] == 0
        g1_ply1 = _moves_row(conn, "g1", 1)
        conn.close()

        backfill_mod.backfill(migrated_db_path)

        conn = sqlite3.connect(migrated_db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        assert conn.execute("SELECT COUNT(*) FROM batch_eval_cache").fetchone()[0] > 0

        _insert_game_with_moves(conn, "g2", ["e4", "e5", "Nf3"])  # exact-FEN repeat, brand-new game
        calls_before = engine.analyse_call_count
        worker.analyze_game(conn, engine, _game_row(conn, "g2"), depth=6, multipv=1, pv_max_len=10,
                             commit_every_n_moves=1, engine_version="FakeEngine", run_id=1,
                             reuse_evals=True)
        assert engine.analyse_call_count == calls_before, \
            "every ply of g2 exact-FEN-repeats g1 -- the engine must never be called"

        g2_ply1 = _moves_row(conn, "g2", 1)
        assert g2_ply1[-1] == "reuse"
        assert g2_ply1[:-1] == g1_ply1[:-1]  # identical payload, ignoring eval_source
        sources = [r[0] for r in conn.execute(
            "SELECT eval_source FROM moves WHERE game_id='g2' ORDER BY ply")]
        assert sources == ["reuse", "reuse", "reuse"]
        conn.close()


@pytest.mark.integration
class TestCountPendingGroups:
    """count_pending_groups() is the cheap existence-check the dashboard
    (analysis_jobs_view.py) polls on every render to decide whether to show
    the backfill banner -- it must agree with backfill()'s own notion of
    "groups seen" without doing the full move_lines join/reshape."""

    def test_empty_db_has_no_pending_groups(self, migrated_db_path):
        conn = sqlite3.connect(migrated_db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        assert backfill_mod.count_pending_groups(conn) == 0
        conn.close()

    def test_eligible_uncached_rows_are_counted(self, migrated_db_path):
        conn = sqlite3.connect(migrated_db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        conn = _with_runs(conn)
        conn.execute("UPDATE analysis_runs SET depth=6, multipv=1 WHERE id=1")
        conn.commit()
        _insert_game_with_moves(conn, "g1", ["e4", "e5", "Nf3"])
        _populate_fen_before(conn, "g1")
        engine = FakeAnalysisEngine()
        worker.analyze_game(conn, engine, _game_row(conn, "g1"), depth=6, multipv=1, pv_max_len=10,
                             commit_every_n_moves=1, engine_version="FakeEngine", run_id=1,
                             reuse_evals=False)
        pending = backfill_mod.count_pending_groups(conn)
        assert pending > 0
        conn.close()

    def test_zero_again_after_backfill_runs(self, migrated_db_path):
        conn = sqlite3.connect(migrated_db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        conn = _with_runs(conn)
        conn.execute("UPDATE analysis_runs SET depth=6, multipv=1 WHERE id=1")
        conn.commit()
        _insert_game_with_moves(conn, "g1", ["e4", "e5", "Nf3"])
        _populate_fen_before(conn, "g1")
        engine = FakeAnalysisEngine()
        worker.analyze_game(conn, engine, _game_row(conn, "g1"), depth=6, multipv=1, pv_max_len=10,
                             commit_every_n_moves=1, engine_version="FakeEngine", run_id=1,
                             reuse_evals=False)
        assert backfill_mod.count_pending_groups(conn) > 0
        conn.close()

        backfill_mod.backfill(migrated_db_path)

        conn = sqlite3.connect(migrated_db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        assert backfill_mod.count_pending_groups(conn) == 0
        conn.close()
