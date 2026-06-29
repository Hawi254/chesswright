"""Game Endings page queries."""
import collections

import pandas as pd

import analytics
from _common import get_config


def _classify_endgame_type(endgame_sig: str) -> str | None:
    """Map a player-relative material_sig to a broad endgame category.

    material_sig format (from chess_utils.material_signature): piece letters
    Q/R/B/N/P each followed by their count, white side first, then 'v', then
    black side. e.g. "R1P5vP4" -> Rook, "B1N1P4vN2P3" -> Minor piece.
    Kings are NOT in the signature (they're always present, not listed).
    """
    if not endgame_sig:
        return None
    if "Q" in endgame_sig:
        return "Queen"
    if "R" in endgame_sig:
        return "Rook"
    if "B" in endgame_sig or "N" in endgame_sig:
        return "Minor piece"
    return "King & pawn"


def get_endgame_type_performance(sqlite_conn, config_path=None):
    """Win/draw/loss rate and endgame ACPL broken down by endgame material type.

    Uses structure_ctx's endgame_sig (player-relative material at the first ply
    where non-pawn piece count drops to endgame_max_pieces) to classify each
    game's endgame type, then aggregates outcomes and move quality.
    """
    cfg = get_config(config_path)
    analytics.ensure_structure_ctx(sqlite_conn, cfg)

    outcome_rows = sqlite_conn.execute("""
        SELECT sc.endgame_sig, g.outcome_for_player, COUNT(*) AS n
        FROM structure_ctx sc
        JOIN games g ON g.id = sc.game_id
        WHERE sc.endgame_sig IS NOT NULL
        GROUP BY sc.endgame_sig, g.outcome_for_player
    """).fetchall()

    # SUM(cpl) + COUNT so we can weight-correctly aggregate across multiple
    # endgame_sig values that map to the same broad type -- AVG(AVG) is wrong
    # when sigs have different move counts.
    acpl_rows = sqlite_conn.execute("""
        SELECT sc.endgame_sig,
               SUM(m.cpl)                                                       AS sum_cpl,
               COUNT(*)                                                         AS n_moves,
               SUM(CASE WHEN m.classification='blunder' THEN 1 ELSE 0 END)     AS n_blunders
        FROM structure_ctx sc
        JOIN moves m ON m.game_id = sc.game_id
        WHERE sc.endgame_sig IS NOT NULL
          AND sc.endgame_ply IS NOT NULL
          AND m.ply >= sc.endgame_ply
          AND m.is_player_move = 1
          AND m.cpl IS NOT NULL
        GROUP BY sc.endgame_sig
    """).fetchall()

    tally = collections.defaultdict(lambda: {"win": 0, "draw": 0, "loss": 0, "n": 0})
    for endgame_sig, outcome, n in outcome_rows:
        etype = _classify_endgame_type(endgame_sig)
        if etype:
            tally[etype][outcome] = tally[etype].get(outcome, 0) + n
            tally[etype]["n"] += n

    acpl_acc = collections.defaultdict(lambda: [0, 0.0, 0])
    for endgame_sig, sum_cpl, n_moves, n_blunders in acpl_rows:
        etype = _classify_endgame_type(endgame_sig)
        if etype and n_moves:
            acc = acpl_acc[etype]
            acc[0] += n_moves
            acc[1] += sum_cpl or 0.0
            acc[2] += n_blunders or 0

    rows = []
    for etype in ("Queen", "Rook", "Minor piece", "King & pawn"):
        if etype not in tally:
            continue
        counts = tally[etype]
        total = counts["n"]
        n_moves, sum_cpl, n_blunders = acpl_acc.get(etype, [0, 0.0, 0])
        rows.append({
            "endgame_type": etype,
            "n_games": total,
            "win_pct": 100.0 * counts.get("win", 0) / total if total else 0.0,
            "draw_pct": 100.0 * counts.get("draw", 0) / total if total else 0.0,
            "loss_pct": 100.0 * counts.get("loss", 0) / total if total else 0.0,
            "acpl": sum_cpl / n_moves if n_moves else None,
            "blunder_rate": 100.0 * n_blunders / n_moves if n_moves else None,
        })
    return pd.DataFrame(rows)


def get_game_end_type_breakdown(duck_conn):
    overall = duck_conn.execute("""
        SELECT game_end_type, COUNT(*) AS n FROM db.games GROUP BY game_end_type ORDER BY n DESC
    """).fetchdf()
    by_tc = duck_conn.execute("""
        SELECT time_control_category, game_end_type, COUNT(*) AS n
        FROM db.games WHERE time_control_category IS NOT NULL
        GROUP BY time_control_category, game_end_type
    """).fetchdf()
    pivot = by_tc.pivot_table(index="time_control_category", columns="game_end_type", values="n", fill_value=0)
    pivot_pct = pivot.div(pivot.sum(axis=1), axis=0) * 100.0
    return overall, pivot_pct
