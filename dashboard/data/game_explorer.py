"""Badges, drama scoring, Game Explorer table, and the per-game detail
query. These stay together: get_game_badges and get_game_explorer_table
depend on get_lead_changes and on the comeback/giant-killing thresholds
in roughly the order they appear below.
"""
import pandas as pd

from ._shared import (
    GIANT_KILLING_UPSET_THRESHOLD, COMEBACK_WP_THRESHOLD,
)

# Story-worthiness badge thresholds (Build Order step 4) -- each checked
# against the real analyzed dataset (179 games) before picking a cutoff,
# not guessed. See the plan / PROJECT_BRIEF.md for the full distributions.
BLUNDER_FEST_THRESHOLD = 4       # combined (both sides) blunders -- 35 games
BRILLIANT_FIND_THRESHOLD = 2     # is_brilliant_candidate count in one game -- 34 games
NAIL_BITER_THRESHOLD = 8         # lead changes (player win-prob crossing 50%) -- 45 games


def get_lead_changes(duck_conn):
    """Per-game count of how many times the player's win-probability
    crosses 50% -- the nail-biter badge's input. Same POV-flip
    comebacks.py already established (player_wp = win_prob_before if
    is_player_move else 1-win_prob_before), walked in ply order per game."""
    rows = duck_conn.execute("""
        SELECT game_id, ply, is_player_move, win_prob_before FROM db.moves
        WHERE win_prob_before IS NOT NULL ORDER BY game_id, ply
    """).fetchall()
    lead_changes = {}
    cur_game = None
    prev_sign = None
    changes = 0
    for game_id, _ply, is_player_move, wp in rows:
        if game_id != cur_game:
            if cur_game is not None:
                lead_changes[cur_game] = changes
            cur_game = game_id
            prev_sign = None
            changes = 0
        player_wp = wp if is_player_move else 1 - wp
        sign = player_wp > 0.5
        if prev_sign is not None and sign != prev_sign:
            changes += 1
        prev_sign = sign
    if cur_game is not None:
        lead_changes[cur_game] = changes
    return pd.DataFrame(list(lead_changes.items()), columns=["game_id", "lead_changes"])


def get_game_badges(duck_conn):
    """One row per ALL games (not just analyzed ones) -- giant-killing is
    board-derived and applies database-wide; the other 4 badges are
    engine-derived and simply come out False for the ~28,459 unanalyzed
    games (LEFT JOINed, not used as the base population -- an earlier
    version of this function started from the analyzed-only comeback
    query and silently lost all but 0 of the 228 real giant-killing
    games as a result; this is the fix).

    All five badge metrics are computed in one DuckDB query using a LAG
    window function for lead changes, replacing five separate SQLITE_SCANs
    + a Python loop. Saves ~600ms on a 32k-game database. get_lead_changes
    is kept as a public function for callers that need the per-game df."""
    df = duck_conn.execute(f"""
        WITH move_stats AS (
            SELECT
                game_id,
                CASE WHEN is_player_move THEN win_prob_before
                     ELSE 1 - win_prob_before END                               AS player_wp,
                LAG(CASE WHEN is_player_move THEN win_prob_before
                         ELSE 1 - win_prob_before END)
                    OVER (PARTITION BY game_id ORDER BY ply)                    AS prev_player_wp,
                CASE WHEN classification = 'blunder' THEN 1 ELSE 0 END         AS is_blunder,
                CAST(is_brilliant_candidate AS INTEGER)                         AS is_brilliant
            FROM db.moves
        ),
        per_game AS (
            SELECT
                game_id,
                SUM(CASE WHEN prev_player_wp IS NOT NULL
                          AND (player_wp > 0.5) != (prev_player_wp > 0.5)
                         THEN 1 ELSE 0 END)                                     AS lead_changes,
                SUM(is_blunder)                                                 AS n_blunders,
                SUM(is_brilliant)                                               AS n_brilliant,
                MIN(CASE WHEN player_wp IS NOT NULL THEN player_wp END)         AS min_player_wp
            FROM move_stats
            GROUP BY game_id
        )
        SELECT g.id AS game_id, p.lead_changes, p.n_blunders, p.n_brilliant,
               p.min_player_wp, g.outcome_for_player, g.rating_diff
        FROM db.games g LEFT JOIN per_game p ON p.game_id = g.id
    """).fetchdf()

    df["lead_changes"] = df["lead_changes"].fillna(0).astype(int)
    df["n_blunders"]   = df["n_blunders"].fillna(0).astype(int)
    df["n_brilliant"]  = df["n_brilliant"].fillna(0).astype(int)

    df["is_comeback"] = (
        df["min_player_wp"].notna() &
        (df["min_player_wp"] <= COMEBACK_WP_THRESHOLD) &
        df["outcome_for_player"].isin(["win", "draw"]))
    df["is_giant_killing"] = (
        df["rating_diff"].notna() &
        (df["rating_diff"] <= GIANT_KILLING_UPSET_THRESHOLD) &
        (df["outcome_for_player"] == "win"))
    df["is_blunder_fest"]   = df.n_blunders  >= BLUNDER_FEST_THRESHOLD
    df["is_brilliant_find"] = df.n_brilliant >= BRILLIANT_FIND_THRESHOLD
    df["is_nail_biter"]     = df.lead_changes >= NAIL_BITER_THRESHOLD

    badge_cols = ["is_comeback", "is_giant_killing", "is_blunder_fest", "is_brilliant_find", "is_nail_biter"]
    df["badge_count"] = df[badge_cols].sum(axis=1)
    df["drama_score"] = df.badge_count * 100 + df.n_blunders + df.lead_changes
    return df.drop(columns=["outcome_for_player", "rating_diff", "min_player_wp"])


def get_game_explorer_table(duck_conn):
    """Joins game_badges with the header info the Game Explorer table
    needs to display/filter on (date, opponent, color, result, time
    control, opening) -- one row per game with badges, ready to filter/sort."""
    badges = get_game_badges(duck_conn)
    headers = duck_conn.execute("""
        SELECT id AS game_id, utc_date, opponent_name, opponent_rating, player_color,
               outcome_for_player, time_control_category, opening_family, rating_diff
        FROM db.games
    """).fetchdf()
    return headers.merge(badges, on="game_id", how="inner").sort_values("drama_score", ascending=False)


def get_game_detail(duck_conn, game_id):
    """Everything the per-game view needs: header info, the full move
    list (san, classification, cpl, sharpness, fen_before, is_brilliant_candidate,
    is_puzzle_trigger), and the game_end_type for the narrative's closing line."""
    header = duck_conn.execute("""
        SELECT id AS game_id, utc_date, opponent_name, opponent_rating, player_rating,
               player_color, outcome_for_player, time_control_category, opening_family,
               rating_diff, game_end_type, analysis_status, last_analyzed_ply
        FROM db.games WHERE id = ?
    """, [game_id]).fetchdf().iloc[0]
    moves = duck_conn.execute("""
        SELECT ply, san, is_player_move, classification, cpl, sharpness,
               is_brilliant_candidate, is_puzzle_trigger, fen_before,
               win_prob_before, win_prob_after
        FROM db.moves WHERE game_id = ? ORDER BY ply
    """, [game_id]).fetchdf()
    return header, moves
