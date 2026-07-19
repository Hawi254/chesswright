"""Piece-movement and castling queries (Phase 9, 2026-06-23) -- one of
eight topic modules split out of the former dashboard/data/patterns.py.
Mirrors analysis/piece_movement_patterns.py, piece_phase_sharpness.py,
square_color_backrank_performance.py, castling_performance.py -- see
FINDINGS.md for the full results these restate the query logic of.
"""
import pandas as pd

import analytics
from _common import get_config

from ._shared import SHARPNESS_BUCKETS, PIECE_ORDER, PIECE_NAME


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
