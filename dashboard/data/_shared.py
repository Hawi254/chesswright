"""Helpers and constants used by more than one domain module in this
package -- narrative persistence and headline stats are pulled into
nearly every view; the bucket/threshold constants below are restated in
more than one analysis/*.py-mirroring query and must stay in exact sync
across them, so they live here once rather than in whichever domain
module happened to need them first.
"""
import pandas as pd

import analytics

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


def get_headline_stats(duck_conn, sqlite_conn):
    total_games = _fetchone_scalar(duck_conn, "SELECT COUNT(*) FROM db.games")
    analyzed_games = _fetchone_scalar(
        duck_conn, "SELECT COUNT(*) FROM db.games WHERE analysis_status='done'")
    n_moves, n_games, acpl, blunder_rate = analytics.acpl_and_blunder_rate(sqlite_conn)
    overall_win_pct = _fetchone_scalar(duck_conn, """
        SELECT 100.0 * SUM(CASE WHEN outcome_for_player='win' THEN 1 ELSE 0 END) / COUNT(*)
        FROM db.games WHERE outcome_for_player IS NOT NULL
    """, default=None)
    return {
        "total_games": total_games,
        "analyzed_games": analyzed_games,
        "acpl": acpl,
        "blunder_rate": blunder_rate,
        "win_pct": overall_win_pct,
        "n_analyzed_moves": n_moves,
    }
