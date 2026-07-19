"""Favorite-vs-underdog rating-bucket comparison and clock-pressure
crosses (roadmap §15 unit #3, 2026-07-10) -- one of eight topic modules
split out of the former dashboard/data/patterns.py.

Reuses matchups.get_color_performance_by_rating's config-driven 3-way
underdog/even/favorite bucketing of rating_diff -- NOT _shared.py's
GIANT_KILLING_UPSET_THRESHOLD/GIANT_KILLING_COLLAPSE_THRESHOLD (+-300),
which are reserved for the existing rare-extreme "giant-killing"
narrative already fully built out in matchups_view.py and would produce
a tiny, mismatched-purpose sample here. Kept in THIS module (not
matchups.py) so all three axes below (win/ACPL, clock pressure,
openings) share one rating-bucket CASE fragment and one config read --
matchups.py's own rating-bucket functions are a different, narrower
analysis (color-adjusted win rate, rare-extreme counts) that don't need
any of this module's per-move/per-opening machinery.
"""
import pandas as pd

from connections import get_config

from .._shared import TIME_PRESSURE_BUCKETS, bucket_acpl_blunder_rate


def _rating_bucket_case_sql(cfg, column):
    """SQL CASE fragment bucketing *column* (a rating_diff expression,
    e.g. "g.rating_diff") into 'underdog'/'even'/'favorite' using the
    same config thresholds get_color_performance_by_rating uses."""
    buckets = cfg["analytics"]["rating_diff_buckets"]
    underdog_max, favorite_min = buckets["underdog_max"], buckets["favorite_min"]
    return (f"CASE WHEN {column} <= {underdog_max} THEN 'underdog' "
            f"WHEN {column} >= {favorite_min} THEN 'favorite' ELSE 'even' END")


_RATING_BUCKET_ORDER = ["underdog", "even", "favorite"]


def get_favorite_underdog_performance(duck_conn, config_path=None):
    """Win rate and ACPL split by the underdog/even/favorite rating_diff
    bucket -- same combined-query shape as get_castling_performance (one
    per-game DuckDB scan produces both the outcome flag and the weighted
    ACPL inputs, instead of two separate scans). Returns (win_df, acpl_df):
    win_df columns bucket, n_games, win_pct; acpl_df columns bucket,
    n_games, n_moves, acpl (weighted by each game's own analyzed-move
    count, same weighting as get_castling_performance's acpl_summary)."""
    cfg = get_config(config_path)
    bucket_sql = _rating_bucket_case_sql(cfg, "g.rating_diff")

    df = duck_conn.execute(f"""
        SELECT g.id AS game_id, g.outcome_for_player,
               {bucket_sql} AS rating_bucket,
               AVG(CASE WHEN m.is_player_move=1 AND m.cpl IS NOT NULL THEN m.cpl END) AS mean_cpl,
               COUNT(CASE WHEN m.is_player_move=1 AND m.cpl IS NOT NULL THEN 1 END)   AS n_cpl_moves
        FROM db.games g JOIN db.moves m ON m.game_id = g.id
        WHERE g.rating_diff IS NOT NULL AND g.outcome_for_player IS NOT NULL
        GROUP BY g.id, g.outcome_for_player, g.rating_diff
    """).fetchdf()

    win_rows = []
    for label in _RATING_BUCKET_ORDER:
        sub = df[df.rating_bucket == label]
        if len(sub):
            win_rows.append((label, len(sub), 100.0 * (sub.outcome_for_player == "win").sum() / len(sub)))
    win_df = pd.DataFrame(win_rows, columns=["bucket", "n_games", "win_pct"])

    acpl_rows = []
    for label in _RATING_BUCKET_ORDER:
        sub = df[(df.rating_bucket == label) & (df.n_cpl_moves > 0)]
        if len(sub):
            total_moves = int(sub.n_cpl_moves.sum())
            weighted_acpl = (sub.mean_cpl * sub.n_cpl_moves).sum() / total_moves
            acpl_rows.append((label, len(sub), total_moves, weighted_acpl))
    acpl_df = pd.DataFrame(acpl_rows, columns=["bucket", "n_games", "n_moves", "acpl"])
    return win_df, acpl_df


def get_clock_pressure_by_rating_bucket(duck_conn, config_path=None):
    """Clock-pressure (TIME_PRESSURE_BUCKETS) ACPL/blunder-rate crossed
    with the underdog/even/favorite rating bucket -- one per-move DuckDB
    fetch (same filter shape as get_blunder_rate_by_time_pressure, plus
    the rating_bucket column), then bucket_acpl_blunder_rate is reused
    per rating_bucket subset and the results concatenated, rather than
    hand-restating TIME_PRESSURE_BUCKETS' boundaries as a second SQL CASE
    fragment (that helper is the single source of truth for those cuts).

    Returns a long-form DataFrame: rating_bucket, time_bucket, n_moves,
    acpl, blunder_rate."""
    cfg = get_config(config_path)
    bucket_sql = _rating_bucket_case_sql(cfg, "g.rating_diff")

    df = duck_conn.execute(f"""
        SELECT {bucket_sql} AS rating_bucket, m.cpl, m.classification,
               CAST(m.clock_seconds AS DOUBLE) / g.base_seconds AS time_fraction
        FROM db.moves m JOIN db.games g ON g.id = m.game_id
        WHERE m.is_player_move=1 AND m.cpl IS NOT NULL
          AND m.clock_seconds IS NOT NULL AND g.base_seconds IS NOT NULL AND g.base_seconds > 0
          AND g.rating_diff IS NOT NULL
    """).fetchdf()

    frames = []
    for label in _RATING_BUCKET_ORDER:
        sub = df[df.rating_bucket == label]
        bucketed = bucket_acpl_blunder_rate(sub, "time_fraction", TIME_PRESSURE_BUCKETS)
        if not bucketed.empty:
            bucketed = bucketed.rename(columns={"bucket": "time_bucket"})
            bucketed.insert(0, "rating_bucket", label)
            frames.append(bucketed)
    if not frames:
        return pd.DataFrame(columns=["rating_bucket", "time_bucket", "n_moves", "acpl", "blunder_rate"])
    return pd.concat(frames, ignore_index=True)


def get_clock_pressure_by_outcome(duck_conn):
    """Clock-pressure (TIME_PRESSURE_BUCKETS) ACPL/blunder-rate crossed
    with game outcome -- same shape as get_clock_pressure_by_rating_bucket,
    but the crossed dimension is outcome_for_player instead of the rating
    bucket, restricted to 'win'/'loss' (draws excluded: this is a two-pane
    won-vs-lost comparison, and a draw doesn't fit either pane). Reuses
    bucket_acpl_blunder_rate the same way, once per outcome subset.

    Returns a long-form DataFrame: outcome, time_bucket, n_moves, acpl,
    blunder_rate."""
    df = duck_conn.execute("""
        SELECT g.outcome_for_player, m.cpl, m.classification,
               CAST(m.clock_seconds AS DOUBLE) / g.base_seconds AS time_fraction
        FROM db.moves m JOIN db.games g ON g.id = m.game_id
        WHERE m.is_player_move=1 AND m.cpl IS NOT NULL
          AND m.clock_seconds IS NOT NULL AND g.base_seconds IS NOT NULL AND g.base_seconds > 0
          AND g.outcome_for_player IN ('win', 'loss')
    """).fetchdf()

    frames = []
    for label in ["win", "loss"]:
        sub = df[df.outcome_for_player == label]
        bucketed = bucket_acpl_blunder_rate(sub, "time_fraction", TIME_PRESSURE_BUCKETS)
        if not bucketed.empty:
            bucketed = bucketed.rename(columns={"bucket": "time_bucket"})
            bucketed.insert(0, "outcome", label)
            frames.append(bucketed)
    if not frames:
        return pd.DataFrame(columns=["outcome", "time_bucket", "n_moves", "acpl", "blunder_rate"])
    return pd.concat(frames, ignore_index=True)


def get_clock_pressure_by_color(duck_conn):
    """Clock-pressure (TIME_PRESSURE_BUCKETS) ACPL/blunder-rate crossed
    with player_color -- same shape as get_clock_pressure_by_rating_bucket,
    but the crossed dimension is which color was played. Both 'white' and
    'black' are always meaningful (no filtering needed beyond the base
    per-move WHERE), unlike the outcome variant's win/loss-only restriction.
    Reuses bucket_acpl_blunder_rate once per color subset.

    Returns a long-form DataFrame: color, time_bucket, n_moves, acpl,
    blunder_rate."""
    df = duck_conn.execute("""
        SELECT g.player_color, m.cpl, m.classification,
               CAST(m.clock_seconds AS DOUBLE) / g.base_seconds AS time_fraction
        FROM db.moves m JOIN db.games g ON g.id = m.game_id
        WHERE m.is_player_move=1 AND m.cpl IS NOT NULL
          AND m.clock_seconds IS NOT NULL AND g.base_seconds IS NOT NULL AND g.base_seconds > 0
    """).fetchdf()

    frames = []
    for label in ["white", "black"]:
        sub = df[df.player_color == label]
        bucketed = bucket_acpl_blunder_rate(sub, "time_fraction", TIME_PRESSURE_BUCKETS)
        if not bucketed.empty:
            bucketed = bucketed.rename(columns={"bucket": "time_bucket"})
            bucketed.insert(0, "color", label)
            frames.append(bucketed)
    if not frames:
        return pd.DataFrame(columns=["color", "time_bucket", "n_moves", "acpl", "blunder_rate"])
    return pd.concat(frames, ignore_index=True)


def get_clock_pressure_by_opening(duck_conn, config_path=None, top_n=None):
    """Clock-pressure (TIME_PRESSURE_BUCKETS) ACPL/blunder-rate crossed
    with opening_family -- same shape as get_clock_pressure_by_rating_bucket,
    but the crossed dimension is opening family, capped to the top_n
    opening families (default cfg["analytics"]["top_n_openings"], same
    config key get_openings_by_rating_bucket uses) by total analyzed-move
    count. Reuses bucket_acpl_blunder_rate once per family subset.

    Unlike get_openings_by_rating_bucket, this deliberately does NOT add a
    "family must be present in every bucket" completeness filter --
    TIME_PRESSURE_BUCKETS has 5 buckets total, but the view layer only ever
    compares 2 of them (the two most contrastive extremes: "critical (<5%)"
    vs. "plenty (60-100%)"), so completeness-checking happens at the view
    layer against just those two buckets, not all 5. Pre-filtering to
    "present in all 5" here would be needlessly strict and would drop
    openings that are fine for the actual 2-bucket comparison being
    rendered.

    Returns a long-form DataFrame: opening_family, time_bucket, n_moves,
    acpl, blunder_rate -- sorted by (opening_family, time_bucket)."""
    cfg = get_config(config_path)
    top_n = top_n or cfg["analytics"]["top_n_openings"]

    df = duck_conn.execute("""
        SELECT g.opening_family, m.cpl, m.classification,
               CAST(m.clock_seconds AS DOUBLE) / g.base_seconds AS time_fraction
        FROM db.moves m JOIN db.games g ON g.id = m.game_id
        WHERE m.is_player_move=1 AND m.cpl IS NOT NULL
          AND m.clock_seconds IS NOT NULL AND g.base_seconds IS NOT NULL AND g.base_seconds > 0
          AND g.opening_family IS NOT NULL
    """).fetchdf()
    cols = ["opening_family", "time_bucket", "n_moves", "acpl", "blunder_rate"]
    if df.empty:
        return pd.DataFrame(columns=cols)

    counts = df.groupby("opening_family").size().sort_values(ascending=False)
    top_families = set(counts.head(top_n).index)
    df = df[df.opening_family.isin(top_families)]
    if df.empty:
        return pd.DataFrame(columns=cols)

    frames = []
    for label in sorted(top_families):
        sub = df[df.opening_family == label]
        bucketed = bucket_acpl_blunder_rate(sub, "time_fraction", TIME_PRESSURE_BUCKETS)
        if not bucketed.empty:
            bucketed = bucketed.rename(columns={"bucket": "time_bucket"})
            bucketed.insert(0, "opening_family", label)
            frames.append(bucketed)
    if not frames:
        return pd.DataFrame(columns=cols)
    return pd.concat(frames, ignore_index=True).sort_values(
        ["opening_family", "time_bucket"]).reset_index(drop=True)


def get_openings_by_rating_bucket(duck_conn, config_path=None, top_n=None):
    """Win rate by (rating_bucket, opening_family) -- mirrors
    openings.get_openings_table's GROUP BY shape but crosses opening_family
    with the underdog/even/favorite rating bucket instead of player_color.
    ACPL deliberately omitted: a full ACPL join (sqlite_conn, per
    (opening_family, rating_bucket) pair, same two-query shape
    get_openings_table uses for its own ACPL side) is a reasonable follow-
    up, but win_pct-by-opening is already a complete "Openings" axis for
    the favorite/underdog overlay this feeds, and the analyzed-move
    population is thin enough (~2.9% of games database-wide, see this
    module's board-position-character section above) that crossing it with
    BOTH opening_family and a 3-way rating bucket would leave most cells
    empty.

    Capped to the top_n opening_families by TOTAL game count across all
    rating buckets (top_n_openings if not given), then further restricted
    to opening_families that have a qualifying (>= min_games_per_group
    games) row in EVERY rating_bucket actually present in the data -- so
    an overlay chart comparing buckets never shows a bar for one bucket
    with nothing in the other bucket(s) to compare it against.

    Returns rating_bucket, opening_family, n_games, win_pct."""
    cfg = get_config(config_path)
    bucket_sql = _rating_bucket_case_sql(cfg, "rating_diff")
    top_n = top_n or cfg["analytics"]["top_n_openings"]
    min_games = cfg["analytics"]["min_games_per_group"]

    df = duck_conn.execute(f"""
        SELECT opening_family, {bucket_sql} AS rating_bucket, COUNT(*) AS n_games,
               100.0 * SUM(CASE WHEN outcome_for_player='win' THEN 1 ELSE 0 END) / COUNT(*) AS win_pct
        FROM db.games
        WHERE opening_family IS NOT NULL AND outcome_for_player IS NOT NULL AND rating_diff IS NOT NULL
        GROUP BY opening_family, rating_bucket
        HAVING COUNT(*) >= ?
    """, [min_games]).fetchdf()
    cols = ["rating_bucket", "opening_family", "n_games", "win_pct"]
    if df.empty:
        return pd.DataFrame(columns=cols)

    totals = df.groupby("opening_family")["n_games"].sum().sort_values(ascending=False)
    top_families = set(totals.head(top_n).index)
    df = df[df.opening_family.isin(top_families)]
    if df.empty:
        return pd.DataFrame(columns=cols)

    n_buckets_present = df.rating_bucket.nunique()
    counts_per_family = df.groupby("opening_family")["rating_bucket"].nunique()
    complete_families = counts_per_family[counts_per_family == n_buckets_present].index
    df = df[df.opening_family.isin(complete_families)]

    return df[cols].sort_values(["opening_family", "rating_bucket"]).reset_index(drop=True)
