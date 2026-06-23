"""Patterns page queries -- time pressure, time control, sharpness,
thinking time, game phase, session position, day/hour heatmap,
material-structure win rate, piece-movement/castling tendencies.
"""
import pandas as pd

import analytics
from _common import get_config

from ._shared import TIME_PRESSURE_BUCKETS, THINKING_TIME_BUCKETS

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
    rows = []
    for label, lo, hi in TIME_PRESSURE_BUCKETS:
        sub = df[(df.time_fraction >= lo) & (df.time_fraction < hi)]
        if len(sub):
            rows.append((label, len(sub), sub.cpl.mean(),
                         100.0 * (sub.classification == "blunder").sum() / len(sub)))
    return pd.DataFrame(rows, columns=["bucket", "n_moves", "acpl", "blunder_rate"])


def get_acpl_by_time_control(sqlite_conn):
    categories = sqlite_conn.execute(
        "SELECT DISTINCT time_control_category FROM games WHERE time_control_category IS NOT NULL"
    ).fetchall()
    rows = []
    for (cat,) in categories:
        n_moves, n_games, acpl, blunder_rate = analytics.acpl_and_blunder_rate(
            sqlite_conn, "g.time_control_category=?", (cat,))
        if n_games:
            rows.append((cat, n_games, n_moves, acpl, blunder_rate))
    return pd.DataFrame(rows, columns=["time_control", "n_games", "n_moves", "acpl", "blunder_rate"])


def get_phase_accuracy(sqlite_conn, config_path=None):
    cfg = get_config(config_path)
    analytics.ensure_structure_ctx(sqlite_conn, cfg)
    middlegame_ply = cfg["analytics"]["middlegame_ply"]
    structure_join = "JOIN structure_ctx sc ON sc.game_id = g.id"
    phases = [
        ("opening", f"m.ply < {middlegame_ply}"),
        ("middlegame", f"m.ply >= {middlegame_ply} AND (sc.endgame_ply IS NULL OR m.ply < sc.endgame_ply)"),
        ("endgame", "sc.endgame_ply IS NOT NULL AND m.ply >= sc.endgame_ply"),
    ]
    rows = []
    for label, where_extra in phases:
        n_moves, n_games, acpl, blunder_rate = analytics.acpl_and_blunder_rate(
            sqlite_conn, where_extra, (), extra_join=structure_join)
        if n_games:
            rows.append((label, n_games, n_moves, acpl, blunder_rate))
    return pd.DataFrame(rows, columns=["phase", "n_games", "n_moves", "acpl", "blunder_rate"])


def get_prior_outcome_performance(sqlite_conn, config_path=None):
    cfg = get_config(config_path)
    analytics.ensure_session_ctx(sqlite_conn, cfg["analytics"]["session_gap_minutes"])
    rows = []
    n_moves, n_games, acpl, blunder_rate = analytics.acpl_and_blunder_rate(
        sqlite_conn, "sc.prior_outcome IS NULL", (), extra_join=analytics.SESSION_JOIN)
    if n_games:
        rows.append(("first_game_of_session", n_games, n_moves, acpl, blunder_rate))
    for outcome in ("win", "loss", "draw"):
        n_moves, n_games, acpl, blunder_rate = analytics.acpl_and_blunder_rate(
            sqlite_conn, "sc.prior_outcome=?", (outcome,), extra_join=analytics.SESSION_JOIN)
        if n_games:
            rows.append((f"after a {outcome}", n_games, n_moves, acpl, blunder_rate))
    return pd.DataFrame(rows, columns=["bucket", "n_games", "n_moves", "acpl", "blunder_rate"])


def get_session_position_performance(sqlite_conn, config_path=None):
    cfg = get_config(config_path)
    analytics.ensure_session_ctx(sqlite_conn, cfg["analytics"]["session_gap_minutes"])
    cap = cfg["analytics"]["session_position_cap"]
    rows = []
    for n in range(1, cap):
        n_moves, n_games, acpl, blunder_rate = analytics.acpl_and_blunder_rate(
            sqlite_conn, "sc.session_game_number=?", (n,), extra_join=analytics.SESSION_JOIN)
        if n_games:
            rows.append((f"game #{n}", n_games, n_moves, acpl, blunder_rate))
    n_moves, n_games, acpl, blunder_rate = analytics.acpl_and_blunder_rate(
        sqlite_conn, "sc.session_game_number>=?", (cap,), extra_join=analytics.SESSION_JOIN)
    if n_games:
        rows.append((f"game #{cap}+", n_games, n_moves, acpl, blunder_rate))
    return pd.DataFrame(rows, columns=["position", "n_games", "n_moves", "acpl", "blunder_rate"])


def get_day_hour_heatmap(duck_conn):
    """New cross-tab, not built in Phase 5 -- day_of_week x hour_utc win
    rate, full dataset (board-derived)."""
    df = duck_conn.execute("""
        SELECT day_of_week, hour_utc,
               COUNT(*) AS n,
               100.0 * SUM(CASE WHEN outcome_for_player='win' THEN 1 ELSE 0 END) / COUNT(*) AS win_pct
        FROM db.games
        WHERE day_of_week IS NOT NULL AND hour_utc IS NOT NULL AND outcome_for_player IS NOT NULL
        GROUP BY day_of_week, hour_utc
    """).fetchdf()
    return df.pivot(index="day_of_week", columns="hour_utc", values="win_pct")


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
    castling-ply distribution). Returns (win_rate_df, acpl_df)."""
    cfg = get_config(config_path)
    min_plies = cfg["analytics"]["castling_min_plies"]

    castle_flags = duck_conn.execute("""
        SELECT m.game_id,
               MAX(CASE WHEN m.color = pc.color_code AND m.is_castle=1 THEN 1 ELSE 0 END) AS player_castled,
               MAX(CASE WHEN m.color != pc.color_code AND m.is_castle=1 THEN 1 ELSE 0 END) AS opponent_castled
        FROM db.moves m
        JOIN (SELECT id, CASE WHEN player_color='white' THEN 'w' ELSE 'b' END AS color_code
              FROM db.games) pc ON pc.id = m.game_id
        GROUP BY m.game_id
    """).fetchdf()
    games = duck_conn.execute(f"""
        SELECT id AS game_id, outcome_for_player FROM db.games
        WHERE outcome_for_player IS NOT NULL AND num_plies >= {min_plies}
    """).fetchdf()
    games = games.merge(castle_flags, on="game_id", how="left")
    games["player_castled"] = games["player_castled"].fillna(0).astype(int)

    win_rows = []
    for val, label in ((1, "castled"), (0, "did not castle")):
        sub = games[games.player_castled == val]
        if len(sub):
            win_rows.append((label, len(sub), 100.0 * (sub.outcome_for_player == "win").sum() / len(sub)))
    win_df = pd.DataFrame(win_rows, columns=["status", "n_games", "win_pct"])

    acpl_df = duck_conn.execute(f"""
        SELECT m.game_id, m.cpl
        FROM db.moves m JOIN db.games g ON g.id = m.game_id
        WHERE m.is_player_move=1 AND m.cpl IS NOT NULL AND g.num_plies >= {min_plies}
    """).fetchdf()
    acpl_df = acpl_df.merge(games[["game_id", "player_castled"]], on="game_id", how="inner")
    acpl_rows = []
    for val, label in ((1, "castled"), (0, "did not castle")):
        sub = acpl_df[acpl_df.player_castled == val]
        if len(sub):
            acpl_rows.append((label, sub.game_id.nunique(), len(sub), sub.cpl.mean()))
    acpl_summary = pd.DataFrame(acpl_rows, columns=["status", "n_games", "n_moves", "acpl"])
    return win_df, acpl_summary


# ---------- Gap-analysis additions (dashboard review, 2026-06-22) ----------

def get_sharpness_blunder_correlation(duck_conn):
    """Mirrors analysis/sharpness_correlation.py -- the 2nd-strongest
    finding in Phase 5 (blunder rate climbs ~9x from flat to forcing
    positions), never previously surfaced in the dashboard."""
    df = duck_conn.execute("""
        SELECT sharpness, classification FROM db.moves
        WHERE is_player_move=1 AND cpl IS NOT NULL AND sharpness IS NOT NULL
    """).fetchdf()
    rows = []
    for label, lo, hi in SHARPNESS_BUCKETS:
        sub = df[(df.sharpness >= lo) & (df.sharpness < hi)]
        if len(sub):
            rows.append((label, len(sub), 100.0 * (sub.classification == "blunder").sum() / len(sub)))
    return pd.DataFrame(rows, columns=["bucket", "n_moves", "blunder_rate"])


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
    rows = []
    for label, lo, hi in THINKING_TIME_BUCKETS:
        sub = df[(df.time_spent_seconds >= lo) & (df.time_spent_seconds < hi)]
        if len(sub):
            rows.append((label, len(sub), sub.cpl.mean(),
                         100.0 * (sub.classification == "blunder").sum() / len(sub)))
    return pd.DataFrame(rows, columns=["bucket", "n_moves", "acpl", "blunder_rate"])
