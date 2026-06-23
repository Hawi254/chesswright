"""Matchups and Opponents page queries."""
from _common import get_config

from ._shared import (
    GIANT_KILLING_UPSET_THRESHOLD, GIANT_KILLING_COLLAPSE_THRESHOLD,
    COMEBACK_WP_THRESHOLD, COLLAPSE_WP_THRESHOLD,
)


def get_win_rate_by_rating_diff(duck_conn, band_width=100, band_range=500):
    df = duck_conn.execute("""
        SELECT rating_diff, outcome_for_player FROM db.games
        WHERE rating_diff IS NOT NULL AND outcome_for_player IS NOT NULL
    """).fetchdf()

    def band_label(rating_diff):
        clamped = max(-band_range, min(band_range, rating_diff))
        return (clamped // band_width) * band_width

    df["band"] = df.rating_diff.apply(band_label)
    grouped = df.groupby("band").agg(
        n=("outcome_for_player", "size"),
        win_pct=("outcome_for_player", lambda s: 100.0 * (s == "win").sum() / len(s)),
    ).reset_index().sort_values("band")
    return grouped


def get_comeback_collapse_counts(duck_conn):
    per_game = duck_conn.execute("""
        SELECT m.game_id, g.outcome_for_player,
               MIN(CASE WHEN m.is_player_move=1 THEN m.win_prob_before
                        ELSE 1 - m.win_prob_before END) AS min_player_wp,
               MAX(CASE WHEN m.is_player_move=1 THEN m.win_prob_before
                        ELSE 1 - m.win_prob_before END) AS max_player_wp
        FROM db.moves m JOIN db.games g ON g.id = m.game_id
        WHERE m.win_prob_before IS NOT NULL
        GROUP BY m.game_id, g.outcome_for_player
    """).fetchdf()
    comebacks = per_game[(per_game.min_player_wp <= COMEBACK_WP_THRESHOLD) &
                          (per_game.outcome_for_player.isin(["win", "draw"]))]
    collapses = per_game[(per_game.max_player_wp >= COLLAPSE_WP_THRESHOLD) &
                          (per_game.outcome_for_player.isin(["loss", "draw"]))]
    return {"n_comebacks": len(comebacks), "n_collapses": len(collapses),
            "comeback_game_ids": comebacks.game_id.tolist(),
            "collapse_game_ids": collapses.game_id.tolist()}


def get_color_performance_by_rating(duck_conn, config_path=None):
    """Mirrors analysis/color_performance.py -- the rating-ADJUSTED color
    breakdown (White's ~4-5pp edge holds at every rating bucket). The
    Overview tab's raw win-rate-by-color doesn't control for rating, so
    a real color effect would be indistinguishable from "I'm rated higher
    when I happen to play White" without this cross-tab."""
    cfg = get_config(config_path)
    buckets = cfg["analytics"]["rating_diff_buckets"]
    underdog_max, favorite_min = buckets["underdog_max"], buckets["favorite_min"]
    df = duck_conn.execute(f"""
        SELECT player_color,
               CASE WHEN rating_diff <= {underdog_max} THEN 'underdog'
                    WHEN rating_diff >= {favorite_min} THEN 'favorite'
                    ELSE 'even' END AS rating_bucket,
               COUNT(*) AS n,
               100.0 * SUM(CASE WHEN outcome_for_player='win' THEN 1 ELSE 0 END) / COUNT(*) AS win_pct
        FROM db.games WHERE rating_diff IS NOT NULL AND outcome_for_player IS NOT NULL
        GROUP BY player_color, rating_bucket
    """).fetchdf()
    pivot = df.pivot(index="rating_bucket", columns="player_color", values="win_pct")
    return pivot.reindex(["underdog", "even", "favorite"])


def get_giant_killing_counts(duck_conn):
    """Mirrors analysis/giant_killing.py -- explicit counts (228 wins as
    a 300+ underdog, 466 losses as a 300+ favorite, from FINDINGS.md),
    distinct from the eval-based comeback/collapse counts already in the
    Matchups tab (this is rating-based, not win-probability-based)."""
    upsets = duck_conn.execute(f"""
        SELECT COUNT(*) FROM db.games
        WHERE rating_diff <= {GIANT_KILLING_UPSET_THRESHOLD} AND outcome_for_player='win'
    """).fetchone()[0]
    underdog_total = duck_conn.execute(f"""
        SELECT COUNT(*) FROM db.games WHERE rating_diff <= {GIANT_KILLING_UPSET_THRESHOLD}
        AND outcome_for_player IS NOT NULL
    """).fetchone()[0]
    collapses = duck_conn.execute(f"""
        SELECT COUNT(*) FROM db.games
        WHERE rating_diff >= {GIANT_KILLING_COLLAPSE_THRESHOLD} AND outcome_for_player='loss'
    """).fetchone()[0]
    favorite_total = duck_conn.execute(f"""
        SELECT COUNT(*) FROM db.games WHERE rating_diff >= {GIANT_KILLING_COLLAPSE_THRESHOLD}
        AND outcome_for_player IS NOT NULL
    """).fetchone()[0]
    return {"n_upsets": upsets, "n_underdog_games": underdog_total,
            "n_collapses": collapses, "n_favorite_games": favorite_total}


def get_nemesis_opponents(duck_conn, min_games=5):
    """Mirrors analysis/nemesis_opponents.py -- ranked by score% (win +
    0.5*draw, standard tournament scoring) so repeated draws aren't
    misread as losses. Real finding: 17.1% score against a specific
    41-game opponent, one of the largest single-opponent samples in the
    dataset -- never previously surfaced in the dashboard."""
    df = duck_conn.execute("""
        SELECT opponent_name,
               COUNT(*) AS n,
               SUM(CASE WHEN outcome_for_player='win' THEN 1 ELSE 0 END) AS wins,
               SUM(CASE WHEN outcome_for_player='draw' THEN 1 ELSE 0 END) AS draws,
               SUM(CASE WHEN outcome_for_player='loss' THEN 1 ELSE 0 END) AS losses
        FROM db.games
        WHERE opponent_name IS NOT NULL AND outcome_for_player IS NOT NULL
        GROUP BY opponent_name
        HAVING COUNT(*) >= ?
    """, [min_games]).fetchdf()
    df["score_pct"] = 100.0 * (df.wins + 0.5 * df.draws) / df.n
    return df
