""""Where Your Points Go" page queries -- expected-points decomposition.

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

from _common import get_config
from confidence import confidence_tier, default_thresholds

from ._shared import TIME_PRESSURE_BUCKETS
from .game_endings import MATE_DISTANCE_BUCKETS

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


def get_failed_conversion_causes(duck_conn, classified, config_path=None):
    """Classifies every failed-conversion game by why the conversion
    likely failed, and (for the hung-piece bucket) which piece type
    hung -- the failed-conversion counterpart to
    game_endings.get_resignation_loss_causes, restricted to the window
    AFTER the position first became winning (first_winning_ply), since a
    hang/blown-mate/clock-crunch BEFORE that point isn't what turned a
    winning position into a non-win.

    Unlike resignation causes, there is no not_analyzed bucket here: the
    points ledger only ever contains analysis_status='done' games (see
    get_points_ledger), so every game already has as much engine
    coverage as it will ever get -- if no move-level signal fires, that
    is a real "other" (a gradual give-back with no single clean cause),
    not a backlog gap. Confirmed live (2026-07-07): the ~200-game
    failed-conversion population has zero overlap with the small set of
    legacy 'done' games that predate cpl/classification entirely.

    A game is classified, in priority order, using only moves at or
    after first_winning_ply:
      1. "hung_piece" -- the same hanging-piece definition
         tactical.get_hallucination_blunders and
         game_endings.get_resignation_loss_causes use (a blunder whose
         opponent's IMMEDIATE next move recaptures on the same square
         for >= hallucination_min_material_delta), closest to the game's
         end among qualifying moves.
      2. "blown_mate" -- the same definition tactical.get_blown_mates
         uses (a forced mate was on the board -- eval_mate > 0 before
         the player's own move -- and the player deviated from the
         engine's best move), closest to the end.
      3. "time_pressure" -- no hang or blown mate, but the player's own
         clock was already in TIME_PRESSURE_BUCKETS' "critical" band
         (<5% of base time) at their last recorded move in this window.
         No opponent-lead condition here (unlike the resignation
         time-pressure check) -- converting precisely under a ticking
         clock is a real mechanism on its own, it doesn't need the
         opponent to also be short.
      4. "other" -- none of the above fired; a genuine gradual
         give-back.

    Takes the already-classified ledger (classify_points_ledger's
    output) rather than re-fetching -- both first_winning_ply (a
    ply-level threshold per game) and the failed_conversion game_id list
    are already sitting in that frame, computed once, for free, in
    get_points_ledger's own wp-curve scan. Passed into this query as a
    VALUES list (small: ~200 rows on the real database) rather than a
    second SQL derivation of "when did this game become winning", so
    there is exactly one implementation of the WINNING_WP threshold to
    keep in sync.

    Returns (reason_df, piece_df, mate_df) -- same shapes as
    get_resignation_loss_causes: reason_df (reason, n, pct -- pct of all
    failed-conversion games), piece_df (hung_piece, n, pct -- pct of
    hung_piece failed conversions only), mate_df (bucket, n, pct -- pct
    of blown_mate failed conversions only, bucketed by
    game_endings.MATE_DISTANCE_BUCKETS). All three empty (not None) when
    there are no failed-conversion games yet.
    """
    cfg = get_config(config_path)
    min_material_delta = cfg["analytics"]["hallucination_min_material_delta"]
    critical_fraction = TIME_PRESSURE_BUCKETS[0][2]  # 0.05, "critical (<5%)"

    empty_reason = pd.DataFrame(columns=["reason", "n", "pct"])
    empty_piece = pd.DataFrame(columns=["hung_piece", "n", "pct"])
    empty_mate = pd.DataFrame(columns=["bucket", "n", "pct"])

    conv = classified[classified.bucket == "failed_conversion"]
    if conv.empty:
        return empty_reason, empty_piece, empty_mate

    pairs = list(zip(conv.game_id, conv.first_winning_ply.astype(int)))
    values_sql = ", ".join(["(?, ?)"] * len(pairs))
    params = [v for pair in pairs for v in pair]

    df = duck_conn.execute(f"""
        WITH fw(game_id, first_winning_ply) AS (VALUES {values_sql}),
        last_hang AS (
            SELECT fw.game_id, m.piece AS hung_piece,
                   ROW_NUMBER() OVER (PARTITION BY fw.game_id ORDER BY m.ply DESC) AS rn
            FROM db.moves m
            JOIN db.moves m2 ON m2.game_id = m.game_id AND m2.ply = m.ply + 1
            JOIN fw ON fw.game_id = m.game_id
            WHERE m.is_player_move = 1 AND m.classification = 'blunder' AND m.cpl IS NOT NULL
              AND m.ply >= fw.first_winning_ply
              AND m2.is_capture = 1 AND m2.to_square = m.to_square
              AND m2.material_delta >= {min_material_delta}
            QUALIFY rn = 1
        ),
        last_blown_mate AS (
            SELECT fw.game_id, m.eval_mate,
                   ROW_NUMBER() OVER (PARTITION BY fw.game_id ORDER BY m.ply DESC) AS rn
            FROM db.moves m
            JOIN fw ON fw.game_id = m.game_id
            WHERE m.is_player_move = 1 AND m.eval_mate IS NOT NULL AND m.eval_mate > 0
              AND m.san != m.best_move_san
              AND m.ply >= fw.first_winning_ply
            QUALIFY rn = 1
        ),
        last_player_clock AS (
            SELECT fw.game_id, m.clock_seconds, g.base_seconds,
                   ROW_NUMBER() OVER (PARTITION BY fw.game_id ORDER BY m.ply DESC) AS rn
            FROM db.moves m
            JOIN fw ON fw.game_id = m.game_id
            JOIN db.games g ON g.id = m.game_id
            WHERE m.is_player_move = 1 AND m.clock_seconds IS NOT NULL
              AND m.ply >= fw.first_winning_ply
              AND g.base_seconds IS NOT NULL AND g.base_seconds > 0
            QUALIFY rn = 1
        )
        SELECT fw.game_id,
               CASE WHEN h.hung_piece IS NOT NULL THEN 'hung_piece'
                    WHEN bm.game_id IS NOT NULL THEN 'blown_mate'
                    WHEN pc.game_id IS NOT NULL
                         AND CAST(pc.clock_seconds AS DOUBLE) / pc.base_seconds < {critical_fraction}
                         THEN 'time_pressure'
                    ELSE 'other' END AS reason,
               h.hung_piece, bm.eval_mate
        FROM fw
        LEFT JOIN last_hang h ON h.game_id = fw.game_id
        LEFT JOIN last_blown_mate bm ON bm.game_id = fw.game_id
        LEFT JOIN last_player_clock pc ON pc.game_id = fw.game_id
    """, params).fetchdf()

    if df.empty:
        return empty_reason, empty_piece, empty_mate

    total = len(df)
    reason_df = df.groupby("reason").size().reindex(
        ["hung_piece", "blown_mate", "time_pressure", "other"], fill_value=0).reset_index(name="n")
    reason_df["pct"] = 100.0 * reason_df.n / total

    hung = df[df.reason == "hung_piece"]
    n_hung = len(hung)
    piece_df = hung.groupby("hung_piece").size().reset_index(name="n")
    piece_df["pct"] = 100.0 * piece_df.n / n_hung if n_hung else 0.0
    piece_df = piece_df.sort_values("n", ascending=False).reset_index(drop=True)

    blown = df[df.reason == "blown_mate"]
    n_blown = len(blown)
    moves_to_mate = blown.eval_mate.abs()
    mate_rows = []
    for label, lo, hi in MATE_DISTANCE_BUCKETS:
        n = int(((moves_to_mate >= lo) & (moves_to_mate < hi)).sum())
        if n:
            mate_rows.append((label, n, 100.0 * n / n_blown if n_blown else 0.0))
    mate_df = pd.DataFrame(mate_rows, columns=["bucket", "n", "pct"])

    return reason_df, piece_df, mate_df


def get_conversion_drill_positions(duck_conn, top_n: int = 20, config_path=None) -> pd.DataFrame:
    """Drill positions for failed-conversion games, one row per game: the
    hung-piece or blown-mate move that turned a winning position into a
    non-win -- the drills.py counterpart to get_failed_conversion_causes,
    which only returns aggregate classification counts. Reuses that
    function's exact last_hang/last_blown_mate CTE definitions (same
    fw(game_id, first_winning_ply) VALUES-list construction, same
    min_material_delta config lookup, same window-function/QUALIFY
    shape), extended to also select m.fen_before, m.best_move_san, and
    m.san AS actual_move_san -- the position and moves a drill card
    needs, which the aggregate-only version never selected.

    Self-contained (unlike get_failed_conversion_causes, which takes an
    already-classified ledger the Points page keeps cached): this is a
    build_drill_cards() source, which has no classified DataFrame lying
    around, so it computes ledger = get_points_ledger(duck_conn);
    classified = classify_points_ledger(ledger) internally. Same
    ~0.78s-on-2.3M-rows cost this module's own docstring already
    documents as acceptable for a single call -- acceptable here too for
    an "Add to deck" button click.

    Verified against the real dev DB (2026-07-11): of 221 total
    failed-conversion games, 53 classify as hung_piece and 26 as
    blown_mate (79 total), both with 100% fen_before/best_move_san
    coverage at the identified ply -- these columns are populated by
    worker.py for every analyzed move, not motif-gated.

    Deliberately scoped to hung_piece/blown_mate only -- the two
    get_failed_conversion_causes reasons with an unambiguous single ply.
    time_pressure (51 games) and other (91 games) do NOT have a clean
    single-ply signal the same way: last_player_clock (the CTE
    get_failed_conversion_causes uses to classify time_pressure) only
    finds the LAST move with clock data in the post-first-winning-ply
    window, not necessarily the move that lost the win, so there's no
    reliable single fen/move to drill for those two reasons -- they are
    excluded from this function's output entirely, not merely unlabeled.
    The last_player_clock CTE itself is dropped here for the same reason.

    reason: 'hung_piece' or 'blown_mate', same priority as
    get_failed_conversion_causes -- hung_piece wins when a game
    qualifies for both (the closer-to-the-end hang is what actually
    ended the game; keeps the tie-break identical to the aggregate
    version so a game's card and its Points-page classification always
    agree).

    No natural single numeric severity score exists across both reason
    types (cpl and eval_mate aren't the same scale), so results are
    ordered by game_id for determinism rather than inventing an
    unmotivated cross-scale sort.

    Returns columns: game_id, fen_before, best_move_san,
    actual_move_san, reason.
    """
    empty = pd.DataFrame(columns=["game_id", "fen_before", "best_move_san",
                                   "actual_move_san", "reason"])

    ledger = get_points_ledger(duck_conn)
    classified = classify_points_ledger(ledger)
    conv = classified[classified.bucket == "failed_conversion"]
    if conv.empty:
        return empty

    cfg = get_config(config_path)
    min_material_delta = cfg["analytics"]["hallucination_min_material_delta"]

    pairs = list(zip(conv.game_id, conv.first_winning_ply.astype(int)))
    values_sql = ", ".join(["(?, ?)"] * len(pairs))
    params = [v for pair in pairs for v in pair] + [top_n]

    df = duck_conn.execute(f"""
        WITH fw(game_id, first_winning_ply) AS (VALUES {values_sql}),
        last_hang AS (
            SELECT fw.game_id, m.piece AS hung_piece,
                   m.fen_before, m.best_move_san, m.san AS actual_move_san,
                   ROW_NUMBER() OVER (PARTITION BY fw.game_id ORDER BY m.ply DESC) AS rn
            FROM db.moves m
            JOIN db.moves m2 ON m2.game_id = m.game_id AND m2.ply = m.ply + 1
            JOIN fw ON fw.game_id = m.game_id
            WHERE m.is_player_move = 1 AND m.classification = 'blunder' AND m.cpl IS NOT NULL
              AND m.ply >= fw.first_winning_ply
              AND m2.is_capture = 1 AND m2.to_square = m.to_square
              AND m2.material_delta >= {min_material_delta}
            QUALIFY rn = 1
        ),
        last_blown_mate AS (
            SELECT fw.game_id, m.eval_mate,
                   m.fen_before, m.best_move_san, m.san AS actual_move_san,
                   ROW_NUMBER() OVER (PARTITION BY fw.game_id ORDER BY m.ply DESC) AS rn
            FROM db.moves m
            JOIN fw ON fw.game_id = m.game_id
            WHERE m.is_player_move = 1 AND m.eval_mate IS NOT NULL AND m.eval_mate > 0
              AND m.san != m.best_move_san
              AND m.ply >= fw.first_winning_ply
            QUALIFY rn = 1
        )
        SELECT fw.game_id                                              AS game_id,
               COALESCE(h.fen_before, bm.fen_before)                    AS fen_before,
               COALESCE(h.best_move_san, bm.best_move_san)              AS best_move_san,
               COALESCE(h.actual_move_san, bm.actual_move_san)          AS actual_move_san,
               CASE WHEN h.hung_piece IS NOT NULL THEN 'hung_piece'
                    ELSE 'blown_mate' END                               AS reason
        FROM fw
        LEFT JOIN last_hang h ON h.game_id = fw.game_id
        LEFT JOIN last_blown_mate bm ON bm.game_id = fw.game_id
        WHERE h.hung_piece IS NOT NULL OR bm.game_id IS NOT NULL
        ORDER BY fw.game_id
        LIMIT ?
    """, params).fetchdf()

    return df if not df.empty else empty


def get_defense_drill_positions(duck_conn, top_n: int = 20) -> pd.DataFrame:
    """Drill positions for the Defense Trainer: one row per game, the
    single worst mistake/blunder (by cpl) made WHILE THE POSITION WAS
    ALREADY WORSE-OR-EVEN (win_prob_before <= EVEN_WP, 0.45 -- "still
    holding the balance", the same constant this module already uses for
    the failed_hold bucket's own threshold, reused here rather than
    hardcoded as a second 0.45 magic number).

    Scoped to games in the failed_hold / missed_swindle buckets --
    together, "a lost-or-even position that was handed a real chance, or
    held into the middlegame, and still lost": the natural "you were
    worse and needed to find the saving/holding resource" counterpart to
    get_conversion_drill_positions's "you were better and let it go".

    This is a DIFFERENT signal shape from get_conversion_drill_positions
    (and get_failed_conversion_causes): a raw positional-quality score
    (cpl), not a categorical hang/blown-mate/clock cause-ladder, and it
    needs zero new engine analysis -- cpl and win_prob_before are already
    populated on every analyzed move, so there is no hung-piece/blown-mate
    CTE machinery here, just a per-game ROW_NUMBER() ranked by cpl DESC
    (mirrors get_decisive_moment_positions's ranked/rn=1 shape).

    Verified against the real dev DB (2026-07-11): 143 games sit in the
    failed_hold/missed_swindle buckets combined; of those, 101 have at
    least one qualifying "worst mistake while already worse" row -- a
    real, usable population, comparable to this session's other three
    trainers (Collapse 304, Time Management 145, Conversion 79).

    Self-contained like get_conversion_drill_positions (this is a
    build_drill_cards() source, with no classified ledger lying around):
    computes ledger = get_points_ledger(duck_conn); classified =
    classify_points_ledger(ledger) internally. No config_path param --
    unlike Conversion's min_material_delta, EVEN_WP is a fixed module
    constant, not config-driven.

    Includes opening/move_number/cpl (unlike get_conversion_drill_positions,
    which doesn't) -- these feed chess_display._drill_context()'s
    human-readable context string, and are available for free via the
    same games join every sibling function already does.

    Returns columns: game_id, fen_before, best_move_san, actual_move_san,
    move_number, opening, cpl. Empty DataFrame with these columns when no
    game qualifies (mirrors get_conversion_drill_positions's empty-shape
    handling) rather than running a query with an empty IN (...) clause.
    """
    empty = pd.DataFrame(columns=["game_id", "fen_before", "best_move_san",
                                   "actual_move_san", "move_number", "opening", "cpl"])

    ledger = get_points_ledger(duck_conn)
    classified = classify_points_ledger(ledger)
    defense_games = classified[classified.bucket.isin(['failed_hold', 'missed_swindle'])].game_id.tolist()
    if not defense_games:
        return empty

    placeholders = ", ".join(["?"] * len(defense_games))
    params = defense_games + [top_n]

    df = duck_conn.execute(f"""
        WITH ranked AS (
            SELECT m.game_id, m.fen_before, m.best_move_san,
                   m.san AS actual_move_san, m.move_number,
                   ROUND(m.cpl, 0) AS cpl,
                   g.opening_family AS opening,
                   ROW_NUMBER() OVER (PARTITION BY m.game_id ORDER BY m.cpl DESC) AS rn
            FROM db.moves m
            JOIN db.games g ON g.id = m.game_id
            WHERE m.is_player_move = 1
              AND m.classification IN ('mistake', 'blunder')
              AND m.fen_before     IS NOT NULL
              AND m.best_move_san  IS NOT NULL
              AND m.win_prob_before IS NOT NULL
              AND m.win_prob_before <= {EVEN_WP}
              AND m.game_id IN ({placeholders})
        )
        SELECT game_id, fen_before, best_move_san, actual_move_san, move_number, opening, cpl
        FROM ranked WHERE rn = 1
        ORDER BY cpl DESC
        LIMIT ?
    """, params).fetchdf()

    return df if not df.empty else empty
