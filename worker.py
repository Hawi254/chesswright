#!/usr/bin/env python3
"""
Phase 2: Stockfish analysis worker.

Walks games in `queue_order`, analyzes each position at a fixed depth,
and writes raw engine output back to the `moves` table. Deliberately does
NOT compute CPL/classification/win-probability here -- that's a cheap
post-processing pass (Phase 3) over the raw evals this script produces,
so tuning those formulas never requires re-running the engine.

Eval convention: eval_cp / eval_mate are stored from the perspective of
the player TO MOVE at that position (i.e. "how good is this position for
whoever is about to move"). This is exactly what the engine returns
natively, so no perspective-flipping happens here -- keeping bugs out of
the expensive path. Phase 3 is responsible for flipping perspective when
comparing consecutive plies.

All engine/batch settings come from config.yaml by default; any CLI flag
overrides the config value for that one run.

Usage:
    python3 worker.py                          # uses config.yaml as-is
    python3 worker.py --max-games 50            # override just one setting
    python3 worker.py --depth 24 --multipv 2 --max-duration 2h

Split (largest-file modularization, 2026-07-17) into four sibling
modules -- worker_engine.py (engine discovery/validation/config, plus
now_iso -- see worker_engine.py's own docstring for why now_iso lives
there and not here), worker_eval_cache.py (cached-eval fetch/store),
worker_analysis.py (the per-game analysis loop), worker_calibration.py
(onboarding calibration) -- this file keeps only run()/main() and
re-exports everything above so every existing import path
(`from worker import lines_payload_from_engine_lines`,
`worker.validate_engine_path`, etc.) keeps working unchanged.
"""
import argparse
import os
import platform
import socket
import sys
import time

import chess
import chess.engine

from migrate import migrate
from db import get_connection
from config import load_config, pick
import joblock
import achievements

from worker_engine import now_iso, find_engine_path, configure_supported, validate_engine_path
from worker_eval_cache import (
    REUSE_EVAL_MAX_PLY, score_to_fields, fetch_cached_eval, store_cached_eval,
    lines_payload_from_engine_lines,
)
from worker_analysis import fetch_next_game, write_move_and_lines, analyze_game
from worker_calibration import calibrate


def parse_duration(s):
    """'2h' -> 7200, '90m' -> 5400, '300' -> 300 (bare seconds)."""
    if s is None:
        return None
    s = str(s).strip().lower()
    units = {"h": 3600, "m": 60, "s": 1}
    if s and s[-1] in units:
        return int(float(s[:-1]) * units[s[-1]])
    return int(s)


def run(db_path, depth, multipv, threads, hash_mb, pv_max_len, engine_path,
         max_games, max_duration_s, consecutive_failure_limit, commit_every_n_moves,
         backlog_quota=0.0, backlog_quota_window=20, on_game_done=None, stop_event=None,
         reuse_evals=None):
    """reuse_evals: the batch_eval_cache knob (config.yaml engine.reuse_evals,
    see migrations/0033). None -- the default, what every existing in-process
    caller (job_runner.py, onboarding_view.py, opponent_analysis.py) passes
    implicitly -- means "read it from config.yaml", so setting the knob false
    restores the old always-re-analyze behavior for every entry point, not
    just the CLI. An explicit True/False (the CLI __main__ below, tests)
    wins over config, same precedence rule as pick().

    on_game_done(games_done, n_plies, finished): optional callback fired
    after each game, used by the packaged app's onboarding wizard to drive
    a live progress bar in-process (BRIEF.md Phase C found that launching
    this as a `sys.executable worker.py` subprocess -- fine from a source
    checkout -- breaks once frozen by PyInstaller, since sys.executable
    IS the bundled app itself there, not a separate runnable worker.py).
    CLI usage (`python3 worker.py ...`) passes nothing, unaffected.

    stop_event: optional threading.Event, checked between moves (same
    granularity as max_duration's own deadline check) so the Analysis
    Jobs dashboard view can cancel a batch running on a background thread
    without killing the process. None for CLI usage -- only Ctrl-C
    (KeyboardInterrupt, already handled below) applies there.

    joblock.acquire()/release(): closes the cross-process duplicate-run
    gap named in BRIEF.md S6 -- a second `worker.py` (CLI or another
    dashboard instance) against the SAME database raises immediately
    instead of silently running two engine processes against one queue."""
    if reuse_evals is None:
        # .get() with a default, not a bare key lookup: a packaged install's
        # user config.yaml is backfilled on launch (config.backfill_missing_keys),
        # but this in-process path can also be reached with an older config in
        # unusual sequences -- degrade to the shipped default, not a KeyError.
        reuse_evals = load_config()["engine"].get("reuse_evals", True)

    joblock.acquire()
    migrate(db_path)
    conn = get_connection(db_path)

    path = find_engine_path(engine_path)
    if not path:
        # raise, not sys.exit() -- this is called in-process from the
        # packaged app now, not just as a standalone CLI script, and
        # SystemExit would otherwise silently kill the whole dashboard
        # server it's running inside.
        conn.close()
        joblock.release()
        raise RuntimeError(
            "Could not find a stockfish binary. Install it (e.g. `sudo apt install stockfish`) "
            "or set engine.path in config.yaml / pass --engine-path.")

    engine = chess.engine.SimpleEngine.popen_uci(path)
    configure_supported(engine, {"Threads": threads, "Hash": hash_mb})
    engine_version = engine.id.get("name", "unknown")
    print(f"Engine: {engine_version} | depth={depth} multipv={multipv} threads={threads} hash={hash_mb}MB "
          f"| max_games={max_games} max_duration={max_duration_s} "
          f"backlog_quota={backlog_quota} (window={backlog_quota_window}) "
          f"reuse_evals={reuse_evals}")

    cur = conn.execute("""
        INSERT INTO analysis_runs (started_at, engine_version, depth, multipv, threads, hash_mb,
                                    hostname, platform, cpu_count)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, (now_iso(), engine_version, depth, multipv, threads, hash_mb,
          socket.gethostname(), platform.platform(), os.cpu_count()))
    run_id = cur.lastrowid
    conn.commit()

    start_time = time.monotonic()
    deadline = (start_time + max_duration_s) if max_duration_s is not None else None
    games_done = 0
    total_plies = 0
    consecutive_failures = 0
    # Cumulative for the whole session, mutated in place by every analyze_game()
    # call below. Same hit-rate definition the Analysis Jobs GUI tile uses
    # (reused / (reused + engine) among ply<=REUSE_EVAL_MAX_PLY) -- this is
    # just the in-process-counter route to it instead of a query, since the
    # CLI has no reason to hit the DB again for a number it already knows.
    cache_stats = {"eligible": 0, "reused": 0}

    try:
        while True:
            if max_games is not None and games_done >= max_games:
                print(f"Stopping: reached --max-games {max_games}.")
                break
            if deadline is not None and time.monotonic() >= deadline:
                print(f"Stopping: reached --max-duration ({max_duration_s}s elapsed).")
                break
            if stop_event is not None and stop_event.is_set():
                print("Stopping: cancelled.")
                break

            game_row = fetch_next_game(conn, backlog_quota, backlog_quota_window)
            if game_row is None:
                print("Queue empty -- all games analyzed.")
                break

            game_id = game_row[0]
            t0 = time.monotonic()
            try:
                n_plies, finished = analyze_game(conn, engine, game_row, depth, multipv, pv_max_len,
                                                  commit_every_n_moves, engine_version, run_id, deadline,
                                                  stop_event=stop_event, reuse_evals=reuse_evals,
                                                  cache_stats=cache_stats)
                consecutive_failures = 0
            except chess.engine.EngineTerminatedError:
                raise  # engine itself died; not worth continuing the batch
            except Exception as e:
                consecutive_failures += 1
                print(f"  FAILED game {game_id}: {e}", file=sys.stderr)
                conn.execute("UPDATE games SET analysis_status='failed' WHERE id=?", (game_id,))
                conn.commit()
                if consecutive_failures >= consecutive_failure_limit:
                    print(f"{consecutive_failure_limit} consecutive failures -- stopping batch to avoid "
                          "silently failing the whole queue. Investigate before resuming.", file=sys.stderr)
                    break
                continue

            dt = time.monotonic() - t0
            games_done += 1
            total_plies += n_plies
            elapsed = time.monotonic() - start_time
            avg_per_game = elapsed / games_done
            remaining = conn.execute(
                "SELECT COUNT(*) FROM games WHERE analysis_status IN ('pending','in_progress')"
            ).fetchone()[0]
            eta_h = (remaining * avg_per_game) / 3600
            status = "done" if finished else "paused (duration limit mid-game)"
            # Cache fragment omitted entirely when no eligible (ply<=REUSE_EVAL_MAX_PLY)
            # plies have been touched yet this session -- naturally covers both
            # reuse_evals=False and "batch hasn't reached any eligible ply yet",
            # matching this codebase's existing "don't clutter when there's
            # nothing to show" convention (e.g. the annotation-pass-now section
            # in dashboard/analysis_jobs_view.py).
            cache_fragment = ""
            if cache_stats["eligible"] > 0:
                rate = cache_stats["reused"] / cache_stats["eligible"]
                cache_fragment = (f" | cache {cache_stats['reused']}/{cache_stats['eligible']} "
                                   f"eligible plies reused ({rate:.0%})")
            print(f"[{games_done}] game {game_id}: {n_plies} plies in {dt:.1f}s [{status}] "
                  f"| session avg {avg_per_game:.1f}s/game | {remaining} games left "
                  f"(~{eta_h:.1f}h at current pace){cache_fragment}")
            conn.execute("""
                UPDATE analysis_runs SET games_analyzed=?, plies_analyzed=? WHERE id=?
            """, (games_done, total_plies, run_id))
            conn.commit()
            if on_game_done is not None:
                on_game_done(games_done, n_plies, finished)
            if not finished:
                print("Stopping: reached --max-duration mid-game (resumable next run).")
                break
    except KeyboardInterrupt:
        print("\nInterrupted -- progress already committed, safe to resume.")
    finally:
        conn.execute("UPDATE analysis_runs SET ended_at=?, games_analyzed=?, plies_analyzed=? WHERE id=?",
                      (now_iso(), games_done, total_plies, run_id))
        conn.commit()
        engine.quit()
        conn.close()
        joblock.release()

    if games_done > 0:
        achievements_conn = None
        try:
            achievements_conn = get_connection(db_path)
            achievements.evaluate(achievements_conn, "analysis")
        except Exception as e:
            print(f"WARNING: achievement evaluation failed (analysis batch unaffected): {e}")
        finally:
            if achievements_conn is not None:
                achievements_conn.close()

    summary_cache_fragment = ""
    if cache_stats["eligible"] > 0:
        rate = cache_stats["reused"] / cache_stats["eligible"]
        summary_cache_fragment = (f" | cache {cache_stats['reused']}/{cache_stats['eligible']} "
                                   f"eligible plies reused ({rate:.0%})")
    print(f"Session summary: {games_done} games, {total_plies} plies, "
          f"{time.monotonic()-start_time:.1f}s elapsed.{summary_cache_fragment}")
    return run_id


def main(argv=None):
    """CLI entrypoint. argv=None means "read real sys.argv[1:]" (argparse's
    own default) -- preserves `python3 worker.py ...`'s exact existing
    behavior. Extracted out of a bare `if __name__ == "__main__":` block so
    desktop_app.py's frozen `--run-worker` mode can call this SAME argparse
    surface and dispatch path in-process, instead of duplicating flag
    definitions or (worse) re-invoking `sys.executable worker.py` as a
    subprocess -- which breaks once frozen, since sys.executable IS the
    single bundled exe there (same reason desktop_app.py's own module
    docstring already documents for why --server-mode re-invokes itself
    instead of shelling out to a second script)."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=None)
    ap.add_argument("--depth", type=int, default=None)
    ap.add_argument("--multipv", type=int, default=None)
    ap.add_argument("--threads", type=int, default=None)
    ap.add_argument("--hash", type=int, default=None, help="Hash table size in MB")
    ap.add_argument("--pv-max-len", type=int, default=None)
    ap.add_argument("--engine-path", default=None)
    ap.add_argument("--max-games", type=int, default=None)
    ap.add_argument("--max-duration", default=None, help="e.g. 2h, 90m, 5400s")
    ap.add_argument("--consecutive-failure-limit", type=int, default=None)
    ap.add_argument("--commit-every-n-moves", type=int, default=None)
    ap.add_argument("--backlog-quota", type=float, default=None,
                     help="0.0-1.0: minimum share of the last --backlog-quota-window analyzed "
                          "games guaranteed to the historical backlog, even while recency-bumped "
                          "games are pending.")
    ap.add_argument("--backlog-quota-window", type=int, default=None,
                     help="How many of the most recently analyzed games backlog-quota looks at.")
    ap.add_argument("--config", default=None, help="Path to config.yaml (default: ./config.yaml)")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    db_path = pick(args.db, cfg["database"]["path"])
    depth = pick(args.depth, cfg["engine"]["depth"])
    multipv = pick(args.multipv, cfg["engine"]["multipv"])
    threads = pick(args.threads, cfg["engine"]["threads"])
    hash_mb = pick(args.hash, cfg["engine"]["hash_mb"])
    pv_max_len = pick(args.pv_max_len, cfg["engine"]["pv_max_len"])
    engine_path = pick(args.engine_path, cfg["engine"]["path"])
    max_games = pick(args.max_games, cfg["worker"]["max_games"])
    max_duration_s = parse_duration(pick(args.max_duration, cfg["worker"]["max_duration"]))
    consecutive_failure_limit = pick(args.consecutive_failure_limit, cfg["worker"]["consecutive_failure_limit"])
    commit_every_n_moves = pick(args.commit_every_n_moves, cfg["worker"]["commit_every_n_moves"])
    backlog_quota = pick(args.backlog_quota, cfg["ingestion"]["backlog_quota"])
    backlog_quota_window = pick(args.backlog_quota_window, cfg["ingestion"]["backlog_quota_window"])
    # No CLI override, matching the existing use_lichess_cloud_eval config knob
    # (dashboard/live_engine.py) -- config-only, no flag on any root-module CLI
    # today. Resolved here (not left to run()'s own None fallback) so a --config
    # path is honored; .get() so an un-backfilled older config means the default.
    reuse_evals = cfg["engine"].get("reuse_evals", True)

    run(db_path, depth, multipv, threads, hash_mb, pv_max_len, engine_path,
        max_games, max_duration_s, consecutive_failure_limit, commit_every_n_moves,
        backlog_quota=backlog_quota, backlog_quota_window=backlog_quota_window,
        reuse_evals=reuse_evals)


if __name__ == "__main__":
    main()
