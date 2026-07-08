"""Integration tests for the batch_eval_cache eval-reuse feature (see
migrations/0033 + explore/batch-cloud-eval's DEDUP_CACHE_PLAN.md): worker.py
reusing a prior Stockfish result for an exact-FEN repeat position instead
of re-running the engine.

analyze_game()-level tests (hit/miss/cutoff/knob/resume) use a fake engine
against the real migrated schema -- fast, deterministic, no real Stockfish
needed to prove the cache seam's own routing logic. The final class uses
the real system Stockfish (Threads=1, tiny depth) for the actual
worker.py -> annotate.py round trip this feature is not allowed to change.
"""
import pathlib
import sqlite3
import subprocess
import sys

import chess
import chess.engine
import pytest

REPO_ROOT = pathlib.Path(__file__).parent.parent.parent
FIXTURES = pathlib.Path(__file__).parent.parent / "fixtures"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "dashboard"))

import worker
from worker import analyze_game


class FakeAnalysisEngine:
    """Deterministic stand-in for chess.engine.SimpleEngine. Every line's
    eval is a function of (this fake's own call count, rank) only -- NOT
    of the position -- so two calls for the exact same FEN are guaranteed
    to disagree, making "the second occurrence's row matches the first
    occurrence's row" an actual proof of reuse, not a coincidence a real
    engine's determinism could also explain."""

    def __init__(self):
        self.analyse_call_count = 0

    def analyse(self, board, limit, multipv=1):
        self.analyse_call_count += 1
        legal = list(board.legal_moves)
        lines = []
        for i in range(min(multipv, len(legal))):
            mv = legal[i]
            cp = 100 * self.analyse_call_count + i
            lines.append({
                "score": chess.engine.PovScore(chess.engine.Cp(cp), board.turn),
                "pv": [mv],
                "nodes": 1000 * self.analyse_call_count,
                "depth": getattr(limit, "depth", None) or 10,
                "seldepth": 12 + i,
                "time": 0.01,
                "hashfull": 7,
                "tbhits": 0,
                "nps": 500000,
            })
        return lines


def _with_runs(conn):
    """moves.analysis_run_id is a real FK to analysis_runs(id) and the
    migrated_db fixture connection runs with foreign_keys ON -- production
    always INSERTs an analysis_runs row before analyze_game() runs
    (worker.run()/calibrate()), so these tests must too. Covers both
    run_ids used below (1 and 7)."""
    conn.execute("INSERT INTO analysis_runs (id, started_at) VALUES (1, 't0'), (7, 't0')")
    conn.commit()
    return conn


def _insert_game_with_moves(conn, game_id, sans):
    """Inserts a minimal games row + one moves row per SAN -- enough for
    analyze_game() to walk, without needing a real PGN/ingest.py pass.
    Ply/move_number/color follow ingest.py's own 1-indexed-ply,
    alternating-color convention."""
    conn.execute("""
        INSERT INTO games (id, white, black, num_plies, last_analyzed_ply, analysis_status, queue_order)
        VALUES (?,?,?,?,?,?,?)
    """, (game_id, "W", "B", len(sans), 0, "pending", 0))
    for i, san in enumerate(sans):
        ply = i + 1
        color = "white" if ply % 2 == 1 else "black"
        move_number = (ply + 1) // 2
        conn.execute(
            "INSERT INTO moves (game_id, ply, move_number, color, san) VALUES (?,?,?,?,?)",
            (game_id, ply, move_number, color, san))
    conn.commit()


def _game_row(conn, game_id):
    return conn.execute(
        "SELECT id, num_plies, last_analyzed_ply FROM games WHERE id=?", (game_id,)
    ).fetchone()


def _moves_row(conn, game_id, ply, cols="eval_cp, eval_mate, best_move_san, pv_json, score_is_exact, eval_source"):
    return conn.execute(
        f"SELECT {cols} FROM moves WHERE game_id=? AND ply=?", (game_id, ply)
    ).fetchone()


TELEMETRY_COLS = "nodes, engine_depth, seldepth, search_time_ms, hashfull, tbhits, nps, engine_reported_time_ms"


@pytest.mark.integration
class TestCacheHitWritesIdenticalRows:
    def test_hit_matches_fresh_run_payload_and_skips_engine(self, migrated_db):
        conn = _with_runs(migrated_db)
        _insert_game_with_moves(conn, "g1", ["e4", "e5"])
        _insert_game_with_moves(conn, "g2", ["d4", "d5"])  # different ply-1 move, same ply-1 FEN (start pos)
        engine = FakeAnalysisEngine()

        analyze_game(conn, engine, _game_row(conn, "g1"), depth=6, multipv=2, pv_max_len=10,
                      commit_every_n_moves=1, engine_version="FakeEngine", run_id=1)
        assert engine.analyse_call_count == 2  # both of g1's plies are fresh

        analyze_game(conn, engine, _game_row(conn, "g2"), depth=6, multipv=2, pv_max_len=10,
                      commit_every_n_moves=1, engine_version="FakeEngine", run_id=1)
        # g2 ply 1 shares g1 ply 1's FEN (both start from the standard starting
        # position) -- only g2's ply 2 (a genuinely new position) should call the engine.
        assert engine.analyse_call_count == 3

        g1_ply1 = _moves_row(conn, "g1", 1)
        g2_ply1 = _moves_row(conn, "g2", 1)
        assert g1_ply1[:-1] == g2_ply1[:-1]  # identical payload, ignoring eval_source
        assert g1_ply1[-1] == "engine"
        assert g2_ply1[-1] == "reuse"

        telemetry = conn.execute(
            f"SELECT {TELEMETRY_COLS} FROM moves WHERE game_id='g2' AND ply=1").fetchone()
        assert all(v is None for v in telemetry), "telemetry must be NULL on a reused row"

        g1_lines = conn.execute("""
            SELECT pv_rank, eval_cp, eval_mate, move_san, pv_json, score_is_exact FROM move_lines
            WHERE move_id=(SELECT id FROM moves WHERE game_id='g1' AND ply=1) ORDER BY pv_rank
        """).fetchall()
        g2_lines = conn.execute("""
            SELECT pv_rank, eval_cp, eval_mate, move_san, pv_json, score_is_exact FROM move_lines
            WHERE move_id=(SELECT id FROM moves WHERE game_id='g2' AND ply=1) ORDER BY pv_rank
        """).fetchall()
        assert g1_lines == g2_lines
        assert len(g2_lines) == 2  # multipv=2, both ranks reconstructed from cache

        g2_seldepths = conn.execute("""
            SELECT seldepth FROM move_lines
            WHERE move_id=(SELECT id FROM moves WHERE game_id='g2' AND ply=1)
        """).fetchall()
        assert all(v == (None,) for v in g2_seldepths)

        cache_rows = conn.execute("SELECT COUNT(*) FROM batch_eval_cache").fetchone()[0]
        assert cache_rows >= 1

    def test_analysis_run_id_and_engine_version_still_set_on_reuse(self, migrated_db):
        """analysis_run_id/engine_version are current-run identity, not
        search telemetry -- they stay populated on a reused row too."""
        conn = _with_runs(migrated_db)
        _insert_game_with_moves(conn, "g1", ["e4"])
        _insert_game_with_moves(conn, "g2", ["d4"])
        engine = FakeAnalysisEngine()
        analyze_game(conn, engine, _game_row(conn, "g1"), depth=6, multipv=1, pv_max_len=10,
                      commit_every_n_moves=1, engine_version="FakeEngine", run_id=7)
        analyze_game(conn, engine, _game_row(conn, "g2"), depth=6, multipv=1, pv_max_len=10,
                      commit_every_n_moves=1, engine_version="FakeEngine", run_id=7)
        row = conn.execute(
            "SELECT analysis_run_id, engine_version, eval_source FROM moves WHERE game_id='g2' AND ply=1"
        ).fetchone()
        assert row == (7, "FakeEngine", "reuse")


@pytest.mark.integration
class TestKeyMismatchIsAMiss:
    def test_engine_version_mismatch(self, migrated_db):
        conn = _with_runs(migrated_db)
        _insert_game_with_moves(conn, "g1", ["e4"])
        _insert_game_with_moves(conn, "g2", ["d4"])
        engine = FakeAnalysisEngine()
        analyze_game(conn, engine, _game_row(conn, "g1"), depth=6, multipv=1, pv_max_len=10,
                      commit_every_n_moves=1, engine_version="EngineA", run_id=1)
        analyze_game(conn, engine, _game_row(conn, "g2"), depth=6, multipv=1, pv_max_len=10,
                      commit_every_n_moves=1, engine_version="EngineB", run_id=1)
        assert engine.analyse_call_count == 2  # no reuse across different engine identities
        assert _moves_row(conn, "g2", 1, "eval_source")[0] == "engine"

    def test_depth_mismatch(self, migrated_db):
        conn = _with_runs(migrated_db)
        _insert_game_with_moves(conn, "g1", ["e4"])
        _insert_game_with_moves(conn, "g2", ["d4"])
        engine = FakeAnalysisEngine()
        analyze_game(conn, engine, _game_row(conn, "g1"), depth=6, multipv=1, pv_max_len=10,
                      commit_every_n_moves=1, engine_version="FakeEngine", run_id=1)
        analyze_game(conn, engine, _game_row(conn, "g2"), depth=10, multipv=1, pv_max_len=10,
                      commit_every_n_moves=1, engine_version="FakeEngine", run_id=1)
        assert engine.analyse_call_count == 2
        assert _moves_row(conn, "g2", 1, "eval_source")[0] == "engine"

    def test_multipv_mismatch(self, migrated_db):
        conn = _with_runs(migrated_db)
        _insert_game_with_moves(conn, "g1", ["e4"])
        _insert_game_with_moves(conn, "g2", ["d4"])
        engine = FakeAnalysisEngine()
        analyze_game(conn, engine, _game_row(conn, "g1"), depth=6, multipv=1, pv_max_len=10,
                      commit_every_n_moves=1, engine_version="FakeEngine", run_id=1)
        analyze_game(conn, engine, _game_row(conn, "g2"), depth=6, multipv=2, pv_max_len=10,
                      commit_every_n_moves=1, engine_version="FakeEngine", run_id=1)
        assert engine.analyse_call_count == 2
        assert _moves_row(conn, "g2", 1, "eval_source")[0] == "engine"


@pytest.mark.integration
class TestPlyCutoff:
    def test_ply_past_cutoff_never_reads_or_writes_cache(self, migrated_db, monkeypatch):
        # Lower the cutoff to 1 so a 2-ply game exercises the "past cutoff" branch
        # without needing a fixture with 25+ plies.
        monkeypatch.setattr(worker, "REUSE_EVAL_MAX_PLY", 1)
        conn = _with_runs(migrated_db)
        _insert_game_with_moves(conn, "g1", ["e4", "e5"])
        _insert_game_with_moves(conn, "g2", ["e4", "e5"])  # identical line -> ply 1 AND ply 2 FENs both match
        engine = FakeAnalysisEngine()
        analyze_game(conn, engine, _game_row(conn, "g1"), depth=6, multipv=1, pv_max_len=10,
                      commit_every_n_moves=1, engine_version="FakeEngine", run_id=1)
        calls_after_g1 = engine.analyse_call_count
        assert calls_after_g1 == 2

        analyze_game(conn, engine, _game_row(conn, "g2"), depth=6, multipv=1, pv_max_len=10,
                      commit_every_n_moves=1, engine_version="FakeEngine", run_id=1)
        # ply 1 (<=cutoff) is a cache hit; ply 2 (>cutoff) must NOT consult the
        # cache even though its FEN also matches g1's ply 2 exactly.
        assert engine.analyse_call_count == calls_after_g1 + 1
        assert _moves_row(conn, "g2", 1, "eval_source")[0] == "reuse"
        assert _moves_row(conn, "g2", 2, "eval_source")[0] == "engine"

        # and ply 2 was never even inserted into the cache by g1's own run
        cached = worker.fetch_cached_eval(
            conn, conn.execute("SELECT fen_before FROM moves WHERE game_id='g1' AND ply=2").fetchone()[0],
            "FakeEngine", 6, 1)
        assert cached is None


@pytest.mark.integration
class TestReuseEvalsKnobOff:
    def test_knob_off_never_reads_or_writes_cache(self, migrated_db):
        conn = _with_runs(migrated_db)
        _insert_game_with_moves(conn, "g1", ["e4"])
        _insert_game_with_moves(conn, "g2", ["d4"])
        engine = FakeAnalysisEngine()
        analyze_game(conn, engine, _game_row(conn, "g1"), depth=6, multipv=1, pv_max_len=10,
                      commit_every_n_moves=1, engine_version="FakeEngine", run_id=1, reuse_evals=False)
        analyze_game(conn, engine, _game_row(conn, "g2"), depth=6, multipv=1, pv_max_len=10,
                      commit_every_n_moves=1, engine_version="FakeEngine", run_id=1, reuse_evals=False)
        assert engine.analyse_call_count == 2  # no reuse at all, despite identical ply-1 FEN
        assert _moves_row(conn, "g1", 1, "eval_source")[0] == "engine"
        assert _moves_row(conn, "g2", 1, "eval_source")[0] == "engine"
        assert conn.execute("SELECT COUNT(*) FROM batch_eval_cache").fetchone()[0] == 0


@pytest.mark.integration
class TestCacheStatsTally:
    """cache_stats mutation in analyze_game() -- the in-process counter
    worker.run() uses for its CLI print lines (must count 'eligible' among
    ply<=REUSE_EVAL_MAX_PLY only, never ply beyond the cutoff, and 'reused'
    only on an actual hit)."""

    def test_mix_of_hits_misses_and_ineligible_plies_in_one_call(self, migrated_db, monkeypatch):
        monkeypatch.setattr(worker, "REUSE_EVAL_MAX_PLY", 3)
        conn = _with_runs(migrated_db)
        engine = FakeAnalysisEngine()

        # Seed the cache: g1's 3 plies are all fresh (first time seeing these
        # FENs), populating batch_eval_cache for start / after-1.e4 / after-1.e4-e5.
        _insert_game_with_moves(conn, "g1", ["e4", "e5", "Nf3"])
        analyze_game(conn, engine, _game_row(conn, "g1"), depth=6, multipv=1, pv_max_len=10,
                      commit_every_n_moves=1, engine_version="FakeEngine", run_id=1,
                      reuse_evals=True)  # no cache_stats passed -- must not raise

        # g2: ply1 "e4" -> same start-position FEN as g1's ply1 -> HIT.
        # ply2 "d5" -> fen_before is "after 1.e4" (matches g1's ply1 move) -> HIT.
        # ply3 "Nf3" -> fen_before is "after 1.e4 d5", never seen before -> MISS.
        # ply4/ply5 -> beyond the ply<=3 cutoff, must never touch the cache at all.
        _insert_game_with_moves(conn, "g2", ["e4", "d5", "Nf3", "Nc6", "Bb5"])
        cache_stats = {"eligible": 0, "reused": 0}
        analyze_game(conn, engine, _game_row(conn, "g2"), depth=6, multipv=1, pv_max_len=10,
                      commit_every_n_moves=1, engine_version="FakeEngine", run_id=1,
                      reuse_evals=True, cache_stats=cache_stats)

        assert cache_stats == {"eligible": 3, "reused": 2}
        sources = [r[0] for r in conn.execute(
            "SELECT eval_source FROM moves WHERE game_id='g2' ORDER BY ply")]
        assert sources == ["reuse", "reuse", "engine", "engine", "engine"]

    def test_cache_stats_stays_zero_when_reuse_evals_off(self, migrated_db):
        conn = _with_runs(migrated_db)
        _insert_game_with_moves(conn, "g1", ["e4"])
        _insert_game_with_moves(conn, "g2", ["e4"])
        engine = FakeAnalysisEngine()
        analyze_game(conn, engine, _game_row(conn, "g1"), depth=6, multipv=1, pv_max_len=10,
                      commit_every_n_moves=1, engine_version="FakeEngine", run_id=1, reuse_evals=False)
        cache_stats = {"eligible": 0, "reused": 0}
        analyze_game(conn, engine, _game_row(conn, "g2"), depth=6, multipv=1, pv_max_len=10,
                      commit_every_n_moves=1, engine_version="FakeEngine", run_id=1,
                      reuse_evals=False, cache_stats=cache_stats)
        assert cache_stats == {"eligible": 0, "reused": 0}

    def test_cache_stats_none_is_a_safe_default(self, migrated_db):
        """Existing callers (e.g. calibrate()) that never pass cache_stats
        must be entirely unaffected -- no crash, no attribute error."""
        conn = _with_runs(migrated_db)
        _insert_game_with_moves(conn, "g1", ["e4", "e5"])
        engine = FakeAnalysisEngine()
        n_plies, finished = analyze_game(
            conn, engine, _game_row(conn, "g1"), depth=6, multipv=1, pv_max_len=10,
            commit_every_n_moves=1, engine_version="FakeEngine", run_id=1, reuse_evals=True)
        assert (n_plies, finished) == (2, True)


@pytest.mark.integration
class TestResumeAcrossCacheHitBoundary:
    def test_interrupt_right_after_a_cache_hit_ply_then_resume(self, migrated_db):
        conn = _with_runs(migrated_db)
        _insert_game_with_moves(conn, "g1", ["e4", "e5", "Nf3"])
        engine = FakeAnalysisEngine()
        analyze_game(conn, engine, _game_row(conn, "g1"), depth=6, multipv=1, pv_max_len=10,
                      commit_every_n_moves=1, engine_version="FakeEngine", run_id=1)
        # seeds the cache for all 3 plies of this exact line

        _insert_game_with_moves(conn, "g2", ["e4", "e5", "Nf3"])  # identical line -> all 3 plies are hits
        n_plies, finished = analyze_game(
            conn, engine, _game_row(conn, "g2"), depth=6, multipv=1, pv_max_len=10,
            commit_every_n_moves=1, engine_version="FakeEngine", run_id=1, max_plies=1)
        assert (n_plies, finished) == (1, False)
        assert conn.execute(
            "SELECT analysis_status, last_analyzed_ply FROM games WHERE id='g2'"
        ).fetchone() == ("in_progress", 1)
        assert _moves_row(conn, "g2", 1, "eval_source")[0] == "reuse"

        calls_before_resume = engine.analyse_call_count
        n_plies2, finished2 = analyze_game(
            conn, engine, _game_row(conn, "g2"), depth=6, multipv=1, pv_max_len=10,
            commit_every_n_moves=1, engine_version="FakeEngine", run_id=1)
        assert finished2 is True
        assert n_plies2 == 2  # plies 2 and 3, resumed correctly past the cache-hit ply 1
        assert engine.analyse_call_count == calls_before_resume  # both remaining plies were hits too
        assert conn.execute(
            "SELECT analysis_status, last_analyzed_ply FROM games WHERE id='g2'"
        ).fetchone() == ("done", 3)
        sources = [r[0] for r in conn.execute(
            "SELECT eval_source FROM moves WHERE game_id='g2' ORDER BY ply")]
        assert sources == ["reuse", "reuse", "reuse"]


# ---------------------------------------------------------------------------
# Real-Stockfish round trip: worker.py -> annotate.py, cached vs uncached.
# ---------------------------------------------------------------------------

def _find_real_stockfish():
    from worker import find_engine_path
    return find_engine_path(None)


REAL_STOCKFISH = _find_real_stockfish()


@pytest.mark.integration
@pytest.mark.skipif(REAL_STOCKFISH is None, reason="no Stockfish binary on this machine")
class TestRealEngineCacheRoundTrip:
    """Analyzes the repo's own synthetic_games.pgn fixture (games 1 and 3
    both open 1.e4 e5 -- a genuine repeated position across two different
    games) twice into two separate scratch DBs: once with reuse_evals=False
    (every ply engine-sourced -- the control) and once with reuse_evals=True
    (repeated positions become cache hits). annotate.py's derived output
    must be byte-identical between the two."""

    DEPTH = 6
    MULTIPV = 2
    THREADS = 1

    def _analyze_fixture(self, tmp_path, name, reuse_evals, monkeypatch):
        import migrate as migrate_mod
        import ingest
        import annotate

        db_path = str(tmp_path / name)
        migrate_mod.migrate(db_path)
        ingest.ingest(pgn_path=str(FIXTURES / "synthetic_games.pgn"), db_path=db_path,
                      player_name="TestPlayerWhite")

        lock_path = tmp_path / f"{name}.lock"
        monkeypatch.setattr(worker.joblock, "LOCK_PATH", lock_path)
        monkeypatch.setattr(worker.joblock, "_lock_fd", None)
        worker.run(
            db_path, self.DEPTH, self.MULTIPV, self.THREADS, hash_mb=16, pv_max_len=10,
            engine_path=REAL_STOCKFISH, max_games=10, max_duration_s=None,
            consecutive_failure_limit=3, commit_every_n_moves=1, reuse_evals=reuse_evals)
        worker.joblock.release()

        annotate.run(
            db_path=db_path, mate_cap=1000,
            thresholds={"excellent": 0.02, "good": 0.05, "inaccuracy": 0.10,
                        "mistake": 0.20, "blunder": 1.00},
            brilliant_threshold=None, puzzle_cfg={}, streak_cfg={}, game_id=None)
        return db_path

    def test_repeated_positions_skip_the_engine_when_cache_on(self, tmp_path, monkeypatch):
        db_cached = self._analyze_fixture(tmp_path, "cached.db", reuse_evals=True, monkeypatch=monkeypatch)
        conn = sqlite3.connect(db_cached)
        sources = dict(conn.execute(
            "SELECT eval_source, COUNT(*) FROM moves WHERE eval_source IS NOT NULL GROUP BY eval_source"
        ).fetchall())
        conn.close()
        assert sources.get("reuse", 0) > 0, \
            "expected at least one exact-FEN repeat across the fixture's games to hit the cache"

    def test_annotate_output_byte_identical_cached_vs_uncached(self, tmp_path, monkeypatch):
        db_uncached = self._analyze_fixture(tmp_path, "uncached.db", reuse_evals=False, monkeypatch=monkeypatch)
        db_cached = self._analyze_fixture(tmp_path, "cached.db", reuse_evals=True, monkeypatch=monkeypatch)

        conn_u = sqlite3.connect(db_uncached)
        conn_c = sqlite3.connect(db_cached)

        sources_u = {r[0] for r in conn_u.execute(
            "SELECT DISTINCT eval_source FROM moves WHERE eval_source IS NOT NULL")}
        sources_c = dict(conn_c.execute(
            "SELECT eval_source, COUNT(*) FROM moves WHERE eval_source IS NOT NULL GROUP BY eval_source"))
        assert sources_u == {"engine"}, "control run must be 100% engine-sourced"
        assert sources_c.get("reuse", 0) > 0, "cached run must have at least one reused ply"

        derived_cols = ("ply, cpl, classification, win_prob_before, win_prob_after, "
                         "sharpness, best_move_streak_length, is_best_move_streak_trigger, "
                         "best_move_streak_unforced_count")
        game_ids = [r[0] for r in conn_u.execute("SELECT id FROM games ORDER BY id").fetchall()]
        assert game_ids == [r[0] for r in conn_c.execute("SELECT id FROM games ORDER BY id").fetchall()], \
            "both DBs ingested the same PGN -- game ids (parsed from the Site URL) must match"

        for gid in game_ids:
            rows_u = conn_u.execute(
                f"SELECT {derived_cols} FROM moves WHERE game_id=? ORDER BY ply", (gid,)).fetchall()
            rows_c = conn_c.execute(
                f"SELECT {derived_cols} FROM moves WHERE game_id=? ORDER BY ply", (gid,)).fetchall()
            assert rows_u == rows_c, f"annotate.py output diverged for game {gid} between cached/uncached runs"

    def test_cli_prints_cache_tally_fragment(self, tmp_path, monkeypatch, capsys):
        """games 1 and 3 of the fixture both open 1.e4 e5 -- a genuine repeat
        -- so a real reuse_evals=True run must produce at least one reused
        ply, and worker.py's own print output (per-game line + session
        summary) must both surface the 'cache N/M eligible plies reused'
        fragment with a sane, non-crashing count."""
        self._analyze_fixture(tmp_path, "cli_cache.db", reuse_evals=True, monkeypatch=monkeypatch)
        out = capsys.readouterr().out

        per_game_lines = [line for line in out.splitlines() if line.startswith("[")]
        assert per_game_lines, "expected at least one per-game print line"
        cache_lines = [line for line in per_game_lines if "eligible plies reused" in line]
        assert cache_lines, \
            f"expected a per-game line with the cache fragment, got:\n{out}"
        for line in cache_lines:
            assert " | cache " in line

        summary_lines = [line for line in out.splitlines() if line.startswith("Session summary:")]
        assert len(summary_lines) == 1
        assert "eligible plies reused" in summary_lines[0], \
            f"expected the session summary to include the cache fragment, got:\n{summary_lines[0]}"

        import re
        m = re.search(r"cache (\d+)/(\d+) eligible plies reused \((\d+)%\)", summary_lines[0])
        assert m is not None, f"cache fragment didn't match the expected shape: {summary_lines[0]}"
        reused, eligible, pct = int(m.group(1)), int(m.group(2)), int(m.group(3))
        assert 0 < reused <= eligible
        assert 0 <= pct <= 100


# ---------------------------------------------------------------------------
# worker.main() CLI-entrypoint refactor correctness (desktop_app.py's
# --run-worker mode calls this exact same function in-process -- see
# desktop_app.run_worker_mode()). Pure extraction from the old bare
# `if __name__ == "__main__":` block, so this only needs to prove
# args-parse-and-dispatch still works, not re-test run()'s own behavior
# (already covered above and in tests/unit/test_worker.py).
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.skipif(REAL_STOCKFISH is None, reason="no Stockfish binary on this machine")
class TestWorkerMainEntrypoint:
    def test_subprocess_python3_worker_py_still_works_post_refactor(self, tmp_path, monkeypatch):
        """`python3 worker.py ...` -- the exact pre-refactor invocation --
        must still behave identically: real subprocess, real engine, one
        game analyzed end to end."""
        import migrate as migrate_mod
        import ingest

        db_path = str(tmp_path / "cli.db")
        migrate_mod.migrate(db_path)
        ingest.ingest(pgn_path=str(FIXTURES / "synthetic_games.pgn"), db_path=db_path,
                      player_name="TestPlayerWhite")

        proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / "worker.py"),
             "--db", db_path, "--depth", "4", "--multipv", "1", "--threads", "1",
             "--max-games", "1", "--engine-path", REAL_STOCKFISH],
            capture_output=True, text=True, timeout=180, cwd=str(REPO_ROOT),
        )
        assert proc.returncode == 0, f"stdout={proc.stdout}\nstderr={proc.stderr}"

        conn = sqlite3.connect(db_path)
        statuses = [r[0] for r in conn.execute("SELECT analysis_status FROM games").fetchall()]
        conn.close()
        assert "done" in statuses, f"expected at least one game analyzed, got {statuses}"

    def test_in_process_main_call_parses_args_and_dispatches(self, tmp_path, monkeypatch):
        """worker.main([...]) called directly in-process (as desktop_app.py's
        --run-worker mode does) with a short real-Stockfish scenario -- proves
        argparse + run() dispatch still works when called as a function, not
        just as a script."""
        import migrate as migrate_mod
        import ingest

        db_path = str(tmp_path / "inprocess.db")
        migrate_mod.migrate(db_path)
        ingest.ingest(pgn_path=str(FIXTURES / "synthetic_games.pgn"), db_path=db_path,
                      player_name="TestPlayerWhite")

        lock_path = tmp_path / "inprocess.lock"
        monkeypatch.setattr(worker.joblock, "LOCK_PATH", lock_path)
        monkeypatch.setattr(worker.joblock, "_lock_fd", None)

        worker.main([
            "--db", db_path, "--depth", "4", "--multipv", "1", "--threads", "1",
            "--max-games", "1", "--engine-path", REAL_STOCKFISH,
        ])

        conn = sqlite3.connect(db_path)
        statuses = [r[0] for r in conn.execute("SELECT analysis_status FROM games").fetchall()]
        conn.close()
        assert "done" in statuses, f"expected at least one game analyzed, got {statuses}"
