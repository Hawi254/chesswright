"""Opponent scouting queries -- run against an opponent's isolated database.

These functions take explicit duck_conn returned by open_opponent_connections(),
not the cached connections from get_connections() (which point at the user's DB).
"""
import pandas as pd

from _common import get_duckdb_connection, get_sqlite_connection
import opponent_analysis


def open_opponent_connections(username: str):
    """Return (sqlite_conn, duck_conn) for an opponent's database.

    Returns (None, None) if the opponent's database doesn't exist yet.
    The caller is responsible for closing both connections when done.
    """
    db_path = opponent_analysis.get_opponent_db_path(username)
    if not db_path.exists():
        return None, None
    return (
        get_sqlite_connection(str(db_path)),
        get_duckdb_connection(str(db_path)),
    )


def get_recent_form(duck_conn, top_n: int = 20) -> pd.DataFrame:
    """Opening repertoire by color -- what the opponent actually plays.

    Groups by color and opening_family, filtered to openings with 3+ games.
    """
    return duck_conn.execute("""
        SELECT
            g.player_color                                             AS color,
            g.opening_family                                           AS opening,
            COUNT(*)                                                   AS n_games,
            ROUND(AVG(CASE WHEN g.outcome_for_player = 'win'  THEN 1.0
                           WHEN g.outcome_for_player = 'draw' THEN 0.5
                           ELSE 0.0 END) * 100.0, 1)                  AS score_pct,
            ROUND(AVG(m.cpl), 1)                                       AS avg_cpl
        FROM db.games g
        LEFT JOIN db.moves m ON m.game_id = g.id AND m.is_player_move = 1
        WHERE g.analysis_status = 'done'
          AND g.opening_family  IS NOT NULL
        GROUP BY g.player_color, g.opening_family
        HAVING COUNT(*) >= 3
        ORDER BY n_games DESC
        LIMIT ?
    """, [top_n]).fetchdf()


def get_opening_tendencies(duck_conn, top_n: int = 20) -> pd.DataFrame:
    """Blunder rate and ACPL by opening -- where does the opponent go wrong?

    Sorted by blunder_pct descending so the weakest openings appear first.
    """
    return duck_conn.execute("""
        SELECT
            g.opening_family                                           AS opening,
            g.player_color                                             AS color,
            COUNT(DISTINCT g.id)                                       AS n_games,
            ROUND(AVG(m.cpl), 1)                                       AS avg_cpl,
            ROUND(
                100.0 * SUM(CASE WHEN m.classification = 'blunder' THEN 1 ELSE 0 END)
                / NULLIF(COUNT(m.id), 0),
                1
            )                                                          AS blunder_pct
        FROM db.games g
        JOIN db.moves m ON m.game_id = g.id AND m.is_player_move = 1
        WHERE g.analysis_status = 'done'
          AND m.cpl             IS NOT NULL
          AND g.opening_family  IS NOT NULL
        GROUP BY g.opening_family, g.player_color
        HAVING COUNT(DISTINCT g.id) >= 3
        ORDER BY blunder_pct DESC
        LIMIT ?
    """, [top_n]).fetchdf()
