"""Unit tests for worker.py's queue-selection logic."""
import sqlite3

import pytest

from worker import fetch_next_game


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
        rows = [(i, "done", -1, f"t{i:03d}") for i in range(1, 51)]  # 50 old recency completions
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
