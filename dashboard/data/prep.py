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

    n_games/score_pct are computed from db.games ALONE (one row per game,
    a true GROUP BY at game grain) and avg_cpl from a separate move-level
    aggregate, then joined on (color, opening) -- NOT from one query that
    LEFT JOINs moves directly under the games GROUP BY. A single combined
    query multiplies each game into one row per analysed player move
    before the GROUP BY runs, so COUNT(*) counted (game, move) pairs
    instead of games (inflating n_games -- confirmed live, 11 real games
    against one opponent showed as 295), and AVG(CASE ...) over that same
    multiplied resultset silently over-weighted score_pct toward games
    with more analysed moves, since outcome_for_player is a per-game fact
    repeated once per move row. get_opening_tendencies right below this
    function already gets n_games right via COUNT(DISTINCT g.id) -- but
    never needed a game-level rate column, so it never hit this second
    part of the bug.
    """
    games_df = duck_conn.execute("""
        SELECT
            player_color                                               AS color,
            opening_family                                             AS opening,
            COUNT(*)                                                   AS n_games,
            ROUND(AVG(CASE WHEN outcome_for_player = 'win'  THEN 1.0
                           WHEN outcome_for_player = 'draw' THEN 0.5
                           ELSE 0.0 END) * 100.0, 1)                  AS score_pct
        FROM db.games
        WHERE analysis_status = 'done'
          AND opening_family  IS NOT NULL
        GROUP BY player_color, opening_family
        HAVING COUNT(*) >= 3
        ORDER BY n_games DESC
        LIMIT ?
    """, [top_n]).fetchdf()
    if games_df.empty:
        games_df["avg_cpl"] = pd.Series(dtype="float64")
        return games_df

    cpl_df = duck_conn.execute("""
        SELECT
            g.player_color   AS color,
            g.opening_family AS opening,
            ROUND(AVG(m.cpl), 1) AS avg_cpl
        FROM db.games g
        JOIN db.moves m ON m.game_id = g.id AND m.is_player_move = 1
        WHERE g.analysis_status = 'done'
          AND g.opening_family  IS NOT NULL
        GROUP BY g.player_color, g.opening_family
    """).fetchdf()
    return games_df.merge(cpl_df, on=["color", "opening"], how="left")


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
