"""Time-pressure, time-control, session, and day/hour queries -- one of
eight topic modules split out of the former dashboard/data/patterns.py.
"""
import pandas as pd

import analytics
from connections import get_config

from .._shared import TIME_PRESSURE_BUCKETS, bucket_acpl_blunder_rate


def get_blunder_rate_by_time_pressure(duck_conn):
    df = duck_conn.execute("""
        SELECT m.cpl, m.classification,
               CAST(m.clock_seconds AS DOUBLE) / g.base_seconds AS time_fraction
        FROM db.moves m JOIN db.games g ON g.id = m.game_id
        WHERE m.is_player_move=1 AND m.cpl IS NOT NULL
          AND m.clock_seconds IS NOT NULL AND g.base_seconds IS NOT NULL AND g.base_seconds > 0
    """).fetchdf()
    return bucket_acpl_blunder_rate(df, "time_fraction", TIME_PRESSURE_BUCKETS)


def get_acpl_by_time_control(sqlite_conn):
    """One GROUP BY instead of one analytics.acpl_and_blunder_rate() call
    per DISTINCT time-control category -- each of those calls is a full
    indexed aggregate over every analyzed player move (~160ms measured on
    the real 2.3M-row moves table), so the loop paid ~1.0s where one
    grouped pass costs ~0.28s. Same N-queries-to-1 fix shape as
    get_openings_table / get_material_structure_table below. Verified
    value-identical to the per-category loop on the real database."""
    rows = sqlite_conn.execute("""
        SELECT g.time_control_category, COUNT(DISTINCT m.game_id), COUNT(*), AVG(m.cpl),
               100.0 * SUM(CASE WHEN m.classification='blunder' THEN 1 ELSE 0 END) / COUNT(*)
        FROM moves m JOIN games g ON g.id = m.game_id
        WHERE m.is_player_move=1 AND m.cpl IS NOT NULL
          AND g.time_control_category IS NOT NULL
        GROUP BY g.time_control_category
    """).fetchall()
    return pd.DataFrame(
        [(cat, n_games, n_moves, acpl, blunder_rate)
         for cat, n_games, n_moves, acpl, blunder_rate in rows],
        columns=["time_control", "n_games", "n_moves", "acpl", "blunder_rate"])


def get_phase_accuracy(sqlite_conn, config_path=None):
    """One CASE-bucketed GROUP BY instead of three acpl_and_blunder_rate
    calls (~0.58s -> ~0.25s measured; see get_acpl_by_time_control). The
    CASE is the same exclusive phase partition get_piece_blunder_by_phase
    and tactical.py's knight-rim query already use -- note the old
    three-WHERE version could in principle count a move in BOTH 'opening'
    and 'endgame' when a game simplifies before middlegame_ply (verified:
    zero such moves in the real database, so results are identical)."""
    cfg = get_config(config_path)
    analytics.ensure_structure_ctx(sqlite_conn, cfg)
    middlegame_ply = cfg["analytics"]["middlegame_ply"]
    rows = sqlite_conn.execute(f"""
        SELECT CASE WHEN m.ply < {middlegame_ply} THEN 'opening'
                    WHEN sc.endgame_ply IS NULL OR m.ply < sc.endgame_ply THEN 'middlegame'
                    ELSE 'endgame' END AS phase,
               COUNT(DISTINCT m.game_id), COUNT(*), AVG(m.cpl),
               100.0 * SUM(CASE WHEN m.classification='blunder' THEN 1 ELSE 0 END) / COUNT(*)
        FROM moves m JOIN games g ON g.id = m.game_id
        JOIN structure_ctx sc ON sc.game_id = g.id
        WHERE m.is_player_move=1 AND m.cpl IS NOT NULL
        GROUP BY 1
        ORDER BY CASE phase WHEN 'opening' THEN 0 WHEN 'middlegame' THEN 1 ELSE 2 END
    """).fetchall()
    return pd.DataFrame(
        [(phase, n_games, n_moves, acpl, blunder_rate)
         for phase, n_games, n_moves, acpl, blunder_rate in rows],
        columns=["phase", "n_games", "n_moves", "acpl", "blunder_rate"])


def get_prior_outcome_performance(sqlite_conn, config_path=None):
    """One GROUP BY instead of four acpl_and_blunder_rate calls (~0.69s ->
    ~0.23s measured; see get_acpl_by_time_control)."""
    cfg = get_config(config_path)
    analytics.ensure_session_ctx(sqlite_conn, cfg["analytics"]["session_gap_minutes"])
    rows = sqlite_conn.execute("""
        SELECT CASE WHEN sc.prior_outcome IS NULL THEN 'first_game_of_session'
                    ELSE 'after a ' || sc.prior_outcome END AS bucket,
               COUNT(DISTINCT m.game_id), COUNT(*), AVG(m.cpl),
               100.0 * SUM(CASE WHEN m.classification='blunder' THEN 1 ELSE 0 END) / COUNT(*)
        FROM moves m JOIN games g ON g.id = m.game_id
        JOIN session_ctx sc ON sc.game_id = g.id
        WHERE m.is_player_move=1 AND m.cpl IS NOT NULL
        GROUP BY 1
        ORDER BY CASE bucket WHEN 'first_game_of_session' THEN 0 WHEN 'after a win' THEN 1
                             WHEN 'after a loss' THEN 2 ELSE 3 END
    """).fetchall()
    return pd.DataFrame(
        [(bucket, n_games, n_moves, acpl, blunder_rate)
         for bucket, n_games, n_moves, acpl, blunder_rate in rows],
        columns=["bucket", "n_games", "n_moves", "acpl", "blunder_rate"])


def get_session_position_performance(sqlite_conn, config_path=None):
    """One GROUP BY (bucketing session_game_number at the cap via the
    two-argument scalar MIN) instead of cap+1 acpl_and_blunder_rate calls
    (~0.65s -> ~0.23s measured; see get_acpl_by_time_control)."""
    cfg = get_config(config_path)
    analytics.ensure_session_ctx(sqlite_conn, cfg["analytics"]["session_gap_minutes"])
    cap = cfg["analytics"]["session_position_cap"]
    rows = sqlite_conn.execute("""
        SELECT MIN(sc.session_game_number, ?) AS pos,
               COUNT(DISTINCT m.game_id), COUNT(*), AVG(m.cpl),
               100.0 * SUM(CASE WHEN m.classification='blunder' THEN 1 ELSE 0 END) / COUNT(*)
        FROM moves m JOIN games g ON g.id = m.game_id
        JOIN session_ctx sc ON sc.game_id = g.id
        WHERE m.is_player_move=1 AND m.cpl IS NOT NULL
        GROUP BY 1 ORDER BY 1
    """, (cap,)).fetchall()
    return pd.DataFrame(
        [(f"game #{pos}" if pos < cap else f"game #{cap}+",
          n_games, n_moves, acpl, blunder_rate)
         for pos, n_games, n_moves, acpl, blunder_rate in rows],
        columns=["position", "n_games", "n_moves", "acpl", "blunder_rate"])


def get_day_hour_heatmap(duck_conn, config_path=None):
    """day_of_week x hour_local win rate, full dataset (board-derived).
    hour_local = (hour_utc + analytics.utc_offset_hours) % 24 -- shifts the
    HOUR axis only into the player's own local time; day_of_week is left
    alone, matching this app's older CLI report_by_hour_bucket convention
    (analytics.py) of never cross-adjusting the day when converting hours.

    Also returns avg_rating_diff pivoted to the same (day_of_week,
    hour_local) shape -- a confidence-gap disclaimer, not a new finding:
    win% varies by hour partly because the opponent pool's average
    strength varies by hour too, not only because of how the player
    performs at that hour. Verified live (2026-07-07) on the real dev DB:
    hours 17-18 UTC combine both the most favorable average rating_diff
    (+33 to +37) and the highest win% (49-50%), while hours 20-23 combine
    a negative rating_diff (-20 to -35) with some of the lowest win%, so a
    bare win% cell can't tell "played worse at this hour" apart from
    "faced tougher opponents at this hour." Returns (win_pct_pivot,
    avg_rating_diff_pivot) -- callers pass the second into charts.heatmap's
    hover_extra, they are never blended into one number."""
    cfg = get_config(config_path)
    utc_offset_hours = cfg["analytics"]["utc_offset_hours"]
    df = duck_conn.execute("""
        SELECT day_of_week, hour_utc,
               COUNT(*) AS n,
               100.0 * SUM(CASE WHEN outcome_for_player='win' THEN 1 ELSE 0 END) / COUNT(*) AS win_pct,
               AVG(rating_diff) AS avg_rating_diff
        FROM db.games
        WHERE day_of_week IS NOT NULL AND hour_utc IS NOT NULL AND outcome_for_player IS NOT NULL
        GROUP BY day_of_week, hour_utc
    """).fetchdf()
    df["hour_local"] = (df["hour_utc"] + utc_offset_hours) % 24
    win_pivot = df.pivot(index="day_of_week", columns="hour_local", values="win_pct")
    rating_pivot = df.pivot(index="day_of_week", columns="hour_local", values="avg_rating_diff")
    return win_pivot, rating_pivot


def get_session_rollup(sqlite_conn, config_path=None):
    """Per-session W/D/L% and ACPL rollup -- the Playing Sessions unit
    (roadmap §15 unit #4). Extends get_prior_outcome_performance/
    get_session_position_performance's session_ctx JOIN, but keyed on the
    session itself (session_start, unique per session -- broadcast onto
    every game in that session by compute_session_context's second pass,
    see analytics.py) rather than folded into either function's handful of
    shared cross-session labels.

    Uses the SAME per-game combined-query shape as get_castling_performance/
    get_favorite_underdog_performance above (one row per game with its own
    mean_cpl/n_cpl_moves, aggregated in pandas afterward) rather than a
    single SQL GROUP BY directly on session_start with a moves JOIN -- a
    LEFT JOIN moves fans a game out to one row per move, which would make
    a naive SUM(CASE WHEN outcome_for_player='win' ...) overcount by the
    game's own move count; aggregating per-game first avoids that.

    No min-games gate on the rollup itself (unlike every other ACPL query
    in this module) -- most sessions are short (session_position_cap is
    typically single digits, see config.yaml), so a min-games floor would
    hide most sessions; ACPL coverage disclosure is the view layer's job
    (patterns_view.py's existing _coverage_caption helper), not this
    function's.

    Games with no recorded outcome_for_player are excluded, matching every
    other win/draw/loss query in this package (get_openings_table,
    get_castling_performance, etc.).

    Returns one row per session: session_start, session_end, n_games,
    win_pct, draw_pct, loss_pct, acpl, n_analyzed (n_analyzed is a MOVE
    count, matching get_material_structure_table's acpl_lookup convention
    -- acpl is None and n_analyzed is 0 for a session with zero analyzed
    moves, not a dropped row)."""
    cfg = get_config(config_path)
    analytics.ensure_session_ctx(sqlite_conn, cfg["analytics"]["session_gap_minutes"])
    rows = sqlite_conn.execute("""
        SELECT sc.session_start, sc.session_end, g.id AS game_id, g.outcome_for_player,
               AVG(CASE WHEN m.is_player_move=1 AND m.cpl IS NOT NULL THEN m.cpl END) AS mean_cpl,
               COUNT(CASE WHEN m.is_player_move=1 AND m.cpl IS NOT NULL THEN 1 END)   AS n_cpl_moves
        FROM session_ctx sc
        JOIN games g ON g.id = sc.game_id
        LEFT JOIN moves m ON m.game_id = g.id
        WHERE g.outcome_for_player IS NOT NULL
        GROUP BY sc.session_start, sc.session_end, g.id, g.outcome_for_player
    """).fetchall()
    cols = ["session_start", "session_end", "n_games", "win_pct", "draw_pct", "loss_pct",
            "acpl", "n_analyzed"]
    df = pd.DataFrame(rows, columns=["session_start", "session_end", "game_id",
                                      "outcome_for_player", "mean_cpl", "n_cpl_moves"])
    if df.empty:
        return pd.DataFrame(columns=cols)

    out_rows = []
    for (start, end), sub in df.groupby(["session_start", "session_end"], sort=True):
        n_games = len(sub)
        win_pct = 100.0 * (sub.outcome_for_player == "win").sum() / n_games
        draw_pct = 100.0 * (sub.outcome_for_player == "draw").sum() / n_games
        loss_pct = 100.0 * (sub.outcome_for_player == "loss").sum() / n_games
        analyzed = sub[sub.n_cpl_moves > 0]
        n_analyzed = int(analyzed.n_cpl_moves.sum())
        acpl = ((analyzed.mean_cpl * analyzed.n_cpl_moves).sum() / n_analyzed) if n_analyzed else None
        out_rows.append((start, end, n_games, win_pct, draw_pct, loss_pct, acpl, n_analyzed))
    return pd.DataFrame(out_rows, columns=cols).sort_values("session_start").reset_index(drop=True)
