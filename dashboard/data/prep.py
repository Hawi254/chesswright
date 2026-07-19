"""Opponent scouting queries -- run against an opponent's isolated database.

These functions take explicit duck_conn returned by open_opponent_connections(),
not the cached connections from get_connections() (which point at the user's DB).
"""
import pathlib

import pandas as pd

from connections import get_duckdb_connection, get_sqlite_connection
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


def get_repertoire(duck_conn, top_n: int = 20) -> pd.DataFrame:
    """Opening repertoire by color, merging what the opponent plays with
    how they score and where they go wrong -- replaces get_recent_form()
    and get_opening_tendencies(), which computed overlapping aggregates
    over the same (player_color, opening_family) grouping in two separate
    tables the Streamlit page rendered side by side (Opening Repertoire /
    Where They Go Wrong). The React frontend renders one sortable table
    instead.

    n_games/score_pct are computed from db.games ALONE (one row per game,
    a true GROUP BY at game grain) and avg_cpl/blunder_pct from a separate
    move-level aggregate, then joined on (color, opening) -- NOT from one
    query that LEFT JOINs moves directly under the games GROUP BY. A
    single combined query multiplies each game into one row per analysed
    player move before the GROUP BY runs, so COUNT(*) counts (game, move)
    pairs instead of games (inflating n_games -- confirmed live, 11 real
    games against one opponent showed as 295), and AVG(CASE ...) over
    that same multiplied resultset silently over-weights score_pct toward
    games with more analysed moves, since outcome_for_player is a
    per-game fact repeated once per move row.

    No default sort -- the frontend table controls sort order.
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
        games_df["blunder_pct"] = pd.Series(dtype="float64")
        return games_df

    tendencies_df = duck_conn.execute("""
        SELECT
            g.player_color   AS color,
            g.opening_family AS opening,
            ROUND(AVG(m.cpl), 1) AS avg_cpl,
            ROUND(
                100.0 * SUM(CASE WHEN m.classification = 'blunder' THEN 1 ELSE 0 END)
                / NULLIF(COUNT(m.id), 0),
                1
            )                                                          AS blunder_pct
        FROM db.games g
        JOIN db.moves m ON m.game_id = g.id AND m.is_player_move = 1
        WHERE g.analysis_status = 'done'
          AND g.opening_family  IS NOT NULL
        GROUP BY g.player_color, g.opening_family
    """).fetchdf()
    return games_df.merge(tendencies_df, on=["color", "opening"], how="left")


def get_scout_summary(duck_conn) -> dict:
    """Games analysed, color split, and date range -- the Opponent Prep
    dossier strip's three headline numbers."""
    row = duck_conn.execute("""
        SELECT
            COUNT(*)                                                      AS n_games,
            SUM(CASE WHEN player_color = 'white' THEN 1 ELSE 0 END)       AS n_white,
            SUM(CASE WHEN player_color = 'black' THEN 1 ELSE 0 END)       AS n_black,
            MIN(utc_date)                                                 AS date_from,
            MAX(utc_date)                                                 AS date_to
        FROM db.games
        WHERE analysis_status = 'done'
    """).fetchone()
    n_games, n_white, n_black, date_from, date_to = row
    return {
        "games_analyzed": n_games or 0,
        "color_split": {"white": n_white or 0, "black": n_black or 0},
        "date_range": {"from": date_from, "to": date_to},
    }


def list_scouted_opponents(main_db_path: str) -> list:
    """Previously-analysed opponents -- scans the opponents/ directory
    next to the main DB. Same logic as prep_view.py's
    _render_prev_opponents, extracted so the API route doesn't
    reimplement a directory scan."""
    opponents_dir = pathlib.Path(main_db_path).parent / "opponents"
    if not opponents_dir.exists():
        return []
    return [
        d.name for d in sorted(opponents_dir.iterdir())
        if d.is_dir() and (d / "games.db").exists()
    ]
