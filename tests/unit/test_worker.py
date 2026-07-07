"""Unit tests for worker.py's queue-selection logic and the batch_eval_cache
eval-reuse helpers (see migrations/0033 + explore/batch-cloud-eval's
DEDUP_CACHE_PLAN.md). analyze_game()-level hit/miss/cutoff/resume behavior
needs the full real schema (games/moves/move_lines), so those live in
tests/integration/test_eval_reuse_cache.py instead -- these are the pure/
narrow-schema pieces only, matching this file's own existing in-memory-
sqlite style for TestFetchNextGameBacklogQuota below."""
import sqlite3

import chess
import chess.engine
import pytest

from worker import (
    fetch_next_game,
    fetch_cached_eval,
    store_cached_eval,
    lines_payload_from_engine_lines,
    REUSE_EVAL_MAX_PLY,
)


@pytest.mark.unit
class TestFetchNextGameBacklogQuota:
    def _db(self, rows):
        """rows: list of (id, analysis_status, queue_order, completed_at).
        completed_at is only meaningful for 'done' rows -- pass an
        increasing counter so ORDER BY ... DESC reflects completion order."""
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE games (id INTEGER, num_plies INTEGER, "
                     "last_analyzed_ply INTEGER, analysis_status TEXT, queue_order INTEGER, "
                     "analysis_completed_at TEXT)")
        for gid, status, qo, completed_at in rows:
            conn.execute("INSERT INTO games VALUES (?,?,?,?,?,?)",
                         (gid, 40, 0, status, qo, completed_at))
        return conn

    def test_zero_quota_always_picks_lowest_queue_order(self):
        # Recency-bumped game (negative queue_order) present alongside backlog --
        # quota disabled should reproduce the old always-recency-first behavior.
        conn = self._db([
            (1, "pending", -5, None),
            (2, "pending", 10, None),
        ])
        row = fetch_next_game(conn, backlog_quota=0.0)
        assert row[0] == 1

    def test_quota_forces_backlog_pick_when_underrepresented(self):
        # Recent completions in the window are all recency -- with a 0.5
        # quota, backlog is underrepresented in-window, so the next pick
        # must come from backlog even though a recency game is pending.
        conn = self._db([
            (1, "done", -1, "t1"),
            (2, "done", -2, "t2"),
            (3, "pending", -3, None),   # recency, would normally win
            (4, "pending", 100, None),  # backlog
        ])
        row = fetch_next_game(conn, backlog_quota=0.5, backlog_quota_window=20)
        assert row[0] == 4

    def test_quota_lets_recency_win_once_window_share_met(self):
        # Backlog already meets/exceeds the 0.5 target within the window --
        # falls through to the plain lowest-queue_order pick, recency wins.
        conn = self._db([
            (1, "done", -1, "t1"),
            (2, "done", 100, "t2"),
            (3, "pending", -3, None),
            (4, "pending", 200, None),
        ])
        row = fetch_next_game(conn, backlog_quota=0.5, backlog_quota_window=20)
        assert row[0] == 3

    def test_quota_falls_back_when_no_backlog_pending(self):
        # Backlog is underrepresented but nothing backlog-side is left to
        # pick -- must fall back to the overall queue instead of returning
        # None while a recency game is still waiting.
        conn = self._db([
            (1, "done", -1, "t1"),
            (2, "pending", -2, None),
        ])
        row = fetch_next_game(conn, backlog_quota=0.9, backlog_quota_window=20)
        assert row[0] == 2

    def test_no_pending_games_returns_none(self):
        conn = self._db([(1, "done", -1, "t1")])
        assert fetch_next_game(conn, backlog_quota=0.5) is None

    def test_rolling_window_bounds_catchup_unlike_alltime_ratio(self):
        # Regression test for the design flaw found via live simulation:
        # an all-time-cumulative ratio needs to fully repay historical debt
        # before recency resumes at all. Here recency has an enormous
        # all-time lead (50 done vs 1), but the window only looks at the
        # last 4 completions -- once those are backlog-heavy enough to
        # clear a 0.5 quota, the natural (recency-first) order must resume,
        # regardless of the huge all-time recency lead.
        # 50 old recency completions (typed to admit the None completed_at
        # of the pending rows appended below)
        rows: list[tuple[int, str, int, str | None]] = [
            (i, "done", -1, f"t{i:03d}") for i in range(1, 51)]
        rows.append((51, "done", 100, "t051"))    # 1 old backlog completion
        rows.append((52, "done", 200, "t052"))    # most recent completions: 2 backlog...
        rows.append((53, "done", -2, "t053"))     # ...and 1 recency, in the last-3 window
        rows.append((54, "pending", -3, None))   # recency, pending
        rows.append((55, "pending", 300, None))  # backlog, pending
        conn = self._db(rows)
        # Window of 3 most-recent completions (52, 53, 51 by completed_at desc
        # -- wait, order by analysis_completed_at DESC picks t53, t52, t51):
        # queue_order signs -2, 200, 100 -> backlog share 2/3 >= 0.5 quota.
        row = fetch_next_game(conn, backlog_quota=0.5, backlog_quota_window=3)
        assert row[0] == 54  # falls through to natural order -- recency wins


def _fake_line(board, move_uci, cp, mate=None, upperbound=False, seldepth=None,
                nodes=None, hashfull=None, tbhits=None, nps=None, time_s=None):
    """Builds one python-chess `engine.analyse()`-shaped line dict -- real
    chess.engine.PovScore/Cp/Mate objects (score.pov() is exercised for
    real, not mocked), a real chess.Move -- everything else fabricated."""
    move = chess.Move.from_uci(move_uci)
    score = chess.engine.PovScore(
        chess.engine.Mate(mate) if mate is not None else chess.engine.Cp(cp), board.turn)
    line = {"score": score, "pv": [move]}
    if seldepth is not None:
        line["seldepth"] = seldepth
    if nodes is not None:
        line["nodes"] = nodes
    if hashfull is not None:
        line["hashfull"] = hashfull
    if tbhits is not None:
        line["tbhits"] = tbhits
    if nps is not None:
        line["nps"] = nps
    if time_s is not None:
        line["time"] = time_s
    if upperbound:
        line["upperbound"] = True
    return line


@pytest.mark.unit
class TestLinesPayloadFromEngineLines:
    """lines_payload_from_engine_lines() builds the JSON-able per-rank
    payload batch_eval_cache stores -- the same shape write_move_and_lines()
    uses for both the fresh-engine and cache-hit write paths."""

    def test_builds_one_entry_per_rank_in_order(self):
        board = chess.Board()
        lines = [_fake_line(board, "e2e4", 30), _fake_line(board, "d2d4", 25)]
        payload = lines_payload_from_engine_lines(lines, board, board.turn, pv_max_len=15)
        assert [e["pv_rank"] for e in payload] == [1, 2]
        assert payload[0]["eval_cp"] == 30
        assert payload[0]["move_san"] == "e4"
        assert payload[0]["pv_san"] == ["e4"]
        assert payload[1]["eval_cp"] == 25
        assert payload[1]["move_san"] == "d4"

    def test_mate_score_captured_and_cp_is_none(self):
        board = chess.Board()
        lines = [_fake_line(board, "e2e4", cp=None, mate=3)]
        payload = lines_payload_from_engine_lines(lines, board, board.turn, pv_max_len=15)
        assert payload[0]["eval_mate"] == 3
        assert payload[0]["eval_cp"] is None

    def test_score_is_exact_flag(self):
        board = chess.Board()
        exact_line = _fake_line(board, "e2e4", 30)
        bound_line = _fake_line(board, "d2d4", 30, upperbound=True)
        payload = lines_payload_from_engine_lines([exact_line, bound_line], board, board.turn, 15)
        assert payload[0]["score_is_exact"] == 1
        assert payload[1]["score_is_exact"] == 0

    def test_pv_truncated_to_pv_max_len(self):
        board = chess.Board()
        # A longer PV than pv_max_len -- only the first move is legal from
        # the root board without playing it out, so use pv_max_len=1 to
        # exercise the truncation itself without needing a fully legal
        # multi-ply continuation.
        line = _fake_line(board, "e2e4", 30)
        payload = lines_payload_from_engine_lines([line], board, board.turn, pv_max_len=1)
        assert len(payload[0]["pv_san"]) == 1

    def test_excludes_telemetry_fields(self):
        """The payload is exactly what a cache entry needs to reconstruct
        moves/move_lines rows -- no nodes/seldepth/etc, since those
        describe the search call, not the position (migrations/0033)."""
        board = chess.Board()
        line = _fake_line(board, "e2e4", 30, seldepth=20, nodes=99999)
        payload = lines_payload_from_engine_lines([line], board, board.turn, 15)
        assert set(payload[0].keys()) == {
            "pv_rank", "eval_cp", "eval_mate", "move_san", "pv_san", "score_is_exact"}


@pytest.mark.unit
class TestFetchAndStoreCachedEval:
    """fetch_cached_eval()/store_cached_eval() -- the PK lookup/insert pair,
    tested against a minimal in-memory batch_eval_cache table (same
    in-memory-sqlite style as TestFetchNextGameBacklogQuota above), not the
    full migrated schema."""

    def _db(self):
        conn = sqlite3.connect(":memory:")
        conn.execute("""
            CREATE TABLE batch_eval_cache (
                fen_before TEXT NOT NULL, engine_version TEXT NOT NULL,
                requested_depth INTEGER NOT NULL, multipv INTEGER NOT NULL,
                lines_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (fen_before, engine_version, requested_depth, multipv)
            )
        """)
        return conn

    FEN = chess.STARTING_FEN
    PAYLOAD = [{"pv_rank": 1, "eval_cp": 30, "eval_mate": None,
                "move_san": "e4", "pv_san": ["e4"], "score_is_exact": 1}]

    def test_miss_on_empty_table(self):
        conn = self._db()
        assert fetch_cached_eval(conn, self.FEN, "Stockfish 16", 14, 3) is None

    def test_hit_round_trips_payload(self):
        conn = self._db()
        store_cached_eval(conn, self.FEN, "Stockfish 16", 14, 3, self.PAYLOAD)
        assert fetch_cached_eval(conn, self.FEN, "Stockfish 16", 14, 3) == self.PAYLOAD

    def test_miss_on_engine_version_mismatch(self):
        conn = self._db()
        store_cached_eval(conn, self.FEN, "Stockfish 16", 14, 3, self.PAYLOAD)
        assert fetch_cached_eval(conn, self.FEN, "Stockfish 15", 14, 3) is None

    def test_miss_on_depth_mismatch(self):
        conn = self._db()
        store_cached_eval(conn, self.FEN, "Stockfish 16", 14, 3, self.PAYLOAD)
        assert fetch_cached_eval(conn, self.FEN, "Stockfish 16", 20, 3) is None

    def test_miss_on_multipv_mismatch(self):
        conn = self._db()
        store_cached_eval(conn, self.FEN, "Stockfish 16", 14, 3, self.PAYLOAD)
        assert fetch_cached_eval(conn, self.FEN, "Stockfish 16", 14, 2) is None

    def test_insert_or_ignore_is_first_write_wins(self):
        conn = self._db()
        store_cached_eval(conn, self.FEN, "Stockfish 16", 14, 3, self.PAYLOAD)
        other_payload = [{"pv_rank": 1, "eval_cp": 999, "eval_mate": None,
                           "move_san": "d4", "pv_san": ["d4"], "score_is_exact": 1}]
        store_cached_eval(conn, self.FEN, "Stockfish 16", 14, 3, other_payload)
        assert fetch_cached_eval(conn, self.FEN, "Stockfish 16", 14, 3) == self.PAYLOAD


@pytest.mark.unit
class TestReuseEvalMaxPly:
    def test_is_24(self):
        # Named constant, not a config knob -- pinning its value here means
        # a future change to it is a deliberate, visible diff, not silent drift.
        assert REUSE_EVAL_MAX_PLY == 24
