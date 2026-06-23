"""Helpers and constants used by more than one domain module in this
package -- narrative persistence and headline stats are pulled into
nearly every view; the bucket/threshold constants below are restated in
more than one analysis/*.py-mirroring query and must stay in exact sync
across them, so they live here once rather than in whichever domain
module happened to need them first.
"""
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
    # Explicit checkpoint right after commit -- this dashboard also holds a
    # long-lived DuckDB connection ATTACHed to the same sqlite file
    # (_common.get_duckdb_connection), and empirically (confirmed live,
    # not assumed) a plain commit() on this sqlite3 connection alone left
    # the row sitting in the WAL, invisible to every OTHER connection to
    # this file (a fresh `sqlite3 chess.db` query, a separate Python
    # process) until the whole dashboard process was killed -- i.e. it
    # would NOT have survived an actual restart, defeating the entire
    # point of persisting this. Checkpointing from the writer connection
    # itself, immediately, makes it durable to disk for real.
    sqlite_conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")


def get_headline_stats(duck_conn, sqlite_conn):
    total_games = duck_conn.execute("SELECT COUNT(*) FROM db.games").fetchone()[0]
    analyzed_games = duck_conn.execute("SELECT COUNT(*) FROM db.games WHERE analysis_status='done'").fetchone()[0]
    n_moves, n_games, acpl, blunder_rate = analytics.acpl_and_blunder_rate(sqlite_conn)
    overall_win_pct = duck_conn.execute("""
        SELECT 100.0 * SUM(CASE WHEN outcome_for_player='win' THEN 1 ELSE 0 END) / COUNT(*)
        FROM db.games WHERE outcome_for_player IS NOT NULL
    """).fetchone()[0]
    return {
        "total_games": total_games,
        "analyzed_games": analyzed_games,
        "acpl": acpl,
        "blunder_rate": blunder_rate,
        "win_pct": overall_win_pct,
        "n_analyzed_moves": n_moves,
    }
