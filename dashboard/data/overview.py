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
    denominators).

    Also returns n_total_games and coverage_pct (n_games / n_total_games)
    per year: analysis coverage is NOT spread evenly across calendar time
    (ingest.py bumps freshly-synced games to the front of the analysis
    queue -- see game_endings.py's resignation-cause docstring for the
    same mechanism), so an early year with a handful of analyzed games out
    of thousands total reads, on the bare acpl-by-year line, as an
    equally-confident data point as a heavily-analyzed recent year. The
    view layer uses coverage_pct to disclaim this rather than hide it --
    same "explained, not hidden" posture as get_resignation_loss_causes's
    not_analyzed bucket."""
    return duck_conn.execute("""
        WITH totals AS (
            SELECT year, COUNT(*) AS n_total_games
            FROM db.games WHERE year IS NOT NULL
            GROUP BY year
        )
        SELECT g.year, AVG(m.cpl) AS acpl, COUNT(DISTINCT m.game_id) AS n_games,
               t.n_total_games, 100.0 * COUNT(DISTINCT m.game_id) / t.n_total_games AS coverage_pct
        FROM db.moves m JOIN db.games g ON g.id = m.game_id
        JOIN totals t ON t.year = g.year
        WHERE m.is_player_move=1 AND m.cpl IS NOT NULL AND g.year IS NOT NULL
        GROUP BY g.year, t.n_total_games ORDER BY g.year
    """).fetchdf()


def get_progress_by_month(duck_conn):
    """Monthly ACPL and win rate — shows improvement over time.

    Only months with ≥3 analyzed games are included to avoid single-game spikes.
    ACPL population: analyzed games only (engine eval required).
    Win rate population: all games in months that have ≥3 analyzed ones.

    Also returns n_total_games and coverage_pct per month, same skew-
    disclosure reasoning as get_acpl_trajectory above -- recent months are
    typically analyzed far more completely than older ones."""
    return duck_conn.execute("""
        WITH monthly_totals AS (
            SELECT LEFT(utc_date, 7) AS period, COUNT(*) AS n_total_games
            FROM db.games
            WHERE utc_date IS NOT NULL AND LENGTH(utc_date) >= 7
            GROUP BY period
        ),
        monthly_acpl AS (
            SELECT LEFT(g.utc_date, 7)           AS period,
                   AVG(m.cpl)                    AS acpl,
                   COUNT(DISTINCT m.game_id)      AS n_analyzed
            FROM db.moves m
            JOIN db.games g ON g.id = m.game_id
            WHERE m.is_player_move = 1
              AND m.cpl IS NOT NULL
              AND g.utc_date IS NOT NULL
              AND LENGTH(g.utc_date) >= 7
            GROUP BY period
            HAVING COUNT(DISTINCT m.game_id) >= 3
        ),
        monthly_wins AS (
            SELECT LEFT(utc_date, 7) AS period,
                   100.0 * SUM(CASE WHEN outcome_for_player = 'win' THEN 1 ELSE 0 END)
                       / COUNT(*) AS win_pct
            FROM db.games
            WHERE utc_date IS NOT NULL AND LENGTH(utc_date) >= 7
              AND outcome_for_player IS NOT NULL
            GROUP BY period
        )
        SELECT a.period, a.acpl, w.win_pct, a.n_analyzed,
               t.n_total_games, 100.0 * a.n_analyzed / t.n_total_games AS coverage_pct
        FROM monthly_acpl a
        LEFT JOIN monthly_wins w ON w.period = a.period
        JOIN monthly_totals t ON t.period = a.period
        ORDER BY a.period
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


def get_rating_snapshot(duck_conn):
    """Current rating (most recent game's player_rating) and all-time peak.
    Board-derived, same population as get_rating_trajectory -- no analysis
    needed."""
    row = duck_conn.execute("""
        SELECT
            (SELECT player_rating FROM db.games
             WHERE player_rating IS NOT NULL
             ORDER BY utc_date DESC, utc_time DESC LIMIT 1) AS current_rating,
            (SELECT MAX(player_rating) FROM db.games) AS peak_rating
    """).fetchone()
    return {"current_rating": row[0], "peak_rating": row[1]}


def get_current_streak(duck_conn):
    """Current ACTIVE streak (consecutive most-recent games sharing the same
    outcome) -- distinct from achievements.py's _longest_win_streak_end,
    which computes the longest-EVER streak for unlock checks. All games, not
    analyzed-only: outcome_for_player needs no engine analysis."""
    df = duck_conn.execute("""
        SELECT outcome_for_player FROM db.games
        WHERE outcome_for_player IS NOT NULL
        ORDER BY utc_date DESC, utc_time DESC
    """).fetchdf()
    if len(df) == 0:
        return {"outcome": None, "length": 0}
    outcomes = df["outcome_for_player"].tolist()
    current = outcomes[0]
    length = 0
    for outcome in outcomes:
        if outcome != current:
            break
        length += 1
    return {"outcome": current, "length": length}


def get_recent_form_snapshot(duck_conn, n=5):
    """Last n games for Overview's recent-form ticker. All board-derived
    (result/opponent/date/rating-change), no analysis dependency."""
    return duck_conn.execute("""
        SELECT outcome_for_player, opponent_name, utc_date, player_rating_change
        FROM db.games
        ORDER BY utc_date DESC, utc_time DESC
        LIMIT ?
    """, [n]).fetchdf()
