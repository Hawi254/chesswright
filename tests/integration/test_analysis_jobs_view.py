"""Integration tests for dashboard/analysis_jobs_view.py's two page-local
sqlite helpers added for the live eval-reuse cache stats tiles:
`_active_run_id` (which analysis_runs row is the currently-running batch)
and `_run_cache_stats` (eval_source counts for that run, scoped to
ply<=REUSE_EVAL_MAX_PLY). Both are plain-sqlite, hand-seeded-schema tests --
no real engine, no DuckDB, matching this page's existing `_queue_counts`
convention (never routed through dashboard/data/*.py)."""
import pathlib
import sqlite3
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "dashboard"))

from worker import REUSE_EVAL_MAX_PLY
from analysis_jobs_view import _active_run_id, _run_cache_stats


def _insert_run(conn, run_id, started_at="2026-07-08T00:00:00+00:00", ended_at=None):
    conn.execute(
        "INSERT INTO analysis_runs (id, started_at, ended_at) VALUES (?,?,?)",
        (run_id, started_at, ended_at))


def _insert_move(conn, game_id, run_id, ply, eval_source, search_time_ms=None):
    """Minimal games + moves row -- enough for _run_cache_stats' query
    (analysis_run_id, ply, eval_source, search_time_ms) without a full
    ingest pass. moves.game_id is a real FK to games(id) and migrated_db
    runs with foreign_keys ON, so a games row must exist first; INSERT OR
    IGNORE lets multiple moves share the same game_id across calls."""
    conn.execute("""
        INSERT OR IGNORE INTO games (id, white, black, num_plies, last_analyzed_ply,
                                      analysis_status, queue_order)
        VALUES (?,?,?,?,?,?,?)
    """, (game_id, "W", "B", 1, 0, "pending", 0))
    conn.execute("""
        INSERT INTO moves (game_id, ply, move_number, color, san, analysis_run_id,
                            eval_source, search_time_ms)
        VALUES (?,?,?,?,?,?,?,?)
    """, (game_id, ply, (ply + 1) // 2, "white" if ply % 2 else "black", "e4",
          run_id, eval_source, search_time_ms))


@pytest.mark.integration
class TestActiveRunId:
    def test_returns_none_when_every_run_has_ended(self, migrated_db):
        conn = migrated_db
        _insert_run(conn, 1, ended_at="2026-07-08T01:00:00+00:00")
        _insert_run(conn, 2, ended_at="2026-07-08T02:00:00+00:00")
        conn.commit()
        assert _active_run_id(conn) is None

    def test_returns_none_when_no_runs_at_all(self, migrated_db):
        assert _active_run_id(migrated_db) is None

    def test_returns_the_open_run(self, migrated_db):
        conn = migrated_db
        _insert_run(conn, 1, started_at="t0", ended_at="t1")
        _insert_run(conn, 2, started_at="t2", ended_at=None)
        conn.commit()
        assert _active_run_id(conn) == (2, "t2")

    def test_picks_highest_id_null_row_over_an_orphaned_older_one(self, migrated_db):
        """Simulates a hard-killed process (worker.py's `finally:` never ran,
        so its analysis_runs row was left with ended_at IS NULL forever) followed
        by a genuinely new run starting -- the new run always gets a higher id,
        so ORDER BY id DESC LIMIT 1 must return it, not the stale orphan."""
        conn = migrated_db
        _insert_run(conn, 1, started_at="orphaned", ended_at=None)  # hard-killed, never closed
        _insert_run(conn, 2, started_at="genuinely_current", ended_at=None)
        conn.commit()
        assert _active_run_id(conn) == (2, "genuinely_current")


@pytest.mark.integration
class TestRunCacheStats:
    def test_hand_computed_counts_match(self, migrated_db):
        conn = migrated_db
        _insert_run(conn, 1)
        # 2 reused + 3 engine among ply<=REUSE_EVAL_MAX_PLY -- the eligible set.
        _insert_move(conn, "g1", 1, 1, "reuse")
        _insert_move(conn, "g1", 1, 2, "reuse")
        _insert_move(conn, "g1", 1, 3, "engine", search_time_ms=100)
        _insert_move(conn, "g1", 1, 4, "engine", search_time_ms=200)
        _insert_move(conn, "g1", 1, 5, "engine", search_time_ms=300)
        conn.commit()

        reused, engine_n, avg_engine_ms = _run_cache_stats(conn, 1)
        assert (reused, engine_n) == (2, 3)
        assert avg_engine_ms == pytest.approx(200.0)

    def test_excludes_plies_beyond_the_reuse_cutoff(self, migrated_db):
        conn = migrated_db
        _insert_run(conn, 1)
        _insert_move(conn, "g1", 1, 1, "reuse")
        # Beyond REUSE_EVAL_MAX_PLY -- must never have been a cache candidate,
        # so including it would wrongly dilute/inflate the eligible-only ratio.
        _insert_move(conn, "g1", 1, REUSE_EVAL_MAX_PLY + 1, "engine", search_time_ms=999)
        conn.commit()

        reused, engine_n, avg_engine_ms = _run_cache_stats(conn, 1)
        assert (reused, engine_n) == (1, 0)
        assert avg_engine_ms is None

    def test_excludes_rows_from_a_different_run(self, migrated_db):
        conn = migrated_db
        _insert_run(conn, 1)
        _insert_run(conn, 2)
        _insert_move(conn, "g1", 1, 1, "reuse")
        _insert_move(conn, "g2", 2, 1, "engine", search_time_ms=500)  # different run -- must be excluded
        conn.commit()

        reused, engine_n, avg_engine_ms = _run_cache_stats(conn, 1)
        assert (reused, engine_n, avg_engine_ms) == (1, 0, None)

    def test_returns_zeros_and_none_when_no_moves_yet(self, migrated_db):
        conn = migrated_db
        _insert_run(conn, 1)
        conn.commit()
        assert _run_cache_stats(conn, 1) == (0, 0, None)
