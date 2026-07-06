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


# Mate-in-N is a per-move eval_mate value, not a duration -- these buckets
# just group the closest-to-the-end qualifying mate score per game into
# "about to be mated outright" vs. "a mate the player could plausibly have
# missed seeing coming" vs. "a deep mate that was more a formality by the
# time it was found." Half-open like every other bucket list in this
# package (TIME_PRESSURE_BUCKETS etc. in _shared.py).
MATE_DISTANCE_BUCKETS = [
    ("Mate in 1-2", 1, 3),
    ("Mate in 3-5", 3, 6),
    ("Mate in 6+",  6, 10**9),
]


def get_resignation_loss_causes(duck_conn, config_path=None):
    """Classifies every resignation loss by why it likely happened, and
    (for the hung-piece bucket) which piece type was hung.

    Reuses the exact hanging-piece definition and thresholds from
    tactical.get_hallucination_blunders (classification='blunder' AND the
    opponent's immediate next move recaptures on the same square for >=
    hallucination_min_material_delta) rather than inventing a second
    "hung a piece" criterion -- this is a fresh single-query self-join,
    not a re-derivation of different logic, because it needs a LEFT JOIN
    against other signals (forced mate against the player, clock pressure)
    and a per-game "closest to the end" pick that get_hallucination_blunders'
    one-row-per-blunder shape doesn't give us for free.

    The hung-piece and forced-mate signals depend entirely on this game
    having been through Stockfish analysis: eval_mate is only ever non-NULL
    on analyzed moves (worker.py fills it in; a freshly-ingested, unanalyzed
    game has it NULL on every move), and classification='blunder' is itself
    derived from cpl, which is only computed post-analysis (see
    annotate.py). On the real dev database, only ~2.5% of resignation
    losses have any analyzed move at all -- so without a separate bucket,
    "no signal found" would silently lump together "genuinely a gradual
    decline" with "hasn't been analyzed yet," and the latter dominates.

    The time-pressure signal is different: clock_seconds comes straight off
    the ingested PGN (%clk comments), not the engine, so it's available
    regardless of analysis status -- confirmed live: of the resignation
    losses currently sitting in the not-yet-analyzed bucket, ~3.4% (336 of
    9774 on the real dev DB) show a qualifying time-pressure signal, so
    checking it here materially shrinks "not_analyzed" down to "no
    explanation of any kind found" rather than leaving it as "we didn't
    even look." A resignation loss is classified, in priority order:
      1. "hung_piece" -- a qualifying hang happened within
         hallucination_max_moves_to_resign of the game's end (the same
         window get_hallucination_blunders uses for its resigned_quickly
         flag). Takes priority over #2/#3 because a hung piece is usually
         the proximate, actionable cause even when it also leads to a
         forced mate or occurred while low on time.
      2. "faced_mate" -- no qualifying hang, but the engine already had a
         forced mate against the player (eval_mate < 0 on the player's own
         move -- see annotate.py's POV convention: eval at ply i is from
         whoever is about to move at ply i) within that same window.
      3. "time_pressure" -- no qualifying hang or forced mate, but at the
         player's last recorded move their own clock was already critically
         low (< resignation_time_pressure_max_own_seconds) AND the opponent
         held at least resignation_time_pressure_min_opponent_lead_seconds
         more time at their own last recorded move -- a real imbalance, not
         just "both scrambling." Doesn't require analysis, so this can
         fire even on never-analyzed games.
      4. "other" -- the game has at least one analyzed move (eval_cp or
         eval_mate present somewhere), but no signal fired near the end --
         a genuine gradual material/positional decline, not an analysis gap
         or a clock issue.
      5. "not_analyzed" -- no move in this game has ever been analyzed, and
         no time-pressure signal fired either, so no explanation could be
         found by any means. Not a chess finding -- a backlog/data-gap
         signal, not a resignation cause.

    Returns (reason_df, piece_df, mate_df):
      reason_df: reason, n, pct (pct of all resignation losses -- the
        caller is responsible for excluding not_analyzed before quoting a
        percentage as if it were about chess causes)
      piece_df: piece, n, pct (pct of hung_piece resignation losses only)
      mate_df: bucket, n, pct (pct of faced_mate resignation losses only) --
        buckets the eval_mate of the closest-to-the-end qualifying move per
        game (see MATE_DISTANCE_BUCKETS); empty buckets are omitted, same
        convention as _shared.bucket_acpl_blunder_rate.
    All three empty (not None) when there are no resignation losses yet.
    """
    cfg = get_config(config_path)
    min_material_delta = cfg["analytics"]["hallucination_min_material_delta"]
    max_plies_to_resign = cfg["analytics"]["hallucination_max_moves_to_resign"] * 2
    max_own_seconds = cfg["analytics"]["resignation_time_pressure_max_own_seconds"]
    min_opponent_lead_seconds = cfg["analytics"]["resignation_time_pressure_min_opponent_lead_seconds"]

    df = duck_conn.execute(f"""
        WITH resignations AS (
            SELECT id AS game_id, num_plies
            FROM db.games
            WHERE outcome_for_player = 'loss' AND game_end_type = 'resignation'
        ),
        analyzed_flag AS (
            SELECT DISTINCT r.game_id
            FROM db.moves m JOIN resignations r ON r.game_id = m.game_id
            WHERE m.eval_cp IS NOT NULL OR m.eval_mate IS NOT NULL
        ),
        last_mate AS (
            SELECT r.game_id, m.eval_mate,
                   ROW_NUMBER() OVER (PARTITION BY r.game_id ORDER BY m.ply DESC) AS rn
            FROM db.moves m JOIN resignations r ON r.game_id = m.game_id
            WHERE m.is_player_move = 1 AND m.eval_mate IS NOT NULL AND m.eval_mate < 0
              AND r.num_plies - m.ply <= {max_plies_to_resign}
            QUALIFY rn = 1
        ),
        last_hang AS (
            SELECT r.game_id, m.piece AS hung_piece,
                   ROW_NUMBER() OVER (PARTITION BY r.game_id ORDER BY m.ply DESC) AS rn
            FROM db.moves m
            JOIN db.moves m2 ON m2.game_id = m.game_id AND m2.ply = m.ply + 1
            JOIN resignations r ON r.game_id = m.game_id
            WHERE m.is_player_move = 1 AND m.classification = 'blunder' AND m.cpl IS NOT NULL
              AND m2.is_capture = 1 AND m2.to_square = m.to_square
              AND m2.material_delta >= {min_material_delta}
              AND r.num_plies - m.ply <= {max_plies_to_resign}
            QUALIFY rn = 1
        ),
        last_player_clock AS (
            SELECT r.game_id, m.clock_seconds AS player_clock,
                   ROW_NUMBER() OVER (PARTITION BY r.game_id ORDER BY m.ply DESC) AS rn
            FROM db.moves m JOIN resignations r ON r.game_id = m.game_id
            WHERE m.is_player_move = 1 AND m.clock_seconds IS NOT NULL
            QUALIFY rn = 1
        ),
        last_opponent_clock AS (
            SELECT r.game_id, m.clock_seconds AS opponent_clock,
                   ROW_NUMBER() OVER (PARTITION BY r.game_id ORDER BY m.ply DESC) AS rn
            FROM db.moves m JOIN resignations r ON r.game_id = m.game_id
            WHERE m.is_player_move = 0 AND m.clock_seconds IS NOT NULL
            QUALIFY rn = 1
        )
        SELECT r.game_id,
               CASE WHEN h.hung_piece IS NOT NULL THEN 'hung_piece'
                    WHEN lm.game_id IS NOT NULL THEN 'faced_mate'
                    WHEN pc.player_clock IS NOT NULL AND oc.opponent_clock IS NOT NULL
                         AND pc.player_clock < {max_own_seconds}
                         AND oc.opponent_clock - pc.player_clock >= {min_opponent_lead_seconds}
                         THEN 'time_pressure'
                    WHEN af.game_id IS NOT NULL THEN 'other'
                    ELSE 'not_analyzed' END AS reason,
               h.hung_piece, lm.eval_mate AS mate_eval
        FROM resignations r
        LEFT JOIN analyzed_flag af ON af.game_id = r.game_id
        LEFT JOIN last_mate lm ON lm.game_id = r.game_id
        LEFT JOIN last_hang h ON h.game_id = r.game_id
        LEFT JOIN last_player_clock pc ON pc.game_id = r.game_id
        LEFT JOIN last_opponent_clock oc ON oc.game_id = r.game_id
    """).fetchdf()

    if df.empty:
        empty_reason = pd.DataFrame(columns=["reason", "n", "pct"])
        empty_piece = pd.DataFrame(columns=["hung_piece", "n", "pct"])
        empty_mate = pd.DataFrame(columns=["bucket", "n", "pct"])
        return empty_reason, empty_piece, empty_mate

    total = len(df)
    reason_df = df.groupby("reason").size().reindex(
        ["hung_piece", "faced_mate", "time_pressure", "other", "not_analyzed"],
        fill_value=0).reset_index(name="n")
    reason_df["pct"] = 100.0 * reason_df.n / total

    hung = df[df.reason == "hung_piece"]
    n_hung = len(hung)
    piece_df = hung.groupby("hung_piece").size().reset_index(name="n")
    piece_df["pct"] = 100.0 * piece_df.n / n_hung if n_hung else 0.0
    piece_df = piece_df.sort_values("n", ascending=False).reset_index(drop=True)

    faced_mate = df[df.reason == "faced_mate"]
    n_mate = len(faced_mate)
    moves_to_mate = faced_mate.mate_eval.abs()
    mate_rows = []
    for label, lo, hi in MATE_DISTANCE_BUCKETS:
        n = int(((moves_to_mate >= lo) & (moves_to_mate < hi)).sum())
        if n:
            mate_rows.append((label, n, 100.0 * n / n_mate if n_mate else 0.0))
    mate_df = pd.DataFrame(mate_rows, columns=["bucket", "n", "pct"])

    return reason_df, piece_df, mate_df


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
