"""BRIEF.md Phase B onboarding calibration -- one of four sibling modules
split out of worker.py (largest-file modularization, 2026-07-17). Imports
from the two leaf siblings (worker_engine.py, worker_eval_cache.py isn't
needed directly here) and worker_analysis.py, never back through worker.py.
"""
import os
import platform
import socket
import time

import chess.engine

from migrate import migrate
from db import get_connection

from worker_engine import now_iso, find_engine_path, configure_supported
from worker_analysis import fetch_next_game, analyze_game


def calibrate(db_path, depth, multipv, threads, hash_mb, pv_max_len, engine_path, max_plies=10):
    """BRIEF.md's Phase B onboarding calibration: measures REAL average
    seconds/move on THIS user's own hardware, against a handful of their
    own already-ingested (but not-yet-analyzed) real games, using the
    exact engine settings config.yaml is configured with -- not a fixed
    claim copy-pasted from the original project's own benchmarking (which
    was specific to different hardware and was itself found to be off by
    nearly 4x once actually measured there).

    One continuous engine process across all calibration plies (not a
    fresh process per move) -- matches how worker.py's own real session
    averages are already computed in production, not a new assumption
    introduced just for calibration. Evals measured here are real and
    kept (not thrown away) -- they count toward the games' own analysis
    progress, same rows the real batch run would have produced anyway.

    Returns (avg_seconds_per_move, plies_measured). Raises RuntimeError
    if no pending games are available to measure against -- the caller
    (the onboarding wizard) is responsible for fetching/ingesting a few
    real games first.
    """
    migrate(db_path)
    conn = get_connection(db_path)

    path = find_engine_path(engine_path)
    if not path:
        conn.close()
        raise RuntimeError("No Stockfish binary found -- install it before calibrating.")

    cur = conn.execute("SELECT COUNT(*) FROM games WHERE analysis_status IN ('pending', 'in_progress')")
    if cur.fetchone()[0] == 0:
        conn.close()
        raise RuntimeError("No pending games to calibrate against -- fetch a few real games first.")

    engine = chess.engine.SimpleEngine.popen_uci(path)
    configure_supported(engine, {"Threads": threads, "Hash": hash_mb})
    engine_version = engine.id.get("name", "unknown")

    cur = conn.execute("""
        INSERT INTO analysis_runs (started_at, engine_version, depth, multipv, threads, hash_mb,
                                    hostname, platform, cpu_count)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, (now_iso(), engine_version, depth, multipv, threads, hash_mb,
          socket.gethostname(), platform.platform(), os.cpu_count()))
    run_id = cur.lastrowid
    conn.commit()

    t0 = time.monotonic()
    plies_measured = 0
    try:
        while plies_measured < max_plies:
            game_row = fetch_next_game(conn)
            if game_row is None:
                break  # ran out of pending games before hitting max_plies -- use what we got
            remaining = max_plies - plies_measured
            # reuse_evals=False here always, regardless of config: calibration exists
            # to measure REAL per-move engine time on this hardware (BRIEF.md Phase B,
            # CLAUDE.md's "state the real time cost honestly" rule) -- a cache hit
            # would resolve a ply in ~0s and silently corrupt that measurement on any
            # calibration run after the cache already has entries (e.g. a user
            # re-running onboarding, or opponent_analysis.py calibrating mid-project).
            n_plies, _finished = analyze_game(conn, engine, game_row, depth, multipv, pv_max_len,
                                               commit_every_n_moves=1, engine_version=engine_version,
                                               run_id=run_id, max_plies=remaining, reuse_evals=False)
            plies_measured += n_plies
            if n_plies == 0:
                break  # a 0-ply game or similar edge case -- avoid spinning forever
    finally:
        elapsed = time.monotonic() - t0
        conn.execute("UPDATE analysis_runs SET ended_at=?, games_analyzed=?, plies_analyzed=? WHERE id=?",
                      (now_iso(), 0, plies_measured, run_id))
        conn.commit()
        engine.quit()
        conn.close()

    if plies_measured == 0:
        raise RuntimeError("Could not measure any real moves -- the fetched game(s) may have 0 plies.")

    return elapsed / plies_measured, plies_measured
