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
    games as a result; this is the fix)."""
    all_games = duck_conn.execute("SELECT id AS game_id FROM db.games").fetchdf()

    lead_changes_df = get_lead_changes(duck_conn)

    blunders_df = duck_conn.execute("""
        SELECT game_id, COUNT(*) AS n_blunders FROM db.moves
        WHERE classification='blunder' GROUP BY game_id
    """).fetchdf()

    brilliant_df = duck_conn.execute("""
        SELECT game_id, COUNT(*) AS n_brilliant FROM db.moves
        WHERE is_brilliant_candidate=1 GROUP BY game_id
    """).fetchdf()

    comeback_df = duck_conn.execute("""
        SELECT m.game_id,
               MIN(CASE WHEN m.is_player_move=1 THEN m.win_prob_before
                        ELSE 1 - m.win_prob_before END) AS min_player_wp,
               g.outcome_for_player
        FROM db.moves m JOIN db.games g ON g.id = m.game_id
        WHERE m.win_prob_before IS NOT NULL
        GROUP BY m.game_id, g.outcome_for_player
    """).fetchdf()
    comeback_df["is_comeback"] = (
        (comeback_df.min_player_wp <= COMEBACK_WP_THRESHOLD) &
        comeback_df.outcome_for_player.isin(["win", "draw"]))

    df = all_games.merge(comeback_df[["game_id", "is_comeback"]], on="game_id", how="left")
    df = df.merge(lead_changes_df, on="game_id", how="left")
    df = df.merge(blunders_df, on="game_id", how="left")
    df = df.merge(brilliant_df, on="game_id", how="left")
    df["is_comeback"] = df["is_comeback"].fillna(False)
    df["lead_changes"] = df["lead_changes"].fillna(0)
    df["n_blunders"] = df["n_blunders"].fillna(0)
    df["n_brilliant"] = df["n_brilliant"].fillna(0)

    df["is_blunder_fest"] = df.n_blunders >= BLUNDER_FEST_THRESHOLD
    df["is_brilliant_find"] = df.n_brilliant >= BRILLIANT_FIND_THRESHOLD
    df["is_nail_biter"] = df.lead_changes >= NAIL_BITER_THRESHOLD

    giant_killing_ids = set(duck_conn.execute(f"""
        SELECT id FROM db.games
        WHERE rating_diff <= {GIANT_KILLING_UPSET_THRESHOLD} AND outcome_for_player='win'
    """).fetchdf()["id"])
    df["is_giant_killing"] = df.game_id.isin(giant_killing_ids)

    badge_cols = ["is_comeback", "is_giant_killing", "is_blunder_fest", "is_brilliant_find", "is_nail_biter"]
    df["badge_count"] = df[badge_cols].sum(axis=1)
    df["drama_score"] = df.badge_count * 100 + df.n_blunders + df.lead_changes
    return df


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
