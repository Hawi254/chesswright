"""Game Endings page queries."""


def get_game_end_type_breakdown(duck_conn):
    overall = duck_conn.execute("""
        SELECT game_end_type, COUNT(*) AS n FROM db.games GROUP BY game_end_type ORDER BY n DESC
    """).fetchdf()
    by_tc = duck_conn.execute("""
        SELECT time_control_category, game_end_type, COUNT(*) AS n
        FROM db.games WHERE time_control_category IS NOT NULL
        GROUP BY time_control_category, game_end_type
    """).fetchdf()
    pivot = by_tc.pivot_table(index="time_control_category", columns="game_end_type", values="n", fill_value=0)
    pivot_pct = pivot.div(pivot.sum(axis=1), axis=0) * 100.0
    return overall, pivot_pct
