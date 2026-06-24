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
"""
import argparse
import json
import shutil
import sqlite3
import sys
import time
import datetime
import platform
import socket
import os

import chess
import chess.engine

from migrate import migrate
from db import get_connection
from config import load_config, pick
import joblock


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def parse_duration(s):
    """'2h' -> 7200, '90m' -> 5400, '300' -> 300 (bare seconds)."""
    if s is None:
        return None
    s = str(s).strip().lower()
    units = {"h": 3600, "m": 60, "s": 1}
    if s and s[-1] in units:
        return int(float(s[:-1]) * units[s[-1]])
    return int(s)


def find_engine_path(explicit_path):
    if explicit_path:
        return explicit_path
    for candidate in ("stockfish", "/usr/games/stockfish", "/usr/bin/stockfish", "/usr/local/bin/stockfish"):
        found = shutil.which(candidate) or (candidate if candidate.startswith("/") else None)
        if found:
            import os
            if os.path.exists(found) and os.access(found, os.X_OK):
                return found
    return None


def configure_supported(engine, desired: dict):
    """Like engine.configure(desired), but silently drops any option name
    the connected engine doesn't actually report supporting, rather than
    letting python-chess raise. "Threads"/"Hash" are near-universal across
    classical UCI engines (Stockfish, Komodo, Ethereal, ...) but not every
    UCI-compliant engine exposes both -- some NN-based engines don't -- and
    this app now accepts ANY UCI engine the user points it at (the
    Settings/onboarding engine picker), not just Stockfish specifically."""
    supported = {name: value for name, value in desired.items() if name in engine.options}
    if supported:
        engine.configure(supported)


def validate_engine_path(path: str) -> str:
    """Confirms `path` is a real, working UCI engine by actually performing
    the UCI handshake (popen_uci already does this) -- returns the engine's
    self-reported name (engine.id["name"]), or raises RuntimeError with a
    clear message on any failure. Used by the engine-picker UI (onboarding
    + Settings) to reject a wrong file before it's accepted as engine.path,
    rather than discovering the problem on the next real analysis run."""
    try:
        engine = chess.engine.SimpleEngine.popen_uci(path)
    except Exception as e:
        raise RuntimeError(
            f"Couldn't start this as a UCI chess engine: {e}") from e
    try:
        return engine.id.get("name", "unknown engine")
    finally:
        engine.quit()


def fetch_next_game(conn):
    row = conn.execute("""
        SELECT id, num_plies, last_analyzed_ply
        FROM games
        WHERE analysis_status IN ('pending', 'in_progress')
        ORDER BY queue_order ASC
        LIMIT 1
    """).fetchone()
    return row


def score_to_fields(score, mover_color):
    """Score relative to the player to move. Returns (eval_cp, eval_mate)."""
    pov = score.pov(mover_color)
    if pov.is_mate():
        return None, pov.mate()
    return pov.score(), None


def analyze_game(conn, engine, game_row, depth, multipv, pv_max_len, commit_every_n_moves,
                  engine_version, run_id, deadline=None, max_plies=None, stop_event=None):
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

        t0 = time.monotonic()
        lines = engine.analyse(board, chess.engine.Limit(depth=depth), multipv=multipv)
        search_time_ms = int((time.monotonic() - t0) * 1000)

        # lines is a list (one dict per PV rank), ordered best-first
        rank1 = lines[0]
        eval_cp, eval_mate = score_to_fields(rank1["score"], mover_color)
        rank1_exact = 0 if (rank1.get("upperbound") or rank1.get("lowerbound")) else 1
        engine_reported_time_ms = int(rank1["time"] * 1000) if "time" in rank1 else None

        pv_moves = rank1.get("pv", [])[:pv_max_len]
        pv_board = board.copy()
        pv_san = []
        best_move_san = None
        for i, mv in enumerate(pv_moves):
            san_mv = pv_board.san(mv)
            if i == 0:
                best_move_san = san_mv
            pv_san.append(san_mv)
            pv_board.push(mv)

        conn.execute("""
            UPDATE moves SET
                eval_cp=?, eval_mate=?, best_move_san=?, pv_json=?,
                nodes=?, engine_depth=?, engine_version=?,
                seldepth=?, search_time_ms=?, analysis_run_id=?,
                hashfull=?, tbhits=?, nps=?, engine_reported_time_ms=?, score_is_exact=?
            WHERE id=?
        """, (
            eval_cp, eval_mate, best_move_san, json.dumps(pv_san),
            rank1.get("nodes"), rank1.get("depth", depth), engine_version,
            rank1.get("seldepth"), search_time_ms, run_id,
            rank1.get("hashfull"), rank1.get("tbhits"), rank1.get("nps"),
            engine_reported_time_ms, rank1_exact,
            move_id,
        ))

        # all ranks (including rank 1, stored redundantly for a uniform query shape).
        # nodes/hashfull/tbhits/nps/time are global to the whole search call
        # (confirmed identical across ranks), so they live on `moves` only,
        # not duplicated here.
        for rank, line in enumerate(lines, start=1):
            line_cp, line_mate = score_to_fields(line["score"], mover_color)
            line_exact = 0 if (line.get("upperbound") or line.get("lowerbound")) else 1
            line_pv = line.get("pv", [])[:pv_max_len]
            lb = board.copy()
            line_san_list = []
            line_best_san = None
            for i, mv in enumerate(line_pv):
                s = lb.san(mv)
                if i == 0:
                    line_best_san = s
                line_san_list.append(s)
                lb.push(mv)
            conn.execute("""
                INSERT OR REPLACE INTO move_lines
                    (move_id, pv_rank, eval_cp, eval_mate, move_san, pv_json, score_is_exact, seldepth)
                VALUES (?,?,?,?,?,?,?,?)
            """, (move_id, rank, line_cp, line_mate, line_best_san, json.dumps(line_san_list),
                  line_exact, line.get("seldepth")))

        conn.execute("UPDATE games SET last_analyzed_ply=? WHERE id=?", (ply, game_id))
        moves_since_commit += 1
        if moves_since_commit >= commit_every_n_moves:
            conn.commit()  # default 1: commit per-move, a crash loses at most the in-flight position
            moves_since_commit = 0

        board.push_san(san)
        analyzed_this_game += 1

        eval_str = f"M{eval_mate}" if eval_mate is not None else f"{eval_cp/100:+.2f}"
        print(f"    ply {ply}/{num_plies}  {san:<8} eval={eval_str:>7}  "
              f"best={best_move_san or '-':<8} {search_time_ms/1000:.1f}s", flush=True)

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
            n_plies, _finished = analyze_game(conn, engine, game_row, depth, multipv, pv_max_len,
                                               commit_every_n_moves=1, engine_version=engine_version,
                                               run_id=run_id, max_plies=remaining)
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


def run(db_path, depth, multipv, threads, hash_mb, pv_max_len, engine_path,
         max_games, max_duration_s, consecutive_failure_limit, commit_every_n_moves,
         on_game_done=None, stop_event=None):
    """on_game_done(games_done, n_plies, finished): optional callback fired
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
          f"| max_games={max_games} max_duration={max_duration_s}")

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

            game_row = fetch_next_game(conn)
            if game_row is None:
                print("Queue empty -- all games analyzed.")
                break

            game_id = game_row[0]
            t0 = time.monotonic()
            try:
                n_plies, finished = analyze_game(conn, engine, game_row, depth, multipv, pv_max_len,
                                                  commit_every_n_moves, engine_version, run_id, deadline,
                                                  stop_event=stop_event)
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
            print(f"[{games_done}] game {game_id}: {n_plies} plies in {dt:.1f}s [{status}] "
                  f"| session avg {avg_per_game:.1f}s/game | {remaining} games left "
                  f"(~{eta_h:.1f}h at current pace)")
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

    print(f"Session summary: {games_done} games, {total_plies} plies, "
          f"{time.monotonic()-start_time:.1f}s elapsed.")


if __name__ == "__main__":
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
    ap.add_argument("--config", default=None, help="Path to config.yaml (default: ./config.yaml)")
    args = ap.parse_args()

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

    run(db_path, depth, multipv, threads, hash_mb, pv_max_len, engine_path,
        max_games, max_duration_s, consecutive_failure_limit, commit_every_n_moves)
