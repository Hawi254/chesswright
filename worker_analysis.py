"""Per-game analysis loop -- one of four sibling modules split out of
worker.py (largest-file modularization, 2026-07-17). Imports from the two
leaf siblings (worker_engine.py, worker_eval_cache.py), never from
worker_calibration.py or back through worker.py itself.
"""
import json
import time

import chess
import chess.engine

from worker_engine import now_iso
from worker_eval_cache import (
    REUSE_EVAL_MAX_PLY, fetch_cached_eval, store_cached_eval,
    lines_payload_from_engine_lines,
)


def fetch_next_game(conn, backlog_quota=0.0, backlog_quota_window=20):
    """Picks the next game to analyze. Plain `ORDER BY queue_order ASC` would
    always hand back a recency-bumped game (queue_order < 0, set by
    sync.py's bump_new_games_to_front_of_queue) over a historical-backlog
    game (queue_order >= 0), for as long as any recency game is pending --
    which starves the backlog indefinitely, since syncs keep adding new
    recency games faster than the backlog drains. backlog_quota forces a
    backlog pick whenever the backlog's share of the last
    backlog_quota_window completed games is below the configured target.

    Deliberately a ROLLING window, not an all-time cumulative ratio: this
    codebase's real chess.db has a severe existing skew (recency 87.6% done
    vs backlog 12.4% done at the time this was written). An all-time ratio
    would need ~1125 consecutive backlog-only picks before recency-bumped
    games got touched again at all -- days of real analysis throughput with
    zero feedback on newly-synced games, which directly defeats the point
    of bumping them in the first place. A rolling window bounds that
    starvation to at most backlog_quota_window picks: once the window is
    saturated with backlog picks, its share hits 100% and the very next
    pick falls through to the natural (recency-first) order, even if the
    all-time debt is nowhere near repaid. 0.0 preserves the old
    always-recency-first behavior."""
    if backlog_quota > 0:
        window_rows = conn.execute("""
            SELECT queue_order FROM games
            WHERE analysis_status = 'done'
            ORDER BY analysis_completed_at DESC
            LIMIT ?
        """, (backlog_quota_window,)).fetchall()
        if window_rows:
            backlog_in_window = sum(1 for (qo,) in window_rows if qo is not None and qo >= 0)
            if backlog_in_window / len(window_rows) < backlog_quota:
                row = conn.execute("""
                    SELECT id, num_plies, last_analyzed_ply
                    FROM games
                    WHERE analysis_status IN ('pending', 'in_progress') AND queue_order >= 0
                    ORDER BY queue_order ASC
                    LIMIT 1
                """).fetchone()
                if row is not None:
                    return row
                # no pending backlog game available -- fall through to the overall pick below

    row = conn.execute("""
        SELECT id, num_plies, last_analyzed_ply
        FROM games
        WHERE analysis_status IN ('pending', 'in_progress')
        ORDER BY queue_order ASC
        LIMIT 1
    """).fetchone()
    return row


def write_move_and_lines(conn, move_id, lines_payload, run_id, engine_version, eval_source,
                          nodes=None, engine_depth=None, seldepth_by_rank=None,
                          search_time_ms=None, hashfull=None, tbhits=None, nps=None,
                          engine_reported_time_ms=None):
    """Writes the `moves` row (from the pv_rank=1 entry) and every
    `move_lines` row from lines_payload -- shared by both the fresh-engine
    path and the cache-hit path in analyze_game() below, so a cache hit is
    structurally guaranteed to write the same shape a fresh engine run
    would. Telemetry kwargs default to None -- the fresh-engine caller
    passes real values; the cache-hit caller leaves them at the default,
    which is the correct value (that search didn't happen this time).
    Returns the pv_rank=1 entry, for the caller's own console log line."""
    seldepth_by_rank = seldepth_by_rank or {}
    rank1 = next(e for e in lines_payload if e["pv_rank"] == 1)
    conn.execute("""
        UPDATE moves SET
            eval_cp=?, eval_mate=?, best_move_san=?, pv_json=?,
            nodes=?, engine_depth=?, engine_version=?,
            seldepth=?, search_time_ms=?, analysis_run_id=?,
            hashfull=?, tbhits=?, nps=?, engine_reported_time_ms=?, score_is_exact=?,
            eval_source=?
        WHERE id=?
    """, (
        rank1["eval_cp"], rank1["eval_mate"], rank1["move_san"], json.dumps(rank1["pv_san"]),
        nodes, engine_depth, engine_version,
        seldepth_by_rank.get(1), search_time_ms, run_id,
        hashfull, tbhits, nps, engine_reported_time_ms, rank1["score_is_exact"],
        eval_source, move_id,
    ))

    # all ranks (including rank 1, stored redundantly for a uniform query shape).
    # nodes/hashfull/tbhits/nps/time are global to the whole search call
    # (confirmed identical across ranks), so they live on `moves` only,
    # not duplicated here.
    for entry in lines_payload:
        conn.execute("""
            INSERT OR REPLACE INTO move_lines
                (move_id, pv_rank, eval_cp, eval_mate, move_san, pv_json, score_is_exact, seldepth)
            VALUES (?,?,?,?,?,?,?,?)
        """, (move_id, entry["pv_rank"], entry["eval_cp"], entry["eval_mate"], entry["move_san"],
              json.dumps(entry["pv_san"]), entry["score_is_exact"],
              seldepth_by_rank.get(entry["pv_rank"])))
    return rank1


def analyze_game(conn, engine, game_row, depth, multipv, pv_max_len, commit_every_n_moves,
                  engine_version, run_id, deadline=None, max_plies=None, stop_event=None,
                  reuse_evals=True, cache_stats=None):
    """cache_stats: optional dict with int "eligible"/"reused" keys, mutated
    in place (not returned) so a caller looping over many games can keep one
    running tally across the whole session without re-summing anything.
    None (every existing caller before this parameter existed, and
    calibrate(), which always runs with reuse_evals=False anyway) means
    "don't bother tallying" -- behavior is otherwise unchanged either way."""
    game_id, num_plies, last_analyzed_ply = game_row
    if num_plies is None or num_plies == 0:
        conn.execute("UPDATE games SET analysis_status='done', analysis_completed_at=? WHERE id=?",
                     (now_iso(), game_id))
        conn.commit()
        return 0, True

    conn.execute("""
        UPDATE games SET analysis_status='in_progress',
            analysis_started_at = COALESCE(analysis_started_at, ?)
        WHERE id=?
    """, (now_iso(), game_id))
    conn.commit()

    rows = conn.execute(
        "SELECT id, ply, san FROM moves WHERE game_id=? ORDER BY ply", (game_id,)
    ).fetchall()

    board = chess.Board()
    # fast-forward (no engine cost) through already-analyzed plies to reach resume point
    for move_id, ply, san in rows:
        if ply > last_analyzed_ply:
            break
        board.push_san(san)

    analyzed_this_game = 0
    moves_since_commit = 0
    for move_id, ply, san in rows:
        if ply <= last_analyzed_ply:
            continue

        mover_color = board.turn
        fen_before = board.fen()

        # Cache seam: consult batch_eval_cache for an exact-FEN repeat of a
        # position this worker already analyzed (in this game or another),
        # before spending engine time on it. Bounded to REUSE_EVAL_MAX_PLY
        # and gated on the config knob -- reuse_evals=False (or ply past the
        # cutoff) reproduces today's behavior exactly: always fall through
        # to engine.analyse() below. See migrations/0033.
        cache_eligible = reuse_evals and ply <= REUSE_EVAL_MAX_PLY
        cached_lines = fetch_cached_eval(conn, fen_before, engine_version, depth, multipv) \
            if cache_eligible else None

        if cache_stats is not None and cache_eligible:
            cache_stats["eligible"] += 1

        if cached_lines is not None:
            if cache_stats is not None:
                cache_stats["reused"] += 1
            search_time_ms = None  # no search happened -- see write_move_and_lines() docstring
            rank1 = write_move_and_lines(
                conn, move_id, cached_lines, run_id, engine_version, eval_source="reuse")
        else:
            t0 = time.monotonic()
            lines = engine.analyse(board, chess.engine.Limit(depth=depth), multipv=multipv)
            search_time_ms = int((time.monotonic() - t0) * 1000)

            # lines is a list (one dict per PV rank), ordered best-first
            rank1_line = lines[0]
            engine_reported_time_ms = int(rank1_line["time"] * 1000) if "time" in rank1_line else None
            seldepth_by_rank = {rank: line.get("seldepth") for rank, line in enumerate(lines, start=1)}

            lines_payload = lines_payload_from_engine_lines(lines, board, mover_color, pv_max_len)
            rank1 = write_move_and_lines(
                conn, move_id, lines_payload, run_id, engine_version, eval_source="engine",
                nodes=rank1_line.get("nodes"), engine_depth=rank1_line.get("depth", depth),
                seldepth_by_rank=seldepth_by_rank, search_time_ms=search_time_ms,
                hashfull=rank1_line.get("hashfull"), tbhits=rank1_line.get("tbhits"),
                nps=rank1_line.get("nps"), engine_reported_time_ms=engine_reported_time_ms,
            )

            if cache_eligible:
                # INSERT OR IGNORE, in the same transaction as the moves/move_lines
                # writes above (all three commit together at the moves_since_commit
                # checkpoint below) -- an aborted write can't leave a cache row
                # without its corresponding moves row.
                store_cached_eval(conn, fen_before, engine_version, depth, multipv, lines_payload)

        eval_cp, eval_mate, best_move_san = rank1["eval_cp"], rank1["eval_mate"], rank1["move_san"]

        conn.execute("UPDATE games SET last_analyzed_ply=? WHERE id=?", (ply, game_id))
        moves_since_commit += 1
        if moves_since_commit >= commit_every_n_moves:
            conn.commit()  # default 1: commit per-move, a crash loses at most the in-flight position
            moves_since_commit = 0

        board.push_san(san)
        analyzed_this_game += 1

        eval_str = f"M{eval_mate}" if eval_mate is not None else f"{eval_cp/100:+.2f}"
        time_str = "cache" if search_time_ms is None else f"{search_time_ms/1000:.1f}s"
        print(f"    ply {ply}/{num_plies}  {san:<8} eval={eval_str:>7}  "
              f"best={best_move_san or '-':<8} {time_str}", flush=True)

        if deadline is not None and time.monotonic() >= deadline:
            conn.commit()
            return analyzed_this_game, False  # game left in_progress, safe to resume later

        if max_plies is not None and analyzed_this_game >= max_plies:
            conn.commit()
            return analyzed_this_game, False  # calibration cutoff, not a real batch limit -- game left in_progress, safe to resume later

        if stop_event is not None and stop_event.is_set():
            conn.commit()
            # Same per-move checkpoint the deadline check above already uses --
            # engine.analyse() itself can't be interrupted mid-search, so this
            # is the finest granularity available, and it's the same one
            # max_duration already relies on in production (not a new, less-
            # proven cancellation path). Game left in_progress, safe to resume.
            return analyzed_this_game, False

    conn.commit()
    conn.execute("UPDATE games SET analysis_status='done', analysis_completed_at=? WHERE id=?",
                 (now_iso(), game_id))
    conn.commit()
    return analyzed_this_game, True
