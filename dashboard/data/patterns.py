"""Patterns page queries -- time pressure, time control, sharpness,
thinking time, game phase, session position, day/hour heatmap,
material-structure win rate, piece-movement/castling tendencies.
"""
import pandas as pd

import analytics
from _common import get_config

from ._shared import (TIME_PRESSURE_BUCKETS, THINKING_TIME_BUCKETS, bucket_acpl_blunder_rate,
                       _fetchone_scalar)

# Mirrors analysis/sharpness_correlation.py's BUCKETS.
SHARPNESS_BUCKETS = [
    ("flat (<5cp gap)", 0, 5),
    ("mild (5-25cp)", 5, 25),
    ("moderate (25-75cp)", 25, 75),
    ("sharp (75-200cp)", 75, 200),
    ("forcing (200cp+)", 200, 10**9),
]

PIECE_ORDER = ["Q", "R", "B", "N", "P", "K"]
PIECE_NAME = {"Q": "queen", "R": "rook", "B": "bishop", "N": "knight", "P": "pawn", "K": "king"}


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


def get_day_hour_heatmap(duck_conn):
    """New cross-tab, not built in Phase 5 -- day_of_week x hour_utc win
    rate, full dataset (board-derived).

    Also returns avg_rating_diff pivoted to the same (day_of_week, hour_utc)
    shape -- a confidence-gap disclaimer, not a new finding: win% varies by
    hour partly because the opponent pool's average strength varies by hour
    too, not only because of how the player performs at that hour. Verified
    live (2026-07-07) on the real dev DB: hours 17-18 UTC combine both the
    most favorable average rating_diff (+33 to +37) and the highest win%
    (49-50%), while hours 20-23 combine a negative rating_diff (-20 to -35)
    with some of the lowest win%, so a bare win% cell can't tell "played
    worse at this hour" apart from "faced tougher opponents at this hour."
    Returns (win_pct_pivot, avg_rating_diff_pivot) -- callers pass the
    second into charts.heatmap's hover_extra, they are never blended into
    one number."""
    df = duck_conn.execute("""
        SELECT day_of_week, hour_utc,
               COUNT(*) AS n,
               100.0 * SUM(CASE WHEN outcome_for_player='win' THEN 1 ELSE 0 END) / COUNT(*) AS win_pct,
               AVG(rating_diff) AS avg_rating_diff
        FROM db.games
        WHERE day_of_week IS NOT NULL AND hour_utc IS NOT NULL AND outcome_for_player IS NOT NULL
        GROUP BY day_of_week, hour_utc
    """).fetchdf()
    win_pivot = df.pivot(index="day_of_week", columns="hour_utc", values="win_pct")
    rating_pivot = df.pivot(index="day_of_week", columns="hour_utc", values="avg_rating_diff")
    return win_pivot, rating_pivot


def get_material_structure_table(sqlite_conn, structure_type="endgame", config_path=None, top_n=15):
    """structure_type: 'middlegame' or 'endgame'. Bulk GROUP BY for both
    outcome and ACPL, not one query pair per structure -- the original
    version (one analytics.structure_outcome_and_acpl call per candidate)
    measured ~10s for 15 structures; this does the same work in 2 queries
    total, same reasoning as the get_openings_table fix above."""
    cfg = get_config(config_path)
    analytics.ensure_structure_ctx(sqlite_conn, cfg)
    min_games = cfg["analytics"]["structure_min_games_per_group"]
    sig_col = "middlegame_sig" if structure_type == "middlegame" else "endgame_sig"

    counts = sqlite_conn.execute(f"""
        SELECT {sig_col}, COUNT(*) AS n FROM structure_ctx
        WHERE {sig_col} IS NOT NULL GROUP BY {sig_col} HAVING COUNT(*) >= ?
        ORDER BY n DESC LIMIT ?
    """, (min_games, top_n)).fetchall()
    sigs = [sig for sig, _ in counts]
    if not sigs:
        return pd.DataFrame(columns=["material_sig", "n_games", "win_pct", "draw_pct", "loss_pct",
                                      "acpl", "n_analyzed"])
    placeholders = ",".join("?" * len(sigs))

    outcomes = sqlite_conn.execute(f"""
        SELECT sc.{sig_col}, g.outcome_for_player, COUNT(*) FROM structure_ctx sc
        JOIN games g ON g.id = sc.game_id
        WHERE sc.{sig_col} IN ({placeholders})
        GROUP BY sc.{sig_col}, g.outcome_for_player
    """, sigs).fetchall()
    outcome_lookup = {}
    for sig, outcome, n in outcomes:
        outcome_lookup.setdefault(sig, {})[outcome] = n

    if structure_type == "middlegame":
        ply_condition = "m.ply = ?"
        acpl_params = [cfg["analytics"]["middlegame_ply"]] + sigs
    else:
        ply_condition = "m.ply = sc.endgame_ply"
        acpl_params = sigs
    acpl_rows = sqlite_conn.execute(f"""
        SELECT sc.{sig_col}, COUNT(DISTINCT m.game_id), AVG(m.cpl)
        FROM moves m JOIN structure_ctx sc ON sc.game_id = m.game_id
        WHERE {ply_condition} AND m.is_player_move=1 AND m.cpl IS NOT NULL
          AND sc.{sig_col} IN ({placeholders})
        GROUP BY sc.{sig_col}
    """, acpl_params).fetchall()
    acpl_lookup = {sig: (n_analyzed, acpl) for sig, n_analyzed, acpl in acpl_rows}

    rows = []
    for sig, n in counts:
        o = outcome_lookup.get(sig, {})
        win, draw, loss = o.get("win", 0), o.get("draw", 0), o.get("loss", 0)
        n_analyzed, acpl = acpl_lookup.get(sig, (0, None))
        rows.append((sig, n, 100.0 * win / n, 100.0 * draw / n, 100.0 * loss / n, acpl, n_analyzed))
    return pd.DataFrame(rows, columns=["material_sig", "n_games", "win_pct", "draw_pct", "loss_pct",
                                        "acpl", "n_analyzed"])


# ---------- Piece-movement / castling (Phase 9, 2026-06-23) ----------
# Mirrors analysis/piece_movement_patterns.py, piece_phase_sharpness.py,
# square_color_backrank_performance.py, castling_performance.py -- see
# FINDINGS.md for the full results these restate the query logic of.

def get_piece_movement_patterns(duck_conn):
    """Mirrors analysis/piece_movement_patterns.py (Tier 1) -- ACPL/blunder
    rate by moves.piece, analyzed games only. Found queen moves blunder at
    ~1.8x the dataset-wide baseline, the clearest piece-level signal in
    the project."""
    df = duck_conn.execute("""
        SELECT piece, COUNT(*) AS n_moves, AVG(cpl) AS acpl,
               100.0 * SUM(CASE WHEN classification='blunder' THEN 1 ELSE 0 END) / COUNT(*) AS blunder_rate
        FROM db.moves
        WHERE is_player_move=1 AND cpl IS NOT NULL AND piece IS NOT NULL
        GROUP BY piece
    """).fetchdf()
    df["piece_name"] = df.piece.map(PIECE_NAME)
    order = {p: i for i, p in enumerate(PIECE_ORDER)}
    return df.sort_values(by="piece", key=lambda s: s.map(order)).reset_index(drop=True)


def get_piece_blunder_by_phase(sqlite_conn, config_path=None):
    """Mirrors analysis/piece_phase_sharpness.py's phase cut -- piece type
    x game phase, reusing the same structure_ctx phase boundaries as
    get_phase_accuracy above. Found knight overtakes queen specifically
    in the endgame (8.0% vs. 6.3%)."""
    cfg = get_config(config_path)
    analytics.ensure_structure_ctx(sqlite_conn, cfg)
    middlegame_ply = cfg["analytics"]["middlegame_ply"]
    rows = sqlite_conn.execute(f"""
        SELECT m.piece,
               CASE WHEN m.ply < {middlegame_ply} THEN 'opening'
                    WHEN sc.endgame_ply IS NULL OR m.ply < sc.endgame_ply THEN 'middlegame'
                    ELSE 'endgame' END AS phase,
               COUNT(*) AS n_moves, AVG(m.cpl) AS acpl,
               100.0 * SUM(CASE WHEN m.classification='blunder' THEN 1 ELSE 0 END) / COUNT(*) AS blunder_rate
        FROM moves m JOIN structure_ctx sc ON sc.game_id = m.game_id
        WHERE m.is_player_move=1 AND m.cpl IS NOT NULL AND m.piece IS NOT NULL
        GROUP BY m.piece, phase
    """).fetchall()
    df = pd.DataFrame(rows, columns=["piece", "phase", "n_moves", "acpl", "blunder_rate"])
    df["piece_name"] = df.piece.map(PIECE_NAME)
    order = {p: i for i, p in enumerate(PIECE_ORDER)}
    return df.sort_values(by="piece", key=lambda s: s.map(order)).reset_index(drop=True)


def get_piece_blunder_by_sharpness(duck_conn):
    """Mirrors analysis/piece_phase_sharpness.py's sharpness cut, reusing
    SHARPNESS_BUCKETS. Found king/knight overtake queen specifically in
    forcing positions (17.2%/16.9% vs. 15.6%)."""
    df = duck_conn.execute("""
        SELECT piece, sharpness, classification FROM db.moves
        WHERE is_player_move=1 AND cpl IS NOT NULL AND sharpness IS NOT NULL AND piece IS NOT NULL
    """).fetchdf()
    rows = []
    for piece in PIECE_ORDER:
        sub_piece = df[df.piece == piece]
        for label, lo, hi in SHARPNESS_BUCKETS:
            sub = sub_piece[(sub_piece.sharpness >= lo) & (sub_piece.sharpness < hi)]
            if len(sub):
                rows.append((piece, PIECE_NAME[piece], label, len(sub),
                            100.0 * (sub.classification == "blunder").sum() / len(sub)))
    return pd.DataFrame(rows, columns=["piece", "piece_name", "bucket", "n_moves", "blunder_rate"])


def get_bishop_square_color_performance(duck_conn):
    """Mirrors analysis/square_color_backrank_performance.py's bishop cut
    -- light vs. dark square ACPL/blunder rate. Found essentially no
    difference (a real null result for the "bad bishop" hypothesis)."""
    dark_square_sql = ("((ascii(substr(to_square,1,1)) - ascii('a') + "
                       "cast(substr(to_square,2,1) as integer) - 1) % 2 = 0)")
    df = duck_conn.execute(f"""
        SELECT {dark_square_sql} AS is_dark, COUNT(*) AS n_moves, AVG(cpl) AS acpl,
               100.0 * SUM(CASE WHEN classification='blunder' THEN 1 ELSE 0 END) / COUNT(*) AS blunder_rate
        FROM db.moves
        WHERE is_player_move=1 AND piece='B' AND cpl IS NOT NULL
          AND to_square IS NOT NULL AND color IS NOT NULL
        GROUP BY is_dark
    """).fetchdf()
    df["square_color"] = df.is_dark.map({True: "dark square", False: "light square"})
    return df


def get_rook_king_backrank_performance(duck_conn):
    """Mirrors analysis/square_color_backrank_performance.py's back-rank
    cut for both rook and king -- own back rank (rank 1 for White, rank 8
    for Black) vs. elsewhere. Found a large, real effect for both, king
    ACPL more than doubles off the back rank."""
    back_rank_sql = "(substr(to_square,2,1) = CASE WHEN color='w' THEN '1' ELSE '8' END)"
    df = duck_conn.execute(f"""
        SELECT piece, {back_rank_sql} AS is_back_rank, COUNT(*) AS n_moves, AVG(cpl) AS acpl,
               100.0 * SUM(CASE WHEN classification='blunder' THEN 1 ELSE 0 END) / COUNT(*) AS blunder_rate
        FROM db.moves
        WHERE is_player_move=1 AND piece IN ('R','K') AND cpl IS NOT NULL
          AND to_square IS NOT NULL AND color IS NOT NULL
        GROUP BY piece, is_back_rank
    """).fetchdf()
    df["piece_name"] = df.piece.map(PIECE_NAME)
    df["location"] = df.is_back_rank.map({True: "back rank", False: "elsewhere"})
    return df


def get_castling_performance(duck_conn, config_path=None):
    """Mirrors analysis/castling_performance.py -- derives a per-game-
    per-color "ever castled" flag from moves.is_castle (no such column on
    games directly), filtered to games long enough that castling was a
    real option (castling_min_plies, the 95th percentile of the real
    castling-ply distribution). Returns (win_rate_df, acpl_df).

    The castle flag and ACPL are computed in one combined query instead of
    two separate DuckDB scans (saves ~450ms on a 32k-game database)."""
    cfg = get_config(config_path)
    min_plies = cfg["analytics"]["castling_min_plies"]

    df = duck_conn.execute(f"""
        SELECT g.id AS game_id, g.outcome_for_player,
               MAX(CASE WHEN m.color = CASE WHEN g.player_color='white' THEN 'w' ELSE 'b' END
                        AND m.is_castle=1 THEN 1 ELSE 0 END)                     AS player_castled,
               AVG(CASE WHEN m.is_player_move=1 AND m.cpl IS NOT NULL THEN m.cpl END)   AS mean_cpl,
               COUNT(CASE WHEN m.is_player_move=1 AND m.cpl IS NOT NULL THEN 1 END)     AS n_cpl_moves
        FROM db.games g JOIN db.moves m ON m.game_id = g.id
        WHERE g.outcome_for_player IS NOT NULL AND g.num_plies >= {min_plies}
        GROUP BY g.id, g.outcome_for_player, g.player_color
    """).fetchdf()
    df["player_castled"] = df["player_castled"].fillna(0).astype(int)

    win_rows = []
    for val, label in ((1, "castled"), (0, "did not castle")):
        sub = df[df.player_castled == val]
        if len(sub):
            win_rows.append((label, len(sub), 100.0 * (sub.outcome_for_player == "win").sum() / len(sub)))
    win_df = pd.DataFrame(win_rows, columns=["status", "n_games", "win_pct"])

    acpl_rows = []
    for val, label in ((1, "castled"), (0, "did not castle")):
        sub = df[(df.player_castled == val) & (df.n_cpl_moves > 0)]
        if len(sub):
            total_moves = int(sub.n_cpl_moves.sum())
            weighted_acpl = (sub.mean_cpl * sub.n_cpl_moves).sum() / total_moves
            acpl_rows.append((label, len(sub), total_moves, weighted_acpl))
    acpl_summary = pd.DataFrame(acpl_rows, columns=["status", "n_games", "n_moves", "acpl"])
    return win_df, acpl_summary


# ---------- Gap-analysis additions (dashboard review, 2026-06-22) ----------

def get_sharpness_blunder_correlation(duck_conn):
    """Mirrors analysis/sharpness_correlation.py -- the 2nd-strongest
    finding in Phase 5 (blunder rate climbs ~9x from flat to forcing
    positions), never previously surfaced in the dashboard."""
    df = duck_conn.execute("""
        SELECT cpl, sharpness, classification FROM db.moves
        WHERE is_player_move=1 AND cpl IS NOT NULL AND sharpness IS NOT NULL
    """).fetchdf()
    return bucket_acpl_blunder_rate(df, "sharpness", SHARPNESS_BUCKETS)


def get_thinking_time_blunder_correlation(duck_conn):
    """Mirrors analysis/thinking_time.py -- the most surprising finding in
    Phase 5 (blunder rate is NOT monotonic with time spent; instant/quick
    moves blunder less than 3-30s "considered" moves), never previously
    surfaced in the dashboard."""
    df = duck_conn.execute("""
        SELECT time_spent_seconds, cpl, classification FROM db.moves
        WHERE is_player_move=1 AND cpl IS NOT NULL
          AND time_spent_seconds IS NOT NULL AND time_spent_seconds >= 0
    """).fetchdf()
    return bucket_acpl_blunder_rate(df, "time_spent_seconds", THINKING_TIME_BUCKETS)


# Ply ranges for the instant-move (time_spent_seconds=0) rate-by-phase
# chart. Deliberately in plies, not the move_number-based phase buckets
# used elsewhere in this module (get_decisive_moments) -- these match the
# exact buckets used to characterize the opening-theory confound during
# design (confirmed live: 41.9% zero-time rate at plies 1-10 vs 8.9% at
# 11-30), so the chart shows the same shape that motivated excluding the
# opening from the correlation query below.
INSTANT_MOVE_PLY_PHASE_BUCKETS = [
    ("opening (1-10)", 1, 11),
    ("middlegame (11-30)", 11, 31),
    ("late middlegame (31-60)", 31, 61),
    ("endgame (61+)", 61, 10**9),
]


def get_instant_move_rate_by_phase(duck_conn):
    """Player's own instant-move (time_spent_seconds=0) rate by ply-phase --
    the descriptive counterpart to get_instant_move_accuracy_by_legal_replies
    below. Deliberately NOT filtered to any ply range: the point of this
    chart is to show the opening-theory spike honestly, not hide it."""
    df = duck_conn.execute("""
        SELECT ply, time_spent_seconds FROM db.moves
        WHERE is_player_move=1 AND time_spent_seconds IS NOT NULL
    """).fetchdf()
    rows = []
    for label, lo, hi in INSTANT_MOVE_PLY_PHASE_BUCKETS:
        sub = df[(df.ply >= lo) & (df.ply < hi)]
        if len(sub):
            n_instant = int((sub.time_spent_seconds == 0).sum())
            rows.append((label, len(sub), n_instant, 100.0 * n_instant / len(sub)))
    return pd.DataFrame(rows, columns=["bucket", "n_moves", "n_instant", "instant_pct"])


def get_instant_move_accuracy_by_legal_replies(duck_conn, config_path=None):
    """Accuracy (cpl/blunder rate) of instant moves, split by legal_reply_count
    into "forced-ish" (few legal replies -- a pre-queued move is more
    plausible) vs "open" (many legal replies) -- see migrations/0032 and
    BRIEF.md's premove-detection design for why legal_reply_count exists and
    why this can't be a real premove/not-premove label, only a confidence
    split.

    Excludes plies at or below instant_move_exclude_max_ply (opening book
    familiarity, not premove-shaped behavior -- see
    get_instant_move_rate_by_phase's confound). Restricted to is_player_move=1,
    cpl IS NOT NULL (i.e. already Stockfish-analyzed) and legal_reply_count
    IS NOT NULL (i.e. an instant move ingested after migrations/0032, or
    backfilled by backfill_legal_reply_count.py).

    Returns (result_df, n_analyzed, n_total_in_scope): result_df has the
    same shape as _shared.bucket_acpl_blunder_rate's output (bucket,
    n_moves, acpl, blunder_rate). n_analyzed/n_total_in_scope let the
    caller show a coverage disclaimer -- analysis backlog coverage of this
    specific population was only ~2.6% at design time, heavily skewed
    toward recently-synced games, so this is a real but thin/skewed
    correlation, not a settled finding."""
    cfg = get_config(config_path)
    exclude_max_ply = cfg["analytics"]["instant_move_exclude_max_ply"]
    low_legal_replies = cfg["analytics"]["instant_move_low_legal_replies"]
    legal_reply_buckets = [
        (f"forced-ish (≤{low_legal_replies} legal replies)", 0, low_legal_replies + 1),
        (f"open (>{low_legal_replies} legal replies)", low_legal_replies + 1, 10**9),
    ]

    n_total_in_scope = _fetchone_scalar(duck_conn, f"""
        SELECT COUNT(*) FROM db.moves
        WHERE is_player_move=1 AND time_spent_seconds=0 AND ply > {exclude_max_ply}
    """)

    df = duck_conn.execute(f"""
        SELECT legal_reply_count, cpl, classification FROM db.moves
        WHERE is_player_move=1 AND time_spent_seconds=0 AND ply > {exclude_max_ply}
          AND cpl IS NOT NULL AND legal_reply_count IS NOT NULL
    """).fetchdf()
    result_df = bucket_acpl_blunder_rate(df, "legal_reply_count", legal_reply_buckets)
    return result_df, len(df), n_total_in_scope


def get_decisive_moments(duck_conn):
    """For each loss, the single move in a contested position with the largest
    win-probability drop.

    'Contested' = win_prob_before between 0.30 and 0.70 -- the game was still
    genuinely in balance.  One row per qualifying loss; losses where no player
    move in a contested position exists are excluded.  clock_fraction is NULL
    when the game has no clock data.
    """
    return duck_conn.execute("""
        WITH contested AS (
            SELECT
                m.game_id,
                m.move_number,
                m.win_prob_before - m.win_prob_after                        AS wp_drop,
                CASE
                    WHEN g.base_seconds IS NOT NULL AND g.base_seconds > 0
                         AND m.clock_seconds IS NOT NULL
                    THEN CAST(m.clock_seconds AS DOUBLE) / g.base_seconds
                    ELSE NULL
                END                                                          AS clock_fraction,
                CASE WHEN m.move_number <= 12 THEN 'opening'
                     WHEN m.move_number <= 30 THEN 'middlegame'
                     ELSE 'endgame' END                                      AS phase,
                ROW_NUMBER() OVER (
                    PARTITION BY m.game_id
                    ORDER BY m.win_prob_before - m.win_prob_after DESC
                )                                                            AS rn
            FROM db.moves m
            JOIN db.games g ON g.id = m.game_id
            WHERE g.outcome_for_player = 'loss'
              AND m.is_player_move    = 1
              AND m.win_prob_before   IS NOT NULL
              AND m.win_prob_after    IS NOT NULL
              AND m.win_prob_before   BETWEEN 0.30 AND 0.70
              AND m.win_prob_before   > m.win_prob_after
        )
        SELECT game_id, move_number, phase, wp_drop, clock_fraction
        FROM contested WHERE rn = 1
    """).fetchdf()
