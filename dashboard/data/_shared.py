"""Helpers and constants used by more than one domain module in this
package -- narrative persistence and headline stats are pulled into
nearly every view; the bucket/threshold constants below are restated in
more than one analysis/*.py-mirroring query and must stay in exact sync
across them, so they live here once rather than in whichever domain
module happened to need them first.
"""
import math

import pandas as pd

import analytics
import chess_utils
from confidence import confidence_tier, default_thresholds

# Mirrors analysis/time_pressure.py's BUCKETS.
TIME_PRESSURE_BUCKETS = [
    ("critical (<5%)", 0.0, 0.05),
    ("low (5-15%)", 0.05, 0.15),
    ("moderate (15-30%)", 0.15, 0.30),
    ("comfortable (30-60%)", 0.30, 0.60),
    ("plenty (60-100%)", 0.60, 1.0001),
]
# Mirrors analysis/thinking_time.py's BUCKETS.
THINKING_TIME_BUCKETS = [
    ("instant (<1s)", 0, 1),
    ("quick (1-3s)", 1, 3),
    ("considered (3-10s)", 3, 10),
    ("deliberate (10-30s)", 10, 30),
    ("long think (30s+)", 30, 10**9),
]
# Mirrors analysis/giant_killing.py's UPSET_THRESHOLD/COLLAPSE_THRESHOLD.
GIANT_KILLING_UPSET_THRESHOLD = -300
GIANT_KILLING_COLLAPSE_THRESHOLD = 300
# Mirrors analysis/comebacks.py's COMEBACK_THRESHOLD/COLLAPSE_THRESHOLD.
COMEBACK_WP_THRESHOLD = 0.10
COLLAPSE_WP_THRESHOLD = 0.90
# Middlegame trade tiers, keyed on chess_utils.non_pawn_piece_count (both
# sides combined, max 14 = 2*(1Q+2R+2B+2N)). Unlike the endgame's 4-bucket
# _classify_endgame_type below (piece TYPE identity, a chess-rule constant
# that doesn't need tuning), these are numeric cutoffs chosen against the
# real dev DB's middlegame_sig distribution at ply 24 (30,973 rows,
# 2026-07-10): 14 alone is 31.9% (no non-pawn piece captured yet -- a real
# invariant, not an arbitrary cut), 12-13 is 48.7% (well past the single
# biggest exact-sig bucket, one symmetric pair traded), 9-11 is 18.7%, and
# <=8 is a thin 0.7% tail. Kept as a fixed constant list (not
# cfg["analytics"]) following THINKING_TIME_BUCKETS/TIME_PRESSURE_BUCKETS's
# precedent above (an ordered (label, lo, hi) range list bucketing a
# continuous/ordinal value), not structure_min_games_per_group/
# action_side_capture_ratio's precedent (a single scalar gate threshold) --
# this is a multi-cutoff scheme, not one tunable knob.
MIDDLEGAME_TRADE_TIERS = [
    ("No trades", 14, 15),
    ("Light trades", 12, 14),
    ("Moderate trades", 9, 12),
    ("Heavy trades", 0, 9),
]


def _classify_endgame_type(material_sig: str) -> str | None:
    """Map a player-relative material_sig to a broad endgame category.

    material_sig format (from chess_utils.material_signature): piece letters
    Q/R/B/N/P each followed by their count, white side first, then 'v', then
    black side. e.g. "R1P5vP4" -> Rook, "B1N1P4vN2P3" -> Minor piece.
    Kings are NOT in the signature (they're always present, not listed).

    Originally game_endings.py-only, promoted here once a second (patterns.py)
    and, it turns out, already a third (analysis_batches.py) module needed
    the identical classifier -- same promotion _quarterly_zero_fill got
    below."""
    if not material_sig:
        return None
    if "Q" in material_sig:
        return "Queen"
    if "R" in material_sig:
        return "Rook"
    if "B" in material_sig or "N" in material_sig:
        return "Minor piece"
    return "King & pawn"


def _classify_middlegame_trade_tier(material_sig: str) -> str | None:
    """Map a material_sig to a MIDDLEGAME_TRADE_TIERS label via
    chess_utils.non_pawn_piece_count. Unlike _classify_endgame_type, piece
    TYPE is not a useful axis here -- 97.1% of real middlegame_sig rows
    still contain a queen (confirmed live, 2026-07-10), so a type-based
    split would dump nearly everything into one bucket. How much material
    has come off is the real variation at this checkpoint."""
    if not material_sig:
        return None
    count = chess_utils.non_pawn_piece_count(material_sig)
    for label, lo, hi in MIDDLEGAME_TRADE_TIERS:
        if lo <= count < hi:
            return label
    return None


def _quarterly_zero_fill(df, count_cols):
    """Expand a (year, quarter, counts...) frame to one row per quarter
    from the first to the last observed, zero-filling the given count
    columns -- so a quarter with no qualifying games at all renders as an
    honest gap rather than being silently skipped (same convention as
    evolution.period_shares). Adds period (sortable int) and label
    ("2019 Q1") columns; callers compute their own pct columns on top,
    using NaN (not 0) where a denominator is 0 -- 0/0 is "no data," not
    "0%." Shared by every calendar trend in this package that needs the
    same merge/fill dance (originally game_endings.py-only, promoted here
    once matchups.py needed the identical shape for the giant-killing
    rate trend)."""
    df["period"] = df["year"].astype(int) * 4 + (df["quarter"].astype(int) - 1)
    all_periods = pd.DataFrame({"period": range(int(df["period"].min()), int(df["period"].max()) + 1)})
    df = all_periods.merge(df, on="period", how="left")
    df["year"] = df["period"] // 4
    df["quarter"] = df["period"] % 4 + 1
    for col in count_cols:
        df[col] = df[col].fillna(0).astype(int)
    df["label"] = df["year"].astype(str) + " Q" + df["quarter"].astype(str)
    return df


def bucket_acpl_blunder_rate(df, value_col, buckets):
    """Buckets df by value_col into the given (label, lo, hi) ranges,
    returning one row per non-empty bucket with columns [bucket, n_moves,
    acpl, blunder_rate]. df must have cpl and classification columns.

    Shared by every per-move correlation query that buckets the SAME
    "is_player_move=1 AND cpl IS NOT NULL" set of moves by a different
    column (sharpness, thinking time, clock-remaining fraction) -- each
    used to re-implement this loop independently, which is exactly the
    kind of near-identical-copy drift this was pulled out to prevent."""
    rows = []
    for label, lo, hi in buckets:
        sub = df[(df[value_col] >= lo) & (df[value_col] < hi)]
        if len(sub):
            rows.append((label, len(sub), sub.cpl.mean(),
                         100.0 * (sub.classification == "blunder").sum() / len(sub)))
    return pd.DataFrame(rows, columns=["bucket", "n_moves", "acpl", "blunder_rate"])


# ---------- Claude commentary persistence (Claude-API extension, 2026-06) ----------
# Writes go through sqlite_conn (the real sqlite3 connection from
# db.get_connection(), not the DuckDB-over-sqlite_scanner attachment used
# for reads elsewhere in this package) -- this project's DB-write convention.

def get_cached_narrative(sqlite_conn, subject_type, subject_key):
    """Returns (response_text, generated_at) or None if nothing's cached yet."""
    row = sqlite_conn.execute(
        "SELECT response_text, generated_at FROM claude_narratives "
        "WHERE subject_type = ? AND subject_key = ?",
        (subject_type, subject_key)).fetchone()
    return tuple(row) if row else None


def save_narrative(sqlite_conn, subject_type, subject_key, response_text, model):
    sqlite_conn.execute("""
        INSERT INTO claude_narratives (subject_type, subject_key, response_text, model, generated_at)
        VALUES (?, ?, ?, ?, datetime('now'))
        ON CONFLICT(subject_type, subject_key) DO UPDATE SET
            response_text = excluded.response_text,
            model = excluded.model,
            generated_at = excluded.generated_at
    """, (subject_type, subject_key, response_text, model))
    sqlite_conn.commit()
    # No explicit checkpoint needed here: this dashboard's DuckDB connection
    # (_common.get_duckdb_connection) only ever ATTACHes a private,
    # read-only snapshot copy of the sqlite file, never the live file, so
    # there's no other connection that needs this write checkpointed to
    # disk for immediate visibility. A plain commit() on this WAL-mode
    # sqlite3 connection is already durable and immediately visible to any
    # other real connection to the file.


def _fetchone_scalar(duck_conn, sql, default: int | None = 0):
    """duck_conn.execute(sql).fetchone() should always return exactly one
    row for a bare COUNT(*)/aggregate query -- a None here means something
    went wrong beneath the query itself (confirmed live: a transient race
    on the shared DuckDB connection, now fixed at the source in
    _common.py's locking wrapper), not a legitimate empty result. Treat it
    as unknown rather than crashing the page with a raw traceback -- same
    "explain what's missing, don't crash" philosophy as
    theme.thin_data_message()."""
    row = duck_conn.execute(sql).fetchone()
    return row[0] if row is not None else default


MIN_ANALYZED_MOVES_FOR_RATING_BENCHMARK = 20  # same cutoff as insights.py's
# MIN_BUCKET_MOVES -- the established "is this ACPL number reliable"
# threshold elsewhere in this codebase. Duplicated as a local constant
# rather than imported from insights.py to avoid a _shared.py -> insights.py
# -> _shared.py import cycle (insights.py already imports from _shared.py).


def estimate_rating_from_acpl(acpl: float) -> int:
    """Population-level ACPL-to-rating correlation, not a personal or
    per-finding prediction. Source: Chess Digits' analysis of human play
    (ELO ~= 3100 * e^(-0.01 * ACPL)), corroborated by Regan & Haworth's
    "Intrinsic Chess Ratings" (>0.98 correlation between ACPL/STDCPL and
    Elo across tournament data). The source community is explicit this
    relationship is weak at the level of attributing a rating delta to
    one specific behavior -- do not use this to estimate per-finding
    impact, only this one aggregate reference point."""
    return round(3100 * math.exp(-0.01 * acpl))


def get_headline_stats(duck_conn, sqlite_conn):
    total_games = _fetchone_scalar(duck_conn, "SELECT COUNT(*) FROM db.games")
    analyzed_games = _fetchone_scalar(
        duck_conn, "SELECT COUNT(*) FROM db.games WHERE analysis_status='done'")
    n_moves, n_games, acpl, blunder_rate = analytics.acpl_and_blunder_rate(sqlite_conn)
    overall_win_pct = _fetchone_scalar(duck_conn, """
        SELECT 100.0 * SUM(CASE WHEN outcome_for_player='win' THEN 1 ELSE 0 END) / COUNT(*)
        FROM db.games WHERE outcome_for_player IS NOT NULL
    """, default=None)

    rating_confidence = None
    implied_rating = None
    if acpl is not None:
        rating_confidence = confidence_tier(
            n_moves, default_thresholds(MIN_ANALYZED_MOVES_FOR_RATING_BENCHMARK))
        if rating_confidence != "insufficient":
            implied_rating = estimate_rating_from_acpl(acpl)
        else:
            rating_confidence = None

    return {
        "total_games": total_games,
        "analyzed_games": analyzed_games,
        "acpl": acpl,
        "blunder_rate": blunder_rate,
        "win_pct": overall_win_pct,
        "n_analyzed_moves": n_moves,
        "implied_rating": implied_rating,
        "rating_confidence": rating_confidence,
    }
