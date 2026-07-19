"""Board-position character and squares queries (drill-down survey,
2026-07-07) -- one of eight topic modules split out of the former
dashboard/data/patterns.py.

Open/closed/semi-open + symmetric/asymmetric come from ONE fen_before
fetch+classify pass at the existing middlegame_ply checkpoint (reuses
analytics.ensure_structure_ctx's own snapshot ply, no new threshold) --
benchmarked live at ~1.1s for the full 32k-game DB, well under the
materialization bar every other calendar-cheap feature in this package
uses (see get_castling_performance/get_day_hour_heatmap: no cache table,
single @st.cache_data suffices), so deliberately no new *_cache table,
no new migration, no new ingest-time column. Castling-configuration and
action-side concentration need no FEN parsing at all -- both come
straight off moves.is_castle/is_capture/to_square/color in one combined
scan. Win rate is board-derived (outcome_for_player, zero-null) and
honest from day one; ACPL/blunder-rate need cpl, which is analysis-gated
(944 of 32,295 games, ~2.9%, have any engine data at all, live-verified)
-- every accuracy panel built on these functions must show the same
n_analyzed/coverage disclosure already established for Instant Moves/
Evolution/Game Explorer, not just the raw number.
"""
import pandas as pd

import chess_utils
from connections import get_config

from .._shared import _fetchone_scalar

_POSITION_CHARACTER_BUCKET_ORDER = ["open", "semi-open", "closed"]


def get_position_character_performance(duck_conn, config_path=None):
    """Classifies each game's pawn structure at the middlegame_ply
    checkpoint (chess_utils.classify_position_character) and splits
    win-rate/ACPL/blunder-rate across two axes computed from that SAME
    pass: the open/semi-open/closed bucket, and symmetric vs. asymmetric
    pawn files. Games shorter than middlegame_ply contribute no row (same
    "no row" convention as analytics.ensure_structure_ctx for games that
    never reach the checkpoint).

    Returns a dict: bucket_win/bucket_acpl (columns: bucket, n_games,
    win_pct / bucket, n_games, n_moves, acpl, blunder_rate),
    symmetric_win/symmetric_acpl (same shape, keyed by "symmetric"/
    "asymmetric"), central_tension_pct (share of semi-open games with
    unresolved central pawn tension, or None if no semi-open games),
    n_classified (games reaching the checkpoint), n_total_games."""
    cfg = get_config(config_path)
    middlegame_ply = cfg["analytics"]["middlegame_ply"]

    ctx = duck_conn.execute(f"""
        SELECT m.game_id, m.fen_before, g.outcome_for_player
        FROM db.moves m JOIN db.games g ON g.id = m.game_id
        WHERE m.ply = {middlegame_ply} AND m.fen_before IS NOT NULL
    """).fetchdf()
    n_total_games = _fetchone_scalar(duck_conn, "SELECT COUNT(*) FROM db.games")
    n_classified = len(ctx)
    if ctx.empty:
        empty_win = pd.DataFrame(columns=["bucket", "n_games", "win_pct"])
        empty_acpl = pd.DataFrame(columns=["bucket", "n_games", "n_moves", "acpl", "blunder_rate"])
        return {"bucket_win": empty_win, "bucket_acpl": empty_acpl,
                "symmetric_win": empty_win.rename(columns={"bucket": "symmetric"}),
                "symmetric_acpl": empty_acpl.rename(columns={"bucket": "symmetric"}),
                "central_tension_pct": None, "n_classified": 0, "n_total_games": n_total_games}

    # pd.DataFrame(list-of-dicts) instead of .apply(pd.Series) -- the
    # latter measured ~8.4s for 31k rows vs. ~0.03s for this, on the real
    # dev DB (a well-known pandas anti-pattern: .apply(pd.Series) builds
    # one intermediate Series per row instead of one bulk construction).
    classified = pd.DataFrame(
        ctx["fen_before"].apply(chess_utils.classify_position_character).tolist())
    ctx = pd.concat([ctx.drop(columns=["fen_before"]), classified], axis=1)
    ctx["symmetry_label"] = ctx["symmetric"].map({True: "symmetric", False: "asymmetric"})

    moves = duck_conn.execute("""
        SELECT game_id, cpl, classification FROM db.moves
        WHERE is_player_move=1 AND cpl IS NOT NULL
    """).fetchdf()

    def _win_table(group_col, order=None):
        sub = ctx.dropna(subset=["outcome_for_player"])
        rows = sub.groupby(group_col).agg(
            n_games=("game_id", "count"),
            win_pct=("outcome_for_player", lambda s: 100.0 * (s == "win").sum() / len(s)),
        ).reset_index()
        if order:
            rows[group_col] = pd.Categorical(rows[group_col], categories=order, ordered=True)
            rows = rows.sort_values(group_col).reset_index(drop=True)
        return rows

    def _acpl_table(group_col, order=None):
        merged = moves.merge(ctx[["game_id", group_col]], on="game_id", how="inner")
        if merged.empty:
            return pd.DataFrame(columns=[group_col, "n_games", "n_moves", "acpl", "blunder_rate"])
        rows = merged.groupby(group_col).agg(
            n_games=("game_id", "nunique"),
            n_moves=("cpl", "size"),
            acpl=("cpl", "mean"),
            blunder_rate=("classification", lambda s: 100.0 * (s == "blunder").sum() / len(s)),
        ).reset_index()
        if order:
            rows[group_col] = pd.Categorical(rows[group_col], categories=order, ordered=True)
            rows = rows.sort_values(group_col).reset_index(drop=True)
        return rows

    semi_open = ctx[ctx["bucket"] == "semi-open"]
    central_tension_pct = (100.0 * semi_open["central_tension"].sum() / len(semi_open)
                            if len(semi_open) else None)

    return {
        "bucket_win": _win_table("bucket", _POSITION_CHARACTER_BUCKET_ORDER),
        "bucket_acpl": _acpl_table("bucket", _POSITION_CHARACTER_BUCKET_ORDER),
        "symmetric_win": _win_table("symmetry_label", ["symmetric", "asymmetric"]),
        "symmetric_acpl": _acpl_table("symmetry_label", ["symmetric", "asymmetric"]),
        "central_tension_pct": central_tension_pct,
        "n_classified": n_classified,
        "n_total_games": n_total_games,
    }


def _classify_castling_config(white_sq, black_sq):
    if pd.isna(white_sq) or pd.isna(black_sq):
        return "never-castled" if pd.isna(white_sq) and pd.isna(black_sq) else "one-side-only"
    white_side = "K" if white_sq in ("g1", "g8") else "Q"
    black_side = "K" if black_sq in ("g1", "g8") else "Q"
    return "same-side" if white_side == black_side else "opposite-side"


def _classify_action_side(q_caps, k_caps, ratio):
    if q_caps >= k_caps * ratio and q_caps > 0:
        return "queenside-heavy"
    if k_caps >= q_caps * ratio and k_caps > 0:
        return "kingside-heavy"
    return "balanced"


_CASTLING_CONFIG_ORDER = ["same-side", "opposite-side", "one-side-only", "never-castled"]
_ACTION_SIDE_ORDER = ["queenside-heavy", "balanced", "kingside-heavy"]


def get_game_side_performance(duck_conn, config_path=None):
    """Two "queenside vs. kingside" cuts from ONE combined per-game scan
    of moves.is_castle/is_capture/to_square -- no FEN parsing needed.
    Castling configuration (same-side/opposite-side/one-side-only/never)
    is the king-safety proxy (opposite-side castling races are a
    well-established sharper/more-decisive shape); action-side
    concentration (queenside-heavy/balanced/kingside-heavy, from capture
    counts on a-d vs. e-h files) is the "where did the fight happen" proxy.
    Returns a dict shaped like get_position_character_performance's:
    castling_win/castling_acpl, action_win/action_acpl."""
    cfg = get_config(config_path)
    ratio = cfg["analytics"]["action_side_capture_ratio"]

    ctx = duck_conn.execute("""
        SELECT g.id AS game_id, g.outcome_for_player,
               MAX(CASE WHEN m.is_castle=1 AND m.color='w' THEN m.to_square END) AS white_castle_sq,
               MAX(CASE WHEN m.is_castle=1 AND m.color='b' THEN m.to_square END) AS black_castle_sq,
               SUM(CASE WHEN m.is_capture=1 AND substr(m.to_square,1,1) IN ('a','b','c','d')
                        THEN 1 ELSE 0 END) AS q_caps,
               SUM(CASE WHEN m.is_capture=1 AND substr(m.to_square,1,1) IN ('e','f','g','h')
                        THEN 1 ELSE 0 END) AS k_caps
        FROM db.games g JOIN db.moves m ON m.game_id = g.id
        GROUP BY g.id, g.outcome_for_player
    """).fetchdf()
    if ctx.empty:
        empty_win = pd.DataFrame(columns=["config", "n_games", "win_pct"])
        empty_acpl = pd.DataFrame(columns=["config", "n_games", "n_moves", "acpl", "blunder_rate"])
        return {"castling_win": empty_win, "castling_acpl": empty_acpl,
                "action_win": empty_win.rename(columns={"config": "action_side"}),
                "action_acpl": empty_acpl.rename(columns={"config": "action_side"})}

    ctx["castling_config"] = ctx.apply(
        lambda r: _classify_castling_config(r["white_castle_sq"], r["black_castle_sq"]), axis=1)
    ctx["action_side"] = ctx.apply(
        lambda r: _classify_action_side(r["q_caps"], r["k_caps"], ratio), axis=1)

    moves = duck_conn.execute("""
        SELECT game_id, cpl, classification FROM db.moves
        WHERE is_player_move=1 AND cpl IS NOT NULL
    """).fetchdf()

    def _win_table(group_col, order):
        sub = ctx.dropna(subset=["outcome_for_player"])
        rows = sub.groupby(group_col).agg(
            n_games=("game_id", "count"),
            win_pct=("outcome_for_player", lambda s: 100.0 * (s == "win").sum() / len(s)),
        ).reset_index()
        rows[group_col] = pd.Categorical(rows[group_col], categories=order, ordered=True)
        return rows.sort_values(group_col).reset_index(drop=True)

    def _acpl_table(group_col, order):
        merged = moves.merge(ctx[["game_id", group_col]], on="game_id", how="inner")
        if merged.empty:
            return pd.DataFrame(columns=[group_col, "n_games", "n_moves", "acpl", "blunder_rate"])
        rows = merged.groupby(group_col).agg(
            n_games=("game_id", "nunique"),
            n_moves=("cpl", "size"),
            acpl=("cpl", "mean"),
            blunder_rate=("classification", lambda s: 100.0 * (s == "blunder").sum() / len(s)),
        ).reset_index()
        rows[group_col] = pd.Categorical(rows[group_col], categories=order, ordered=True)
        return rows.sort_values(group_col).reset_index(drop=True)

    return {
        "castling_win": _win_table("castling_config", _CASTLING_CONFIG_ORDER),
        "castling_acpl": _acpl_table("castling_config", _CASTLING_CONFIG_ORDER),
        "action_win": _win_table("action_side", _ACTION_SIDE_ORDER),
        "action_acpl": _acpl_table("action_side", _ACTION_SIDE_ORDER),
    }


def get_square_blunder_heatmap(duck_conn, config_path=None):
    """Per-to_square blunder rate, generalizing the existing bishop-color/
    back-rank cuts (get_bishop_square_color_performance,
    get_rook_king_backrank_performance) to a real 8x8 grid -- same
    to_square convention get_hallucination_blunders already established.
    Inherently analysis-gated (unlike the position-character bucket
    above, there's no board-only proxy for "was this a blunder"): callers
    must show n_analyzed/n_total_in_scope, same as
    get_instant_move_accuracy_by_legal_replies.

    Returns (blunder_pivot, n_moves_pivot, n_analyzed, n_total_in_scope).
    blunder_pivot/n_moves_pivot are None if no square clears
    square_heatmap_min_moves. n_missed_tactics is deliberately NOT
    returned here -- motif coverage is currently 0 database-wide (see
    tactical.motif_backfill_needed), so callers should show that existing
    banner rather than a second all-zero heatmap."""
    cfg = get_config(config_path)
    min_moves = cfg["analytics"]["square_heatmap_min_moves"]

    n_total_in_scope = _fetchone_scalar(duck_conn, """
        SELECT COUNT(*) FROM db.moves WHERE is_player_move=1 AND to_square IS NOT NULL
    """)
    n_analyzed = _fetchone_scalar(duck_conn, """
        SELECT COUNT(*) FROM db.moves
        WHERE is_player_move=1 AND to_square IS NOT NULL AND cpl IS NOT NULL
    """)

    df = duck_conn.execute("""
        SELECT to_square, COUNT(*) AS n_moves,
               100.0 * SUM(CASE WHEN classification='blunder' THEN 1 ELSE 0 END) / COUNT(*) AS blunder_rate
        FROM db.moves
        WHERE is_player_move=1 AND to_square IS NOT NULL AND cpl IS NOT NULL
        GROUP BY to_square HAVING COUNT(*) >= ?
    """, [min_moves]).fetchdf()
    if df.empty:
        return None, None, n_analyzed, n_total_in_scope

    df["file"] = df["to_square"].str[0]
    df["rank"] = df["to_square"].str[1].astype(int)
    blunder_pivot = df.pivot(index="rank", columns="file", values="blunder_rate").sort_index(ascending=False)
    n_moves_pivot = df.pivot(index="rank", columns="file", values="n_moves").sort_index(ascending=False)
    return blunder_pivot, n_moves_pivot, n_analyzed, n_total_in_scope
