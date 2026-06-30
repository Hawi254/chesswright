#!/usr/bin/env python3
"""
Phase 4a: Core rollups -- ACPL & blunder rate by context.

Pure read-only SQL aggregation over already-stored moves/games columns.
No new migration, nothing written back -- re-running this after more
worker.py batches complete just reflects more data. Every section states
its own sample size so a stat from a handful of analyzed games is never
mistaken for one covering the whole real dataset.

Usage:
    python3 analytics.py                       # full report
    python3 analytics.py --section opening      # one section only
"""
import argparse
import datetime
from collections import Counter

from db import get_connection
from config import load_config, pick
from chess_utils import non_pawn_piece_count

BASE_FILTER = "m.is_player_move=1 AND m.cpl IS NOT NULL"


def acpl_and_blunder_rate(conn, where_extra="", params=(), extra_join=""):
    """Returns (n_moves, n_games, acpl, blunder_rate_pct) over player's
    analyzed moves, optionally further filtered by where_extra (a SQL
    fragment ANDed onto the base filter) and/or extra_join (a SQL fragment
    inserted between FROM and WHERE, e.g. to join the session_ctx temp table).

    SECURITY: where_extra and extra_join are interpolated directly into the
    SQL query without escaping. They MUST be hardcoded string literals —
    never pass user-supplied or externally-sourced strings here. All values
    that vary at runtime must go through the params tuple instead.
    """
    where = BASE_FILTER if not where_extra else f"{BASE_FILTER} AND {where_extra}"
    row = conn.execute(f"""
        SELECT COUNT(*), COUNT(DISTINCT m.game_id), AVG(m.cpl),
               100.0 * SUM(CASE WHEN m.classification='blunder' THEN 1 ELSE 0 END) / COUNT(*)
        FROM moves m JOIN games g ON g.id = m.game_id {extra_join}
        WHERE {where}
    """, params).fetchone()
    n_moves, n_games, acpl, blunder_rate = row
    return n_moves or 0, n_games or 0, acpl, blunder_rate


def compute_session_context(conn, session_gap_minutes):
    """Walks ALL games (not just analyzed ones) in real chronological order
    and assigns, per game: session_game_number (1-indexed position within
    its session), prior_outcome (the immediately preceding game's outcome
    within the SAME session, None for the first game of a session), and
    losing_streak (consecutive prior losses within the same session).
    Session boundary = a gap of more than session_gap_minutes since the
    previous game's start (start-to-start, not end-to-start -- see plan
    note on why this simplification is fine for this dataset).

    Computed over all games (engine-analyzed or not) because outcome/
    timestamp are tier-2 ingest-time facts available regardless of
    analysis status -- only the ACPL/blunder-rate numbers later need a
    game to be analyzed, not the session structure itself."""
    rows = conn.execute("""
        SELECT id, utc_date, utc_time, outcome_for_player FROM games
        WHERE utc_date IS NOT NULL AND utc_date != ''
          AND utc_time IS NOT NULL AND utc_time != ''
        ORDER BY utc_date, utc_time, id
    """).fetchall()

    gap = datetime.timedelta(minutes=session_gap_minutes)
    context = []
    skipped = 0
    prev_dt = None
    prev_outcome = None
    session_game_number = 0
    losing_streak = 0

    for game_id, utc_date, utc_time, outcome in rows:
        try:
            dt = datetime.datetime.strptime(f"{utc_date} {utc_time}", "%Y.%m.%d %H:%M:%S")
        except ValueError:
            skipped += 1
            continue

        if prev_dt is None or (dt - prev_dt) > gap:
            session_game_number = 1
            prior_outcome = None
            losing_streak = 0
        else:
            session_game_number += 1
            prior_outcome = prev_outcome
            losing_streak = losing_streak + 1 if prev_outcome == "loss" else 0

        context.append((game_id, session_game_number, prior_outcome, losing_streak))
        prev_dt = dt
        prev_outcome = outcome

    return context, skipped


def classification_breakdown(conn, where_extra="", params=()):
    # SECURITY: where_extra must be a hardcoded SQL literal — see acpl_and_blunder_rate's docstring.
    where = BASE_FILTER if not where_extra else f"{BASE_FILTER} AND {where_extra}"
    return conn.execute(f"""
        SELECT m.classification, COUNT(*) FROM moves m JOIN games g ON g.id = m.game_id
        WHERE {where} GROUP BY m.classification ORDER BY COUNT(*) DESC
    """, params).fetchall()


def fmt_row(label, n_moves, n_games, acpl, blunder_rate, min_sample_size):
    flag = " (small sample)" if n_games < min_sample_size else ""
    acpl_str = f"{acpl:6.1f}" if acpl is not None else "   n/a"
    br_str = f"{blunder_rate:5.1f}%" if blunder_rate is not None else "  n/a"
    return f"  {label:<22} ACPL={acpl_str}  blunder_rate={br_str}  ({n_games} games, {n_moves} moves){flag}"


def report_overall(conn, min_sample_size):
    print("=== Overall summary ===")
    total_games = conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]
    done_games = conn.execute("SELECT COUNT(*) FROM games WHERE analysis_status='done'").fetchone()[0]
    n_moves, n_games, acpl, blunder_rate = acpl_and_blunder_rate(conn)
    pct = 100.0 * done_games / total_games if total_games else 0.0
    print(f"  {done_games} of {total_games} games engine-analyzed ({pct:.1f}%) -- "
          f"every stat below is based on this subset only.")
    print(fmt_row("overall", n_moves, n_games, acpl, blunder_rate, min_sample_size))
    print("  Classification breakdown:")
    for cls, count in classification_breakdown(conn):
        print(f"    {cls or 'NULL':<12} {count}")
    print()


def report_by_outcome(conn, min_sample_size):
    print("=== By outcome ===")
    for outcome in ("win", "loss", "draw"):
        n_moves, n_games, acpl, blunder_rate = acpl_and_blunder_rate(
            conn, "g.outcome_for_player=?", (outcome,))
        if n_games:
            print(fmt_row(outcome, n_moves, n_games, acpl, blunder_rate, min_sample_size))
    print()


def report_by_time_control(conn, min_sample_size):
    print("=== By time control ===")
    categories = conn.execute(
        "SELECT DISTINCT time_control_category FROM games WHERE time_control_category IS NOT NULL"
    ).fetchall()
    rows = []
    for (cat,) in categories:
        n_moves, n_games, acpl, blunder_rate = acpl_and_blunder_rate(
            conn, "g.time_control_category=?", (cat,))
        if n_games:
            print(fmt_row(cat, n_moves, n_games, acpl, blunder_rate, min_sample_size))
            rows.append({"label": cat, "n": n_games, "n_moves": n_moves,
                         "acpl": acpl, "blunder_rate": blunder_rate})
    print()
    return rows


def report_by_opening(conn, min_sample_size, min_games_per_group, top_n):
    print(f"=== By opening (top {top_n} most-played, min {min_games_per_group} analyzed games, worst ACPL first) ===")
    openings = conn.execute("""
        SELECT DISTINCT g.opening_family FROM games g
        JOIN moves m ON m.game_id = g.id
        WHERE g.opening_family IS NOT NULL AND """ + BASE_FILTER
    ).fetchall()
    rows = []
    for (opening,) in openings:
        n_moves, n_games, acpl, blunder_rate = acpl_and_blunder_rate(
            conn, "g.opening_family=?", (opening,))
        if n_games >= min_games_per_group:
            rows.append((opening, n_moves, n_games, acpl, blunder_rate))
    rows.sort(key=lambda r: (r[3] is None, -(r[3] or 0)))
    for opening, n_moves, n_games, acpl, blunder_rate in rows[:top_n]:
        print(fmt_row(opening, n_moves, n_games, acpl, blunder_rate, min_sample_size))
    print()


def report_by_rating_bucket(conn, min_sample_size, buckets):
    print("=== By rating differential ===")
    underdog_max = buckets["underdog_max"]
    favorite_min = buckets["favorite_min"]
    bucket_defs = [
        ("underdog", "g.rating_diff <= ?", (underdog_max,)),
        ("even", "g.rating_diff > ? AND g.rating_diff < ?", (underdog_max, favorite_min)),
        ("favorite", "g.rating_diff >= ?", (favorite_min,)),
    ]
    for label, where_extra, params in bucket_defs:
        n_moves, n_games, acpl, blunder_rate = acpl_and_blunder_rate(conn, where_extra, params)
        if n_games:
            print(fmt_row(label, n_moves, n_games, acpl, blunder_rate, min_sample_size))
    print()


def report_by_hour_bucket(conn, min_sample_size, buckets, utc_offset):
    print(f"=== By time of day (local, UTC+{utc_offset}) ===")
    rows = []
    for label, (start, end) in buckets.items():
        local_hours = [(h - utc_offset) % 24 for h in range(start, end)]
        placeholders = ",".join("?" * len(local_hours))
        n_moves, n_games, acpl, blunder_rate = acpl_and_blunder_rate(
            conn, f"g.hour_utc IN ({placeholders})", tuple(local_hours))
        if n_games:
            print(fmt_row(label, n_moves, n_games, acpl, blunder_rate, min_sample_size))
            rows.append({"label": label, "n": n_games, "n_moves": n_moves,
                         "acpl": acpl, "blunder_rate": blunder_rate})
    print()
    return rows


def report_by_day_of_week(conn, min_sample_size):
    print("=== By day of week ===")
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    rows = []
    for dow, label in enumerate(days):
        n_moves, n_games, acpl, blunder_rate = acpl_and_blunder_rate(
            conn, "g.day_of_week=?", (dow,))
        if n_games:
            print(fmt_row(label, n_moves, n_games, acpl, blunder_rate, min_sample_size))
            rows.append({"label": label, "n": n_games, "n_moves": n_moves,
                         "acpl": acpl, "blunder_rate": blunder_rate})
    print()
    return rows


def ensure_session_ctx(conn, session_gap_minutes):
    """Idempotent within a connection.

    Fast path (after migration 0023): if session_ctx_cache is current (game
    count unchanged since last build), the TEMP TABLE is created from the
    32k-row cache in <100ms instead of running compute_session_context()
    (~500ms).  Stale or absent cache falls back to a full rebuild and
    persists the result so the next start is fast.
    """
    if conn.execute("SELECT name FROM sqlite_temp_master WHERE name='session_ctx'").fetchone():
        return

    game_count = conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]
    meta = conn.execute("SELECT session_game_count FROM ctx_cache_meta WHERE id=1").fetchone()
    cache_current = (meta and meta[0] == game_count and game_count > 0
                     and conn.execute("SELECT COUNT(*) FROM session_ctx_cache").fetchone()[0] > 0)

    if cache_current:
        conn.execute("""CREATE TEMP TABLE session_ctx (
            game_id TEXT PRIMARY KEY, session_game_number INTEGER,
            prior_outcome TEXT, losing_streak INTEGER
        )""")
        conn.execute("INSERT INTO session_ctx SELECT * FROM session_ctx_cache")
        return

    context, skipped = compute_session_context(conn, session_gap_minutes)
    if skipped:
        print(f"  ({skipped} game(s) skipped from session analysis -- unparseable timestamp)")

    conn.execute("DELETE FROM session_ctx_cache")
    conn.executemany("INSERT INTO session_ctx_cache VALUES (?,?,?,?)", context)
    conn.execute("UPDATE ctx_cache_meta SET session_game_count=?, built_at=CURRENT_TIMESTAMP WHERE id=1",
                 (game_count,))
    conn.commit()

    conn.execute("""CREATE TEMP TABLE session_ctx (
        game_id TEXT PRIMARY KEY, session_game_number INTEGER,
        prior_outcome TEXT, losing_streak INTEGER
    )""")
    conn.execute("INSERT INTO session_ctx SELECT * FROM session_ctx_cache")


SESSION_JOIN = "JOIN session_ctx sc ON sc.game_id = g.id"


def report_by_session_position(conn, min_sample_size, cap):
    print(f"=== By position within session (game 1, 2, ... of a sitting) ===")
    rows = []
    for n in range(1, cap):
        n_moves, n_games, acpl, blunder_rate = acpl_and_blunder_rate(
            conn, "sc.session_game_number=?", (n,), extra_join=SESSION_JOIN)
        if n_games:
            print(fmt_row(f"game #{n}", n_moves, n_games, acpl, blunder_rate, min_sample_size))
            rows.append({"label": f"game #{n}", "n": n_games, "n_moves": n_moves,
                         "acpl": acpl, "blunder_rate": blunder_rate})
    n_moves, n_games, acpl, blunder_rate = acpl_and_blunder_rate(
        conn, "sc.session_game_number>=?", (cap,), extra_join=SESSION_JOIN)
    if n_games:
        print(fmt_row(f"game #{cap}+", n_moves, n_games, acpl, blunder_rate, min_sample_size))
        rows.append({"label": f"game #{cap}+", "n": n_games, "n_moves": n_moves,
                     "acpl": acpl, "blunder_rate": blunder_rate})
    print()
    return rows


def report_by_prior_outcome(conn, min_sample_size):
    print("=== By outcome of the PREVIOUS game in the same session (tilt) ===")
    rows = []
    n_moves, n_games, acpl, blunder_rate = acpl_and_blunder_rate(
        conn, "sc.prior_outcome IS NULL", (), extra_join=SESSION_JOIN)
    if n_games:
        print(fmt_row("first_game_of_session", n_moves, n_games, acpl, blunder_rate, min_sample_size))
        rows.append({"label": "first_game_of_session", "n": n_games, "n_moves": n_moves,
                     "acpl": acpl, "blunder_rate": blunder_rate})
    for outcome in ("win", "loss", "draw"):
        n_moves, n_games, acpl, blunder_rate = acpl_and_blunder_rate(
            conn, "sc.prior_outcome=?", (outcome,), extra_join=SESSION_JOIN)
        if n_games:
            print(fmt_row(f"after a {outcome}", n_moves, n_games, acpl, blunder_rate, min_sample_size))
            rows.append({"label": f"after a {outcome}", "n": n_games, "n_moves": n_moves,
                         "acpl": acpl, "blunder_rate": blunder_rate})
    print()
    return rows


def report_by_losing_streak(conn, min_sample_size, cap):
    print(f"=== By consecutive prior losses this session ===")
    for n in range(0, cap):
        n_moves, n_games, acpl, blunder_rate = acpl_and_blunder_rate(
            conn, "sc.losing_streak=?", (n,), extra_join=SESSION_JOIN)
        if n_games:
            print(fmt_row(f"{n} prior loss(es)", n_moves, n_games, acpl, blunder_rate, min_sample_size))
    n_moves, n_games, acpl, blunder_rate = acpl_and_blunder_rate(
        conn, "sc.losing_streak>=?", (cap,), extra_join=SESSION_JOIN)
    if n_games:
        print(fmt_row(f"{cap}+ prior losses", n_moves, n_games, acpl, blunder_rate, min_sample_size))
    print()


SESSION_SECTIONS = {"session_position", "prior_outcome", "losing_streak"}


def player_relative_sig(material_sig, player_color):
    """material_signature() always returns "WhiteSidevBlackSide" -- reorder
    to "playerSidevOpponentSide" so the same lived structure (e.g. "I have
    the bishop, opponent has the knight") doesn't fragment into two
    different buckets depending on which color the player happened to be."""
    if player_color == "white":
        return material_sig
    white_side, black_side = material_sig.split("v", 1)
    return f"{black_side}v{white_side}"


def compute_structure_context(conn, middlegame_ply, endgame_max_pieces):
    """One pass over ALL moves (any analysis status -- material_sig is
    board-derivable, not engine-dependent) building, per game:
    middlegame_sig (player-relative material_sig at the fixed ply
    checkpoint) and endgame_sig/endgame_ply (player-relative material_sig
    and ply number at the FIRST ply whose total non-pawn piece count drops
    to endgame_max_pieces or below). Games that never reach the checkpoint
    ply, or never simplify that far, simply contribute no row for that field."""
    colors = dict(conn.execute("SELECT id, player_color FROM games").fetchall())
    rows = conn.execute(
        "SELECT game_id, ply, material_sig FROM moves WHERE material_sig IS NOT NULL ORDER BY game_id, ply"
    ).fetchall()

    context = []
    cur_game = None
    middlegame_sig = None
    endgame_sig = None
    endgame_ply = None
    endgame_found = False

    def flush():
        if cur_game is not None:
            context.append((cur_game, middlegame_sig, endgame_sig, endgame_ply))

    for game_id, ply, sig in rows:
        if game_id != cur_game:
            flush()
            cur_game = game_id
            middlegame_sig = None
            endgame_sig = None
            endgame_ply = None
            endgame_found = False
        color = colors.get(game_id)
        rel_sig = player_relative_sig(sig, color) if color else sig
        if ply == middlegame_ply:
            middlegame_sig = rel_sig
        if not endgame_found and non_pawn_piece_count(sig) <= endgame_max_pieces:
            endgame_found = True
            endgame_sig = rel_sig
            endgame_ply = ply
    flush()
    return context


def ensure_structure_ctx(conn, cfg):
    """Idempotent within a connection.

    Fast path (after migration 0023): if structure_ctx_cache is current (game
    count unchanged since last build), the TEMP TABLE is created from the
    32k-row cache in <100ms instead of running compute_structure_context()
    (~11-12s cold on 32k games / 2.3M moves).  Stale or absent cache falls
    back to a full rebuild and persists the result for the next start.
    """
    if conn.execute("SELECT name FROM sqlite_temp_master WHERE name='structure_ctx'").fetchone():
        return

    game_count = conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]
    meta = conn.execute("SELECT structure_game_count FROM ctx_cache_meta WHERE id=1").fetchone()
    cache_current = (meta and meta[0] == game_count and game_count > 0
                     and conn.execute("SELECT COUNT(*) FROM structure_ctx_cache").fetchone()[0] > 0)

    if cache_current:
        conn.execute("""CREATE TEMP TABLE structure_ctx (
            game_id TEXT PRIMARY KEY, middlegame_sig TEXT, endgame_sig TEXT, endgame_ply INTEGER
        )""")
        conn.execute("INSERT INTO structure_ctx SELECT * FROM structure_ctx_cache")
        return

    context = compute_structure_context(
        conn, cfg["analytics"]["middlegame_ply"], cfg["analytics"]["endgame_max_pieces"])

    conn.execute("DELETE FROM structure_ctx_cache")
    conn.executemany("INSERT INTO structure_ctx_cache VALUES (?,?,?,?)", context)
    conn.execute("UPDATE ctx_cache_meta SET structure_game_count=?, built_at=CURRENT_TIMESTAMP WHERE id=1",
                 (game_count,))
    conn.commit()

    conn.execute("""CREATE TEMP TABLE structure_ctx (
        game_id TEXT PRIMARY KEY, middlegame_sig TEXT, endgame_sig TEXT, endgame_ply INTEGER
    )""")
    conn.execute("INSERT INTO structure_ctx SELECT * FROM structure_ctx_cache")


def fmt_structure_row(label, n_games, win, draw, loss, n_analyzed, acpl, blunder_rate, min_sample_size):
    flag = " (small sample)" if n_games < min_sample_size else ""
    pct = lambda x: f"{100.0*x/n_games:3.0f}%"
    line = f"  {label:<24} {n_games:>5} games  W{pct(win)}/D{pct(draw)}/L{pct(loss)}"
    if acpl is not None:
        line += f"  ACPL={acpl:5.1f} blunder={blunder_rate:4.1f}% ({n_analyzed} analyzed)"
    return line + flag


def _bulk_structure_outcome_and_acpl(conn, candidates, ply_for_acpl_sql, ply_params):
    """Returns (win, draw, loss, n_analyzed, acpl, blunder_rate) per
    structure signature, computed for ALL groups in candidates via 2
    queries total, not 2 per group -- material_structures.py was measured
    calling the (now-removed) one-group-at-a-time version 30+ times per
    run (15 middlegame groups + 15 endgame groups), each a real full-ish
    scan; the same N-queries-to-1 fix already applied in
    dashboard/data/openings.py's get_openings_table() and
    analysis/phase_accuracy.py."""
    all_game_ids = [gid for _, ids in candidates for gid in ids]
    sig_by_game = {gid: sig for sig, ids in candidates for gid in ids}
    if not all_game_ids:
        return {}
    placeholders = ",".join("?" * len(all_game_ids))

    outcomes_by_sig = {}
    for game_id, outcome in conn.execute(
        f"SELECT id, outcome_for_player FROM games WHERE id IN ({placeholders})", all_game_ids
    ).fetchall():
        outcomes_by_sig.setdefault(sig_by_game[game_id], Counter())[outcome] += 1

    acpl_acc = {}  # sig -> [n_analyzed, sum_cpl, n_blunder]
    for game_id, cpl, classification in conn.execute(f"""
        SELECT m.game_id, m.cpl, m.classification
        FROM moves m JOIN structure_ctx sc ON sc.game_id = m.game_id
        WHERE m.game_id IN ({placeholders}) AND {ply_for_acpl_sql}
          AND m.is_player_move=1 AND m.cpl IS NOT NULL
    """, all_game_ids + list(ply_params)).fetchall():
        acc = acpl_acc.setdefault(sig_by_game[game_id], [0, 0.0, 0])
        acc[0] += 1
        acc[1] += cpl
        if classification == "blunder":
            acc[2] += 1

    result = {}
    for sig, _ in candidates:
        outcomes = outcomes_by_sig.get(sig, Counter())
        n_analyzed, sum_cpl, n_blunder = acpl_acc.get(sig, [0, 0.0, 0])
        acpl = sum_cpl / n_analyzed if n_analyzed else None
        blunder_rate = 100.0 * n_blunder / n_analyzed if n_analyzed else None
        result[sig] = (outcomes.get("win", 0), outcomes.get("draw", 0), outcomes.get("loss", 0),
                       n_analyzed, acpl, blunder_rate)
    return result


def report_by_middlegame_structure(conn, min_sample_size, min_games_per_group, top_n, middlegame_ply):
    print(f"=== By middlegame structure (material at ply {middlegame_ply}, "
          f"top {top_n}, min {min_games_per_group} games) ===")
    groups = {}
    for game_id, sig in conn.execute(
        "SELECT game_id, middlegame_sig FROM structure_ctx WHERE middlegame_sig IS NOT NULL"
    ).fetchall():
        groups.setdefault(sig, []).append(game_id)
    candidates = [(sig, ids) for sig, ids in groups.items() if len(ids) >= min_games_per_group]
    candidates.sort(key=lambda r: -len(r[1]))
    candidates = candidates[:top_n]
    bulk = _bulk_structure_outcome_and_acpl(conn, candidates, "m.ply=?", (middlegame_ply,))
    out_rows = []
    for sig, game_ids in candidates:
        win, draw, loss, n_analyzed, acpl, blunder_rate = bulk[sig]
        print(fmt_structure_row(sig, len(game_ids), win, draw, loss, n_analyzed, acpl,
                                 blunder_rate, min_sample_size))
        out_rows.append({"label": sig, "n": len(game_ids), "win": win, "draw": draw, "loss": loss,
                         "win_pct": 100.0 * win / len(game_ids), "acpl": acpl,
                         "blunder_rate": blunder_rate, "n_analyzed": n_analyzed})
    print()
    return out_rows


def report_by_endgame_structure(conn, min_sample_size, min_games_per_group, top_n):
    print(f"=== By endgame structure (material at first ply reaching the "
          f"endgame threshold, top {top_n}, min {min_games_per_group} games) ===")
    groups = {}
    for game_id, sig in conn.execute(
        "SELECT game_id, endgame_sig FROM structure_ctx WHERE endgame_sig IS NOT NULL"
    ).fetchall():
        groups.setdefault(sig, []).append(game_id)
    candidates = [(sig, ids) for sig, ids in groups.items() if len(ids) >= min_games_per_group]
    candidates.sort(key=lambda r: -len(r[1]))
    candidates = candidates[:top_n]
    bulk = _bulk_structure_outcome_and_acpl(conn, candidates, "m.ply=sc.endgame_ply", ())
    out_rows = []
    for sig, game_ids in candidates:
        win, draw, loss, n_analyzed, acpl, blunder_rate = bulk[sig]
        print(fmt_structure_row(sig, len(game_ids), win, draw, loss, n_analyzed, acpl,
                                 blunder_rate, min_sample_size))
        out_rows.append({"label": sig, "n": len(game_ids), "win": win, "draw": draw, "loss": loss,
                         "win_pct": 100.0 * win / len(game_ids), "acpl": acpl,
                         "blunder_rate": blunder_rate, "n_analyzed": n_analyzed})
    print()
    return out_rows


STRUCTURE_SECTIONS = {"middlegame_structure", "endgame_structure"}


def run(db_path, cfg, section):
    conn = get_connection(db_path)
    min_sample_size = cfg["analytics"]["min_sample_size"]

    if section is None or section in SESSION_SECTIONS:
        ensure_session_ctx(conn, cfg["analytics"]["session_gap_minutes"])
    if section is None or section in STRUCTURE_SECTIONS:
        ensure_structure_ctx(conn, cfg)

    if section is None or section == "overall":
        report_overall(conn, min_sample_size)
    if section is None or section == "outcome":
        report_by_outcome(conn, min_sample_size)
    if section is None or section == "time_control":
        report_by_time_control(conn, min_sample_size)
    if section is None or section == "opening":
        report_by_opening(conn, min_sample_size,
                           cfg["analytics"]["min_games_per_group"],
                           cfg["analytics"]["top_n_openings"])
    if section is None or section == "rating":
        report_by_rating_bucket(conn, min_sample_size, cfg["analytics"]["rating_diff_buckets"])
    if section is None or section == "hour":
        report_by_hour_bucket(conn, min_sample_size, cfg["analytics"]["hour_buckets"],
                               cfg["analytics"]["utc_offset_hours"])
    if section is None or section == "day":
        report_by_day_of_week(conn, min_sample_size)
    if section is None or section == "session_position":
        report_by_session_position(conn, min_sample_size, cfg["analytics"]["session_position_cap"])
    if section is None or section == "prior_outcome":
        report_by_prior_outcome(conn, min_sample_size)
    if section is None or section == "losing_streak":
        report_by_losing_streak(conn, min_sample_size, cfg["analytics"]["losing_streak_cap"])
    if section is None or section == "middlegame_structure":
        report_by_middlegame_structure(conn, min_sample_size,
                                        cfg["analytics"]["structure_min_games_per_group"],
                                        cfg["analytics"]["structure_top_n"],
                                        cfg["analytics"]["middlegame_ply"])
    if section is None or section == "endgame_structure":
        report_by_endgame_structure(conn, min_sample_size,
                                     cfg["analytics"]["structure_min_games_per_group"],
                                     cfg["analytics"]["structure_top_n"])

    conn.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=None)
    ap.add_argument("--section", choices=["overall", "outcome", "time_control", "opening", "rating", "hour", "day",
                                           "session_position", "prior_outcome", "losing_streak",
                                           "middlegame_structure", "endgame_structure"],
                     default=None, help="Print just one section (default: full report)")
    ap.add_argument("--config", default=None, help="Path to config.yaml (default: ./config.yaml)")
    args = ap.parse_args()

    cfg = load_config(args.config)
    db_path = pick(args.db, cfg["database"]["path"])

    run(db_path, cfg, args.section)
