"""Points ledger: the win-probability-curve decomposition and the
Points-page aggregation queries built on top of it -- one of two topic
modules split out of the former dashboard/data/points.py.

Every fully analyzed game already stores a complete win-probability curve
(win_prob_before on every move, mover's POV -- flipped to the player's
POV here the same way get_comeback_collapse_counts does). Until this
module the only consumer of that curve was loss-only decisive-moment
profiling (patterns.get_decisive_moments); this generalizes it into a
points ledger: for each game, how many points did the position promise
at its best, and where did the difference go?

Each game lands in exactly one bucket (priority order):
- failed_conversion: reached a winning position (player wp >= WINNING_WP)
  and didn't win. Leak = peak wp minus points actually scored.
- missed_swindle: was lost (wp <= LOST_WP), was then handed a real chance
  (wp back >= SWINDLE_CHANCE_WP), and still lost. Leak = that chance.
- failed_hold: still holding an even game into the middlegame
  (wp >= EVEN_WP at or after move HOLD_EVEN_MIN_MOVE), never winning,
  and lost. Leak = the half point an even position is worth.
- none: converted wins, even draws, and losses that were simply lost.

Threshold lineage: the top CONVERSION_BANDS edge (0.90) is _shared's
COLLAPSE_WP_THRESHOLD -- the 90%+ failed conversions here are exactly
the Matchups tab's "collapses" population (cross-checked equal, 73/73,
on the real database), weighted by points instead of merely counted.

The SQL returns per-game primitives only; bucket assignment lives in
classify_points_ledger (pure pandas) so the thresholds stay inspectable
in one place and the expensive scan is classification-independent.
Measured 2026-07-05 on the real 2.3M-row moves table: 0.78s -- fine for
a single @st.cache_data'd call, no materialized cache needed.
"""
import pandas as pd

from connections import get_config
from confidence import confidence_tier, default_thresholds

from .._shared import TIME_PRESSURE_BUCKETS

WINNING_WP = 0.70          # genuinely winning -- conversion duty begins
LOST_WP = 0.25             # position lost
SWINDLE_CHANCE_WP = 0.50   # recovered to at least even = a real chance
EVEN_WP = 0.45             # still holding the balance
HOLD_EVEN_MIN_MOVE = 15    # even at/after this move = "held into the middlegame"

# (label, lo, hi) on peak_wp for failed-conversion rows. 0.90 ==
# _shared.COLLAPSE_WP_THRESHOLD -- keep aligned.
CONVERSION_BANDS = [
    ("clearly better (70-80%)", 0.70, 0.80),
    ("winning (80-90%)", 0.80, 0.90),
    ("completely winning (90%+)", 0.90, 1.01),
]

_POINTS = {"win": 1.0, "draw": 0.5, "loss": 0.0}

BUCKET_LABEL = {
    "failed_conversion": "Failed conversion",
    "missed_swindle": "Missed swindle",
    "failed_hold": "Failed hold",
    "none": "No leak",
}

def get_points_ledger(duck_conn):
    """One row per fully analyzed game with win-prob data: the per-game
    curve primitives that classify_points_ledger buckets.

    Only analysis_status='done' games qualify -- a partially analyzed
    curve could cut off before the collapse/recovery it would have shown,
    misclassifying the game (get_comeback_collapse_counts doesn't filter,
    but it only counts extremes; this module does points accounting).

    first_winning_ply (alongside the pre-existing first_winning_move) is
    the ply-level twin get_failed_conversion_causes needs to scope its
    own per-move self-join to "after the position first became winning"
    -- computed once here, alongside peak_wp, rather than re-derived by
    a second query re-scanning the same wp curve.
    """
    return duck_conn.execute(f"""
        WITH wp AS (
            SELECT m.game_id, m.ply, m.move_number,
                   CASE WHEN m.is_player_move = 1 THEN m.win_prob_before
                        ELSE 1 - m.win_prob_before END AS player_wp,
                   -- player's clock only: clock_seconds on an opponent row
                   -- is the opponent's clock, meaningless for "how much
                   -- time did YOU have when you got winning".
                   CASE WHEN m.is_player_move = 1
                             AND g.base_seconds IS NOT NULL AND g.base_seconds > 0
                             AND m.clock_seconds IS NOT NULL
                        THEN CAST(m.clock_seconds AS DOUBLE) / g.base_seconds
                   END AS clock_fraction
            FROM db.moves m
            JOIN db.games g ON g.id = m.game_id
            WHERE m.win_prob_before IS NOT NULL
              AND g.outcome_for_player IS NOT NULL
              AND g.analysis_status = 'done'
        ),
        runs AS (
            SELECT *,
                   MIN(player_wp) OVER (
                       PARTITION BY game_id ORDER BY ply
                       ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
                   ) AS prior_min_wp
            FROM wp
        ),
        per_game AS (
            SELECT game_id,
                   MAX(player_wp) AS peak_wp,
                   MIN(player_wp) AS trough_wp,
                   MIN(CASE WHEN player_wp >= {WINNING_WP} THEN move_number END)
                       AS first_winning_move,
                   MIN(CASE WHEN player_wp >= {WINNING_WP} THEN ply END)
                       AS first_winning_ply,
                   arg_min(clock_fraction, ply)
                       FILTER (WHERE player_wp >= {WINNING_WP}
                               AND clock_fraction IS NOT NULL)
                       AS winning_clock_fraction,
                   MAX(CASE WHEN prior_min_wp <= {LOST_WP} THEN player_wp END)
                       AS post_lost_peak_wp,
                   MAX(CASE WHEN move_number >= {HOLD_EVEN_MIN_MOVE}
                                 AND player_wp >= {EVEN_WP}
                            THEN 1 ELSE 0 END) AS held_even_late
            FROM runs
            GROUP BY game_id
        )
        SELECT p.*, g.outcome_for_player, LEFT(g.utc_date, 7) AS period,
               g.time_control_category, g.opening_family, g.player_color,
               g.opponent_name, g.utc_date, g.site
        FROM per_game p JOIN db.games g ON g.id = p.game_id
    """).fetchdf()


def _phase_of_move(move_number):
    """Same exclusive move-number partition as get_decisive_moments."""
    if pd.isna(move_number):
        return None
    if move_number <= 12:
        return "opening"
    if move_number <= 30:
        return "middlegame"
    return "endgame"


def _clock_bucket(fraction):
    if pd.isna(fraction):
        return "no clock data"
    for label, lo, hi in TIME_PRESSURE_BUCKETS:
        if lo <= fraction < hi:
            return label
    # clock_seconds can exceed base_seconds under increment -- more time
    # than the game started with is still "plenty".
    return TIME_PRESSURE_BUCKETS[-1][0]


def classify_points_ledger(ledger):
    """Adds points/bucket/leaked plus the failed-conversion detail
    dimensions (adv_band, conv_phase, conv_clock). Pure pandas, no I/O."""
    df = ledger.copy()
    if df.empty:
        for col in ("points", "leaked"):
            df[col] = pd.Series(dtype="float64")
        for col in ("bucket", "adv_band", "conv_phase", "conv_clock"):
            df[col] = pd.Series(dtype="object")
        return df

    df["points"] = df.outcome_for_player.map(_POINTS)
    conv = (df.peak_wp >= WINNING_WP) & (df.points < 1.0)
    swin = (~conv & (df.outcome_for_player == "loss")
            & (df.post_lost_peak_wp >= SWINDLE_CHANCE_WP))
    hold = (~conv & ~swin & (df.outcome_for_player == "loss")
            & (df.held_even_late == 1))

    df["bucket"] = "none"
    df.loc[hold, "bucket"] = "failed_hold"
    df.loc[swin, "bucket"] = "missed_swindle"
    df.loc[conv, "bucket"] = "failed_conversion"

    df["leaked"] = 0.0
    df.loc[hold, "leaked"] = 0.5
    df.loc[swin, "leaked"] = df.post_lost_peak_wp[swin]  # points are 0 in a loss
    df.loc[conv, "leaked"] = (df.peak_wp - df.points)[conv]

    df["adv_band"] = None
    for label, lo, hi in CONVERSION_BANDS:
        df.loc[conv & (df.peak_wp >= lo) & (df.peak_wp < hi), "adv_band"] = label
    df["conv_phase"] = None
    df.loc[conv, "conv_phase"] = df.first_winning_move[conv].map(_phase_of_move)
    df["conv_clock"] = None
    df.loc[conv, "conv_clock"] = df.winning_clock_fraction[conv].map(_clock_bucket)
    return df


def summarize_buckets(classified):
    """One row per leak bucket (excluding 'none'): n_games, leaked points."""
    leaks = classified[classified.bucket != "none"]
    if leaks.empty:
        return pd.DataFrame(columns=["bucket", "n_games", "leaked"])
    out = (leaks.groupby("bucket")
           .agg(n_games=("game_id", "size"), leaked=("leaked", "sum"))
           .reset_index()
           .sort_values("leaked", ascending=False, ignore_index=True))
    return out


def monthly_points(classified, min_games: int | None = None, config_path=None):
    """Per month: actual score vs. score with leaks recovered, both as
    raw point sums and per-game percentages (the chart plots the
    percentages -- monthly game volume varies by two orders of magnitude
    in real data, so raw sums mostly graph volume, not quality). month is
    a real datetime: the 'YYYY.MM' period strings LOOK numeric to plotly,
    which coerces them onto a fractional-year continuous axis (confirmed
    on the rendered chart, axis read 2018..2026). Months under min_games
    are dropped -- same single-game-noise guard as get_progress_by_month.
    min_games defaults to analytics.min_sample_size when not passed
    explicitly."""
    if min_games is None:
        min_games = get_config(config_path)["analytics"]["min_sample_size"]
    df = classified[classified.period.notna() & (classified.period != "")]
    if df.empty:
        return pd.DataFrame(columns=["period", "month", "n_games", "actual",
                                     "potential", "actual_pct", "potential_pct"])
    out = (df.groupby("period")
           .agg(n_games=("game_id", "size"), actual=("points", "sum"),
                leaked=("leaked", "sum"))
           .reset_index()
           .sort_values("period", ignore_index=True))
    out["potential"] = out.actual + out.leaked
    month_thresholds = default_thresholds(min_games)
    out = out[out.n_games.map(
        lambda n: confidence_tier(n, month_thresholds) != "insufficient")]
    out = out.drop(columns="leaked").reset_index(drop=True)
    out["actual_pct"] = 100.0 * out.actual / out.n_games
    out["potential_pct"] = 100.0 * out.potential / out.n_games
    out["month"] = pd.to_datetime(out.period, format="%Y.%m")
    return out


def conversion_breakdown(classified, dim):
    """Leaked points + game counts for failed conversions grouped by one
    of the detail dimensions: adv_band, conv_phase, or conv_clock.
    Ordered by the dimension's natural scale, not alphabetically."""
    order = {
        "adv_band": [label for label, _, _ in CONVERSION_BANDS],
        "conv_phase": ["opening", "middlegame", "endgame"],
        "conv_clock": [label for label, _, _ in TIME_PRESSURE_BUCKETS] + ["no clock data"],
    }[dim]
    conv = classified[classified.bucket == "failed_conversion"]
    if conv.empty:
        return pd.DataFrame(columns=[dim, "n_games", "leaked"])
    out = (conv.groupby(dim)
           .agg(n_games=("game_id", "size"), leaked=("leaked", "sum"))
           .reindex(order)
           .dropna(how="all")
           .reset_index(names=dim))
    out["n_games"] = out.n_games.astype(int)
    return out
