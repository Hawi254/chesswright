"""Opening-position-stats / repeated-position / repertoire-holes cache
rebuilds -- one of four sibling modules split out of analytics.py
(largest-file modularization, 2026-07-17). Holds _open_write_connection
too (moved here from analytics.py, see this task's header for why: it's
called only by the three ensure_* functions below, all three of which
live in this file, and analytics.py needs to import THEM forward from
here -- keeping _open_write_connection in the entry file would have made
this a circular import).
"""
import sqlite3
import time

from db import get_connection

# Same retry shape as dashboard/_common.py's get_duckdb_connection ATTACH
# retry -- see ensure_opening_position_stats's docstring for why this one
# needs it too.
_REBUILD_RETRY_ATTEMPTS = 5
_REBUILD_RETRY_DELAY_SEC = 2.0


def _open_write_connection(conn):
    """A fresh, independent sqlite3 connection to the SAME database file
    *conn* is already open on -- for a long (multi-second) rebuild
    transaction, NOT for reuse of *conn* itself.

    Confirmed live why this matters (not a guess): dashboard/_common.py's
    sqlite_conn is a single st.cache_resource connection object SHARED
    across every Streamlit session/thread in the process. Python's
    sqlite3 module serializes concurrent calls on ONE connection object
    at the C level -- it doesn't corrupt results, but a second thread's
    read genuinely BLOCKS for the entire duration of whatever the first
    thread is doing on that same object. Measured directly: a plain
    SELECT on the shared connection took ~10.7s to return (matching the
    writer's own duration) while another thread ran a long multi-
    statement write on that SAME object -- every OTHER page sharing
    sqlite_conn would stall for the write's full duration. Reported live
    as "several unrelated charts were blank right after upgrading, fine
    after relaunching" -- the first-ever run of these long caches was
    exactly the multi-second window in which that stall could be hit.

    Fix, verified the same way: give the long write its OWN connection
    object instead. SQLite's real lock semantics then apply (a writer's
    RESERVED lock doesn't block concurrent SHARED-lock readers on a
    DIFFERENT connection -- only the brief COMMIT-time EXCLUSIVE phase
    can, and busy_timeout=5000 already covers that). Measured: the same
    concurrent read that took 10.7s against a shared connection took
    0.0006s once the long write moved to its own connection.
    """
    db_path = conn.execute("PRAGMA database_list").fetchone()[2]
    return get_connection(db_path)


def ensure_opening_position_stats(conn, max_ply=40):
    """Idempotent within a connection -- rebuilds opening_position_stats_cache
    (migration 0029) only when the number of analyzed (zobrist_hash-bearing)
    moves has changed since the last build. Same persisted count-sentinel
    pattern as ensure_structure_ctx/ensure_session_ctx above, sharing their
    ctx_cache_meta row rather than a parallel one.

    Unlike those two, there's no per-session TEMP TABLE fast path -- callers
    query opening_position_stats_cache directly (it's already a small,
    indexed point-lookup table; loading it into a TEMP TABLE every session
    would cost more than it saves).

    max_ply bounds the cache to the opening phase (default: first 20 full
    moves each side). Positions past that are rare enough live queries
    handle them fine -- see get_opening_moves_from_fen's cache/live split.
    """
    move_count = conn.execute(
        "SELECT COUNT(*) FROM moves WHERE zobrist_hash IS NOT NULL"
    ).fetchone()[0]
    meta = conn.execute(
        "SELECT opening_stats_move_count FROM ctx_cache_meta WHERE id=1"
    ).fetchone()
    cache_current = (meta and meta[0] == move_count and move_count > 0
                      and conn.execute(
                          "SELECT COUNT(*) FROM opening_position_stats_cache"
                      ).fetchone()[0] > 0)
    if cache_current:
        return

    # This DELETE+INSERT is a single ~5-8s transaction (measured, ~1.2M
    # moves rows aggregated) -- run on a dedicated connection (see
    # _open_write_connection), not the shared *conn*, so every other page
    # sharing that connection isn't blocked for the whole rebuild. Still
    # long enough to collide with a genuinely separate writer (worker.
    # run()'s per-move commits, or another already-running Chesswright
    # process's own concurrent rebuild of this same cache -- this
    # function's staleness check is per-process, so two processes open on
    # the same chess.db can race to rebuild it at the same time).
    # db.get_connection()'s PRAGMA busy_timeout=5000 was sized for "the
    # brief moment those per-move commits actually take" (its own
    # docstring) -- a multi-second write blows straight through that
    # budget. Retried here the same way get_duckdb_connection's ATTACH
    # already retries for the identical "another writer may still be
    # mid-commit" reason, rather than adding a new pattern.
    write_conn = _open_write_connection(conn)
    try:
        for attempt in range(1, _REBUILD_RETRY_ATTEMPTS + 1):
            try:
                write_conn.execute("DELETE FROM opening_position_stats_cache")
                write_conn.execute("""
                    INSERT INTO opening_position_stats_cache
                    SELECT
                        m.ply,
                        m.zobrist_hash,
                        g.player_color,
                        m.san,
                        MAX(m.is_player_move),
                        COUNT(DISTINCT m.game_id),
                        COUNT(DISTINCT CASE WHEN g.outcome_for_player = 'win'  THEN m.game_id END),
                        COUNT(DISTINCT CASE WHEN g.outcome_for_player = 'draw' THEN m.game_id END),
                        COUNT(DISTINCT CASE WHEN g.outcome_for_player = 'loss' THEN m.game_id END),
                        ROUND(AVG(CASE WHEN m.is_player_move = 1 THEN m.cpl END), 0)
                    FROM moves m
                    JOIN games g ON g.id = m.game_id
                    WHERE m.zobrist_hash IS NOT NULL AND m.ply <= ?
                    GROUP BY m.ply, m.zobrist_hash, g.player_color, m.san
                """, [max_ply])
                write_conn.execute(
                    "UPDATE ctx_cache_meta SET opening_stats_move_count=?, built_at=CURRENT_TIMESTAMP WHERE id=1",
                    (move_count,))
                write_conn.commit()
                return
            except sqlite3.OperationalError as e:
                write_conn.rollback()
                if "database is locked" not in str(e) or attempt == _REBUILD_RETRY_ATTEMPTS:
                    raise
                time.sleep(_REBUILD_RETRY_DELAY_SEC * attempt)
    finally:
        write_conn.close()


def ensure_repeated_positions_cache(conn, min_games=5):
    """Idempotent within a connection -- rebuilds repeated_positions_cache
    (migration 0030) only when the count of analyzed (zobrist_hash-
    bearing) moves has changed since the last build. Same pattern as
    ensure_opening_position_stats.

    min_games=5 bakes in the only value get_most_repeated_positions'
    caller ever actually uses (confirmed by reading every call site --
    the UI only exposes a top_n slider, min_games is never overridden)
    -- a stricter read-time filter is then just a cheap WHERE over this
    already-small cached table.

    Unlike opening_position_stats_cache, this covers every ply, not just
    the opening phase -- "most-repeated position" is a whole-game concept
    (recurring endgame structures count too), so there's no ply cutoff to
    bound the scan. Measured ~30s to build on the real ~2.3M-row moves
    table -- a genuinely long write, hence the same retry-with-backoff as
    ensure_opening_position_stats (even more likely to collide with
    another writer given how long this one holds the lock).
    """
    move_count = conn.execute(
        "SELECT COUNT(*) FROM moves WHERE zobrist_hash IS NOT NULL"
    ).fetchone()[0]
    meta = conn.execute(
        "SELECT repeated_positions_move_count FROM ctx_cache_meta WHERE id=1"
    ).fetchone()
    cache_current = (meta and meta[0] == move_count and move_count > 0
                      and conn.execute(
                          "SELECT COUNT(*) FROM repeated_positions_cache"
                      ).fetchone()[0] > 0)
    if cache_current:
        return

    # Run on a dedicated connection (see _open_write_connection's
    # docstring) -- ~30s is long enough that sharing *conn* would stall
    # every other page using it for the whole rebuild, not just risk a
    # "database is locked" collision.
    write_conn = _open_write_connection(conn)
    try:
        for attempt in range(1, _REBUILD_RETRY_ATTEMPTS + 1):
            try:
                write_conn.execute("DELETE FROM repeated_positions_cache")
                write_conn.execute("""
                    WITH per_group AS (
                        SELECT m.ply, m.zobrist_hash, g.opening_family,
                               COUNT(DISTINCT m.game_id) AS n_local_games,
                               COUNT(DISTINCT CASE WHEN g.outcome_for_player='win'  THEN m.game_id END) AS local_wins,
                               COUNT(DISTINCT CASE WHEN g.outcome_for_player='draw' THEN m.game_id END) AS local_draws,
                               COUNT(DISTINCT CASE WHEN g.outcome_for_player='loss' THEN m.game_id END) AS local_losses
                        FROM moves m JOIN games g ON g.id = m.game_id
                        WHERE m.zobrist_hash IS NOT NULL
                        GROUP BY m.ply, m.zobrist_hash, g.opening_family
                    ),
                    totals AS (
                        SELECT ply, zobrist_hash,
                               SUM(n_local_games) AS n_games,
                               100.0 * SUM(local_wins)   / SUM(n_local_games) AS win_pct,
                               100.0 * SUM(local_draws)  / SUM(n_local_games) AS draw_pct,
                               100.0 * SUM(local_losses) / SUM(n_local_games) AS loss_pct
                        FROM per_group
                        GROUP BY ply, zobrist_hash
                        HAVING SUM(n_local_games) >= ?
                    ),
                    ranked_opening AS (
                        SELECT ply, zobrist_hash, opening_family,
                               ROW_NUMBER() OVER (
                                   PARTITION BY ply, zobrist_hash
                                   ORDER BY n_local_games DESC
                               ) AS rn
                        FROM per_group
                        WHERE opening_family IS NOT NULL
                    )
                    INSERT INTO repeated_positions_cache
                    SELECT t.ply, t.zobrist_hash, t.n_games, t.win_pct, t.draw_pct, t.loss_pct,
                           ro.opening_family
                    FROM totals t
                    LEFT JOIN ranked_opening ro
                        ON ro.ply = t.ply AND ro.zobrist_hash = t.zobrist_hash AND ro.rn = 1
                """, [min_games])
                write_conn.execute(
                    "UPDATE ctx_cache_meta SET repeated_positions_move_count=?, built_at=CURRENT_TIMESTAMP WHERE id=1",
                    (move_count,))
                write_conn.commit()
                return
            except sqlite3.OperationalError as e:
                write_conn.rollback()
                if "database is locked" not in str(e) or attempt == _REBUILD_RETRY_ATTEMPTS:
                    raise
                time.sleep(_REBUILD_RETRY_DELAY_SEC * attempt)
    finally:
        write_conn.close()


def ensure_repertoire_holes_cache(conn, min_appearances=3):
    """Idempotent within a connection -- rebuilds repertoire_holes_cache
    (migration 0030) only when the count of analyzed player moves
    (is_player_move=1 AND cpl IS NOT NULL) has changed since the last
    build. Same pattern as ensure_opening_position_stats.

    min_appearances=3 bakes in the loosest threshold any real caller ever
    uses (openings_view.py's own slider floor) -- a stricter read-time
    filter is then just a cheap WHERE over this already-small cached
    table (~126 rows measured on the real 2.3M-row moves table, bounded
    by requiring >=2 distinct moves from the same position, which by
    construction already implies >=2 games reached it).
    """
    move_count = conn.execute(
        "SELECT COUNT(*) FROM moves WHERE is_player_move=1 AND cpl IS NOT NULL"
    ).fetchone()[0]
    meta = conn.execute(
        "SELECT repertoire_holes_move_count FROM ctx_cache_meta WHERE id=1"
    ).fetchone()
    cache_current = (meta and meta[0] == move_count and move_count > 0
                      and conn.execute(
                          "SELECT COUNT(*) FROM repertoire_holes_cache"
                      ).fetchone()[0] > 0)
    if cache_current:
        return

    # Run on a dedicated connection (see _open_write_connection's
    # docstring) -- ~9s is long enough that sharing *conn* would stall
    # every other page using it for the whole rebuild, not just risk a
    # "database is locked" collision.
    write_conn = _open_write_connection(conn)
    try:
        for attempt in range(1, _REBUILD_RETRY_ATTEMPTS + 1):
            try:
                write_conn.execute("DELETE FROM repertoire_holes_cache")
                write_conn.execute("""
                    WITH pos_stats AS (
                        SELECT
                            m.fen_before,
                            COUNT(DISTINCT m.game_id)                  AS n_games,
                            COUNT(DISTINCT m.san)                      AS n_distinct_moves,
                            AVG(m.cpl)                                 AS avg_cpl,
                            CAST(ROUND(AVG(m.move_number)) AS INTEGER) AS approx_move_number,
                            COUNT(DISTINCT m.san) * AVG(m.cpl)         AS hole_score
                        FROM moves m
                        WHERE m.is_player_move = 1
                          AND m.cpl            IS NOT NULL
                          AND m.fen_before     IS NOT NULL
                        GROUP BY m.fen_before
                        HAVING COUNT(DISTINCT m.game_id) >= ?
                           AND COUNT(DISTINCT m.san)     >= 2
                    ),
                    move_counts AS (
                        SELECT
                            fen_before, san,
                            ROW_NUMBER() OVER (
                                PARTITION BY fen_before ORDER BY COUNT(*) DESC
                            ) AS rn
                        FROM moves
                        WHERE is_player_move = 1 AND fen_before IS NOT NULL
                        GROUP BY fen_before, san
                    ),
                    top_openings AS (
                        SELECT
                            m.fen_before, g.opening_family,
                            ROW_NUMBER() OVER (
                                PARTITION BY m.fen_before ORDER BY COUNT(*) DESC
                            ) AS rn
                        FROM moves m
                        JOIN games g ON g.id = m.game_id
                        WHERE m.is_player_move = 1
                          AND m.fen_before     IS NOT NULL
                          AND g.opening_family IS NOT NULL
                        GROUP BY m.fen_before, g.opening_family
                    )
                    INSERT INTO repertoire_holes_cache
                    SELECT
                        ps.fen_before, ps.n_games, ps.n_distinct_moves,
                        ROUND(ps.avg_cpl, 1), ps.approx_move_number,
                        ROUND(ps.hole_score, 1), mc.san, tof.opening_family
                    FROM pos_stats ps
                    LEFT JOIN move_counts  mc  ON mc.fen_before  = ps.fen_before AND mc.rn  = 1
                    LEFT JOIN top_openings tof ON tof.fen_before = ps.fen_before AND tof.rn = 1
                """, [min_appearances])
                write_conn.execute(
                    "UPDATE ctx_cache_meta SET repertoire_holes_move_count=?, built_at=CURRENT_TIMESTAMP WHERE id=1",
                    (move_count,))
                write_conn.commit()
                return
            except sqlite3.OperationalError as e:
                write_conn.rollback()
                if "database is locked" not in str(e) or attempt == _REBUILD_RETRY_ATTEMPTS:
                    raise
                time.sleep(_REBUILD_RETRY_DELAY_SEC * attempt)
    finally:
        write_conn.close()
