"""Tactical Highlights page queries -- puzzle sequences, brilliant
candidates, best-move streaks, blown forced mates, knight-on-the-rim,
hallucinated hanging-piece blunders.
"""
import pandas as pd

import analytics
from _common import get_config

from ._shared import TIME_PRESSURE_BUCKETS, THINKING_TIME_BUCKETS

RIM_SQL = "(substr(to_square,1,1) IN ('a','h') OR substr(to_square,2,1) IN ('1','8'))"


def get_puzzle_sequences(duck_conn, top_n=15):
    """Mirrors analysis/puzzle_summary.py's trigger half -- 191 sequences
    computed in Phase 3b, never surfaced anywhere including the
    dashboard until now.

    top_n=None returns every qualifying row (the trigger flag bounds this
    to a few hundred rows) -- used by the view layer to cache ONE full
    fetch per session and slice per slider value in pandas, instead of
    re-running this full-table duck scan (~0.65s on the real 2.3M-row
    moves table) on every distinct top_n slider position."""
    limit = "" if top_n is None else "LIMIT ?"
    params = [] if top_n is None else [top_n]
    return duck_conn.execute(f"""
        SELECT game_id, ply, san, classification, is_player_move, puzzle_sequence_length
        FROM db.moves WHERE is_puzzle_trigger=1
        ORDER BY puzzle_sequence_length DESC {limit}
    """, params).fetchdf()


def get_brilliant_candidates(duck_conn, top_n=15):
    """Mirrors analysis/puzzle_summary.py's brilliant half -- 146
    candidates computed in Phase 3b, never surfaced anywhere including
    the dashboard until now.

    top_n=None returns every qualifying row -- same fetch-once/slice-in-
    pandas contract as get_puzzle_sequences above."""
    limit = "" if top_n is None else "LIMIT ?"
    params = [] if top_n is None else [top_n]
    return duck_conn.execute(f"""
        SELECT game_id, ply, san, material_delta FROM db.moves
        WHERE is_brilliant_candidate=1 {limit}
    """, params).fetchdf()


def get_best_move_streaks(duck_conn, top_n=15, min_unforced=1):
    """New feature (2026-06): best-move streaks -- the player matching the
    engine's literal top move for 3+ consecutive own turns, computed by
    annotate.py. Every qualifying row already has
    best_move_streak_unforced_count >= 1 by construction (a streak's
    FIRST move must itself be "unforced" -- a real choice, not the only
    sensible move -- to qualify at all); min_unforced raises that bar
    further, toward "every move in the streak was a real choice," not
    just the minimum required to qualify.

    top_n=None returns every qualifying row -- the view layer caches one
    full fetch at min_unforced=1 (the qualifying minimum, so a superset
    of every stricter setting) and applies both sliders in pandas."""
    limit = "" if top_n is None else "LIMIT ?"
    params = [min_unforced] if top_n is None else [min_unforced, top_n]
    return duck_conn.execute(f"""
        SELECT game_id, ply, san, is_player_move, best_move_streak_length,
               best_move_streak_unforced_count
        FROM db.moves
        WHERE is_best_move_streak_trigger=1 AND best_move_streak_unforced_count >= ?
        ORDER BY best_move_streak_length DESC {limit}
    """, params).fetchdf()


def get_blown_mates(duck_conn):
    """New query (not in any analysis/*.py script -- first computed
    during the Phase 5 gap-analysis report). A forced mate was available
    (eval_mate>0 before the player's move) but the player deviated from
    the engine's mating line. Most of these still won eventually (just a
    less efficient mate); the truly dramatic subset is the 3 that ended
    in an outright loss despite a forced mate having been on the board."""
    df = duck_conn.execute("""
        SELECT m.game_id, m.ply, m.san, m.best_move_san, m.eval_mate, g.outcome_for_player
        FROM db.moves m JOIN db.games g ON g.id = m.game_id
        WHERE m.is_player_move=1 AND m.eval_mate IS NOT NULL AND m.eval_mate > 0
          AND m.san != m.best_move_san
        ORDER BY g.outcome_for_player = 'loss' DESC, m.eval_mate DESC
    """).fetchdf()
    return df


def get_knight_rim_performance(sqlite_conn, config_path=None):
    """Mirrors analysis/knight_rim_performance.py -- "a knight on the rim
    is dim" tested directly, by game phase. Found the proverb holds in
    the opening/middlegame but flips in the endgame (interior moves
    riskier there, 8.3% vs. 5.8% -- a thin 69-move rim-endgame cell).
    Returns (overall_df, phase_df)."""
    cfg = get_config(config_path)
    analytics.ensure_structure_ctx(sqlite_conn, cfg)
    middlegame_ply = cfg["analytics"]["middlegame_ply"]

    overall_rows = sqlite_conn.execute(f"""
        SELECT {RIM_SQL} AS is_rim, COUNT(*) AS n_moves, AVG(cpl) AS acpl,
               100.0 * SUM(CASE WHEN classification='blunder' THEN 1 ELSE 0 END) / COUNT(*) AS blunder_rate
        FROM moves
        WHERE is_player_move=1 AND piece='N' AND cpl IS NOT NULL AND to_square IS NOT NULL
        GROUP BY is_rim
    """).fetchall()
    overall_df = pd.DataFrame(overall_rows, columns=["is_rim", "n_moves", "acpl", "blunder_rate"])
    overall_df["location"] = overall_df.is_rim.map({1: "rim", 0: "interior"})

    phase_rows = sqlite_conn.execute(f"""
        SELECT {RIM_SQL} AS is_rim,
               CASE WHEN m.ply < {middlegame_ply} THEN 'opening'
                    WHEN sc.endgame_ply IS NULL OR m.ply < sc.endgame_ply THEN 'middlegame'
                    ELSE 'endgame' END AS phase,
               COUNT(*) AS n_moves, AVG(m.cpl) AS acpl,
               100.0 * SUM(CASE WHEN m.classification='blunder' THEN 1 ELSE 0 END) / COUNT(*) AS blunder_rate
        FROM moves m JOIN structure_ctx sc ON sc.game_id = m.game_id
        WHERE m.is_player_move=1 AND m.piece='N' AND m.cpl IS NOT NULL AND m.to_square IS NOT NULL
        GROUP BY is_rim, phase
    """).fetchall()
    phase_df = pd.DataFrame(phase_rows, columns=["is_rim", "phase", "n_moves", "acpl", "blunder_rate"])
    phase_df["location"] = phase_df.is_rim.map({1: "rim", 0: "interior"})
    return overall_df, phase_df


def get_motif_breakdown(sqlite_conn):
    """Frequency and avg CPL for each tactical motif the player missed.

    Only covers is_player_move=1 moves classified mistake/blunder where
    annotate.py's Pass 4 was able to identify a motif. Returns an empty
    DataFrame (not None) when no motifs have been classified yet.

    Takes sqlite_conn, not duck_conn -- idx_moves_motif (partial index,
    migration 0031, needs ANALYZE stats to be chosen) makes this a ~4ms
    seek over the ~1.2k motif-bearing rows, vs ~0.5s as a full
    SQLITE_SCAN of all of moves via duck_conn.
    """
    return pd.read_sql_query("""
        SELECT
            motif,
            COUNT(*)                                                                  AS n_missed,
            COUNT(DISTINCT game_id)                                                   AS n_games,
            AVG(cpl)                                                                  AS avg_cpl,
            100.0 * SUM(CASE WHEN classification='blunder' THEN 1 ELSE 0 END)
                  / COUNT(*)                                                           AS blunder_pct
        FROM moves
        WHERE is_player_move = 1
          AND motif IS NOT NULL
          AND classification IN ('mistake', 'blunder')
        GROUP BY motif
        ORDER BY n_missed DESC
    """, sqlite_conn)


# Minimum number of mistake/blunder candidates before an all-zero motif
# count is trusted as "annotation predates motif classification" rather
# than "coincidentally none of a handful of blunders matched a pattern" --
# classify_motif() legitimately returns None for plenty of real blunders
# (anything that isn't a clean fork/pin/skewer/discovery/hanging
# piece/back-rank mate), so zero motifs on a small sample isn't unusual on
# its own. Zero motifs across dozens+ of candidates is not a coincidence.
MOTIF_BACKFILL_MIN_CANDIDATES = 20


def motif_backfill_needed(duck_conn) -> bool:
    """True when this database has real mistake/blunder moves that were
    never run through motif classification at all -- i.e. games analyzed
    before annotate.py's Pass 4 (v0.1.9) existed, and never re-annotated
    since. annotate.run(game_id=None) already recomputes motif for every
    previously-analyzed game (idempotent, see annotate.py's
    fetch_games_to_annotate), so this is purely a detection signal for the
    empty state -- the fix already exists, it just needs to be reachable
    and correctly explained."""
    row = duck_conn.execute("""
        SELECT
            COUNT(*)                                            AS n_candidates,
            SUM(CASE WHEN motif IS NOT NULL THEN 1 ELSE 0 END)  AS n_with_motif
        FROM db.moves
        WHERE is_player_move = 1 AND classification IN ('mistake', 'blunder')
    """).fetchone()
    if row is None:
        return False
    n_candidates, n_with_motif = row
    return n_candidates >= MOTIF_BACKFILL_MIN_CANDIDATES and not n_with_motif


def get_hallucination_blunders(duck_conn, config_path=None):
    """Mirrors analysis/hallucination_blunders.py -- detects hanging a
    real piece (player move classified 'blunder', opponent's IMMEDIATE
    next move recaptures on the exact same square for >=
    hallucination_min_material_delta) and flags whether it was followed
    by a quick resignation. One row per hanging-piece blunder; the view
    layer derives the resilience breakdown and example lists from this
    directly rather than re-querying."""
    cfg = get_config(config_path)
    min_material_delta = cfg["analytics"]["hallucination_min_material_delta"]
    max_moves_to_resign = cfg["analytics"]["hallucination_max_moves_to_resign"]
    max_plies_to_resign = max_moves_to_resign * 2

    hangs = duck_conn.execute(f"""
        SELECT m.game_id, m.ply AS blunder_ply, m.san AS blunder_san,
               g.num_plies, g.outcome_for_player, g.game_end_type,
               g.num_plies - m.ply AS plies_remaining
        FROM db.moves m
        JOIN db.moves m2 ON m2.game_id = m.game_id AND m2.ply = m.ply + 1
        JOIN db.games g ON g.id = m.game_id
        WHERE m.is_player_move = 1 AND m.classification = 'blunder' AND m.cpl IS NOT NULL
          AND m2.is_capture = 1 AND m2.to_square = m.to_square
          AND m2.material_delta >= {min_material_delta}
    """).fetchdf()
    if len(hangs):
        hangs["resigned_quickly"] = (
            (hangs.outcome_for_player == "loss") & (hangs.game_end_type == "resignation") &
            (hangs.plies_remaining <= max_plies_to_resign))
    return hangs


def get_hallucination_context(duck_conn, hangs):
    """Mirrors analysis/hallucination_context.py -- resolves "hallucination
    vs. mouse-slip" using time_spent_seconds on the blundering move, and
    checks whether hangs are concentrated under time pressure. Compares
    against the baseline of ALL analyzed player blunders. Found these are
    genuine hallucinations (NOT skewed toward instant/careless moves) and
    NOT concentrated under time pressure. Returns (time_spent_df, time_pressure_df).

    Takes the already-fetched `hangs` DataFrame (from get_hallucination_blunders)
    rather than re-querying it -- that self-join is the most expensive part
    of this whole panel (~1.3-1.5s), and the view layer already has it
    cached separately; re-running it here would cost that twice per page
    load for no reason."""
    if len(hangs) == 0:
        empty = pd.DataFrame(columns=["bucket", "hang_pct", "baseline_pct"])
        return empty, empty

    detail = duck_conn.execute("""
        SELECT m.game_id, m.ply, m.time_spent_seconds,
               CAST(m.clock_seconds AS DOUBLE) / g.base_seconds AS time_fraction
        FROM db.moves m JOIN db.games g ON g.id = m.game_id
        WHERE m.is_player_move=1 AND m.classification='blunder' AND m.cpl IS NOT NULL
    """).fetchdf()
    hangs_keyed = hangs.merge(
        detail, left_on=["game_id", "blunder_ply"], right_on=["game_id", "ply"], how="left")

    def bucket_compare(hang_vals, baseline_vals, buckets):
        rows = []
        for label, lo, hi in buckets:
            hang_n = int(((hang_vals >= lo) & (hang_vals < hi)).sum())
            base_n = int(((baseline_vals >= lo) & (baseline_vals < hi)).sum())
            hang_pct = 100.0 * hang_n / len(hang_vals) if len(hang_vals) else 0.0
            base_pct = 100.0 * base_n / len(baseline_vals) if len(baseline_vals) else 0.0
            rows.append((label, hang_n, hang_pct, base_n, base_pct))
        return pd.DataFrame(rows, columns=["bucket", "hang_n", "hang_pct", "baseline_n", "baseline_pct"])

    time_spent_df = bucket_compare(hangs_keyed.time_spent_seconds.dropna(),
                                   detail.time_spent_seconds.dropna(), THINKING_TIME_BUCKETS)
    time_pressure_df = bucket_compare(hangs_keyed.time_fraction.dropna(),
                                      detail.time_fraction.dropna(), TIME_PRESSURE_BUCKETS)
    return time_spent_df, time_pressure_df
