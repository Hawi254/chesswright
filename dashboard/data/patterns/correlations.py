"""Sharpness/thinking-time/instant-move correlation queries (gap-analysis
additions, dashboard review 2026-06-22) -- one of eight topic modules
split out of the former dashboard/data/patterns.py.
"""
import pandas as pd

from _common import get_config

from ._shared import SHARPNESS_BUCKETS
from .._shared import THINKING_TIME_BUCKETS, bucket_acpl_blunder_rate, _fetchone_scalar


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
