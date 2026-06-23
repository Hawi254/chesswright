"""Overview page queries."""


def get_rating_trajectory(duck_conn):
    """Full dataset (player_rating is board-derived) -- richer than
    analysis/rating_trajectory.py's analyzed-only version, since rating
    itself needs no engine analysis."""
    return duck_conn.execute("""
        SELECT year, AVG(player_rating) AS avg_rating, COUNT(*) AS n_games
        FROM db.games WHERE year IS NOT NULL AND player_rating IS NOT NULL
        GROUP BY year ORDER BY year
    """).fetchdf()


def get_acpl_trajectory(duck_conn):
    """Analyzed games only -- engine-derived, separate population from
    the rating trajectory above (don't merge into one query: different
    denominators)."""
    return duck_conn.execute("""
        SELECT g.year, AVG(m.cpl) AS acpl, COUNT(DISTINCT m.game_id) AS n_games
        FROM db.moves m JOIN db.games g ON g.id = m.game_id
        WHERE m.is_player_move=1 AND m.cpl IS NOT NULL AND g.year IS NOT NULL
        GROUP BY g.year ORDER BY g.year
    """).fetchdf()


def get_win_rate_by_color(duck_conn):
    return duck_conn.execute("""
        SELECT player_color,
               COUNT(*) AS n,
               100.0 * SUM(CASE WHEN outcome_for_player='win' THEN 1 ELSE 0 END) / COUNT(*) AS win_pct,
               100.0 * SUM(CASE WHEN outcome_for_player='draw' THEN 1 ELSE 0 END) / COUNT(*) AS draw_pct
        FROM db.games WHERE outcome_for_player IS NOT NULL
        GROUP BY player_color
    """).fetchdf()
