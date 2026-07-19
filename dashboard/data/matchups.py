"""Matchups and Opponents page queries."""
import pandas as pd

import chess_utils
from _common import get_config
from confidence import confidence_tier, default_thresholds

from ._shared import (
    GIANT_KILLING_UPSET_THRESHOLD, GIANT_KILLING_COLLAPSE_THRESHOLD,
    COMEBACK_WP_THRESHOLD, COLLAPSE_WP_THRESHOLD, _quarterly_zero_fill,
    TIME_PRESSURE_BUCKETS, bucket_acpl_blunder_rate,
)
from .game_endings import MATE_DISTANCE_BUCKETS
from .patterns import _classify_castling_config, _classify_action_side


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


def get_nemesis_opponents(duck_conn, min_games: int | None = None, config_path=None):
    """Mirrors analysis/nemesis_opponents.py -- ranked by score% (win +
    0.5*draw, standard tournament scoring) so repeated draws aren't
    misread as losses. Real finding: 17.1% score against a specific
    41-game opponent, one of the largest single-opponent samples in the
    dataset -- never previously surfaced in the dashboard.

    Also returns expected_score_pct/surprise_pct: a confidence-gap fix on
    top of raw score_pct, which conflates "genuinely tough matchup" with
    "this opponent is just rated well above you, no surprise there."
    expected_score_pct is the average Elo-predicted score (standard
    logistic curve, 400-point scale) given each game's OWN rating_diff,
    averaged per game -- not derived from the opponent's average
    rating_diff, which is a different (and wrong) quantity by Jensen's
    inequality once game-to-game rating gaps vary. surprise_pct =
    score_pct - expected_score_pct: how far below what the rating gap
    alone predicts, so a large negative number is a genuine surprise, not
    just "this opponent happens to be much stronger."

    Verified live (2026-07-07): most 0%-score "toughest" opponents on the
    real dev DB have a strongly negative avg rating_diff (e.g.
    J-Voorhees, -312 over 9 games) -- fully explained by facing a much
    stronger player, not a real anomaly. One real exception stood out:
    Artist1565, 0% over 6 games despite being +151 rated on average (the
    player was the expected favorite, predicted ~70%+ by Elo) -- exactly
    the kind of genuine surprise raw score_pct can't distinguish from the
    expected losses above it.

    expected_score_pct/surprise_pct are computed only from games with a
    recorded rating_diff (n_rated) -- NaN when n_rated is 0 for an
    opponent (only possible if this database ever has unrated games;
    zero such rows exist on the real dev DB today).

    min_games defaults to analytics.min_sample_size when not passed
    explicitly. It remains the hard SQL gate below; it doubles as
    confidence.py's "low" tier threshold via default_thresholds(), so the
    returned frame also carries a confidence_tier column (every row is
    at least "low" by construction) for future badge use without
    changing which opponents are returned."""
    if min_games is None:
        min_games = get_config(config_path)["analytics"]["min_sample_size"]
    thresholds = default_thresholds(min_games)
    # all_lichess gates the Opponent Prep deep link: prep's fetch pipeline
    # (sync.py) is lichess-only, so a chess.com opponent's name pre-filled
    # into it would scout the wrong (or a nonexistent) player. Names are
    # grouped across sources, so require every game vs. this opponent to
    # be a lichess game before treating the name as a lichess username.
    df = duck_conn.execute("""
        SELECT opponent_name,
               COUNT(*) AS n,
               SUM(CASE WHEN outcome_for_player='win' THEN 1 ELSE 0 END) AS wins,
               SUM(CASE WHEN outcome_for_player='draw' THEN 1 ELSE 0 END) AS draws,
               SUM(CASE WHEN outcome_for_player='loss' THEN 1 ELSE 0 END) AS losses,
               MIN(CASE WHEN site LIKE 'https://lichess.org/%' THEN 1 ELSE 0 END) AS all_lichess,
               COUNT(rating_diff) AS n_rated,
               AVG(CASE WHEN rating_diff IS NOT NULL
                        THEN 1.0 / (1.0 + POWER(10.0, -rating_diff / 400.0)) END) AS expected_score_frac
        FROM db.games
        WHERE opponent_name IS NOT NULL AND outcome_for_player IS NOT NULL
        GROUP BY opponent_name
        HAVING COUNT(*) >= ?
    """, [min_games]).fetchdf()
    df["score_pct"] = 100.0 * (df.wins + 0.5 * df.draws) / df.n
    df["expected_score_pct"] = 100.0 * df["expected_score_frac"]
    df["surprise_pct"] = df["score_pct"] - df["expected_score_pct"]
    df["confidence_tier"] = df.n.map(lambda n: confidence_tier(n, thresholds))
    return df.drop(columns=["expected_score_frac"])


def get_giant_killing_collapse_causes(duck_conn, config_path=None):
    """Classifies every collapse (a loss as a GIANT_KILLING_COLLAPSE_THRESHOLD+
    rating favorite) by why it likely happened -- the giant-killing
    counterpart to game_endings.get_resignation_loss_causes, generalized
    from "resignation losses" to "losses as a heavy favorite": a collapse
    can end by checkmate, time-forfeit, resignation, or abandonment alike
    (verified live 2026-07-07: 290 resignation / 162 time_forfeit / 63
    checkmate / 26 abandoned of 541 total on the real dev DB), and none of
    those end types by itself explains WHY the favorite lost -- so the
    exact same board/clock signal ladder applies regardless of how the
    game technically ended, rather than special-casing by game_end_type.

    Reuses the identical hung-piece/forced-mate/time-pressure definitions,
    thresholds, and priority order as get_resignation_loss_causes (hung_piece
    > faced_mate > time_pressure > other > not_analyzed), including its
    "near the end of the game" window (hallucination_max_moves_to_resign,
    converted to plies) -- the config key's name is resignation-specific,
    but the SQL there already keys the window off num_plies - ply (how
    close to the game's actual end a signal fired), not off a resignation
    event itself, so the same number and meaning carry over unchanged to
    a collapse that ends any other way.

    Verified live (2026-07-07): only 28 of 541 collapses (5.2%) have any
    analyzed move at all -- the same backlog-skew shape as resignation
    causes -- but 529 of 541 (97.8%) have clock data, since that's read
    straight off the PGN regardless of analysis status.

    Returns (reason_df, piece_df, mate_df) -- identical shapes to
    get_resignation_loss_causes: reason_df (reason, n, pct -- pct of all
    collapses), piece_df (hung_piece, n, pct -- pct of hung_piece
    collapses only), mate_df (bucket, n, pct -- pct of faced_mate
    collapses only, bucketed by MATE_DISTANCE_BUCKETS). All three empty
    (not None) when there are no collapses yet.
    """
    cfg = get_config(config_path)
    min_material_delta = cfg["analytics"]["hallucination_min_material_delta"]
    max_plies_window = cfg["analytics"]["hallucination_max_moves_to_resign"] * 2
    max_own_seconds = cfg["analytics"]["resignation_time_pressure_max_own_seconds"]
    min_opponent_lead_seconds = cfg["analytics"]["resignation_time_pressure_min_opponent_lead_seconds"]

    df = duck_conn.execute(f"""
        WITH collapses AS (
            SELECT id AS game_id, num_plies
            FROM db.games
            WHERE outcome_for_player = 'loss' AND rating_diff >= {GIANT_KILLING_COLLAPSE_THRESHOLD}
        ),
        analyzed_flag AS (
            SELECT DISTINCT c.game_id
            FROM db.moves m JOIN collapses c ON c.game_id = m.game_id
            WHERE m.eval_cp IS NOT NULL OR m.eval_mate IS NOT NULL
        ),
        last_mate AS (
            SELECT c.game_id, m.eval_mate,
                   ROW_NUMBER() OVER (PARTITION BY c.game_id ORDER BY m.ply DESC) AS rn
            FROM db.moves m JOIN collapses c ON c.game_id = m.game_id
            WHERE m.is_player_move = 1 AND m.eval_mate IS NOT NULL AND m.eval_mate < 0
              AND c.num_plies - m.ply <= {max_plies_window}
            QUALIFY rn = 1
        ),
        last_hang AS (
            SELECT c.game_id, m.piece AS hung_piece,
                   ROW_NUMBER() OVER (PARTITION BY c.game_id ORDER BY m.ply DESC) AS rn
            FROM db.moves m
            JOIN db.moves m2 ON m2.game_id = m.game_id AND m2.ply = m.ply + 1
            JOIN collapses c ON c.game_id = m.game_id
            WHERE m.is_player_move = 1 AND m.classification = 'blunder' AND m.cpl IS NOT NULL
              AND m2.is_capture = 1 AND m2.to_square = m.to_square
              AND m2.material_delta >= {min_material_delta}
              AND c.num_plies - m.ply <= {max_plies_window}
            QUALIFY rn = 1
        ),
        last_player_clock AS (
            SELECT c.game_id, m.clock_seconds AS player_clock,
                   ROW_NUMBER() OVER (PARTITION BY c.game_id ORDER BY m.ply DESC) AS rn
            FROM db.moves m JOIN collapses c ON c.game_id = m.game_id
            WHERE m.is_player_move = 1 AND m.clock_seconds IS NOT NULL
            QUALIFY rn = 1
        ),
        last_opponent_clock AS (
            SELECT c.game_id, m.clock_seconds AS opponent_clock,
                   ROW_NUMBER() OVER (PARTITION BY c.game_id ORDER BY m.ply DESC) AS rn
            FROM db.moves m JOIN collapses c ON c.game_id = m.game_id
            WHERE m.is_player_move = 0 AND m.clock_seconds IS NOT NULL
            QUALIFY rn = 1
        )
        SELECT c.game_id,
               CASE WHEN h.hung_piece IS NOT NULL THEN 'hung_piece'
                    WHEN lm.game_id IS NOT NULL THEN 'faced_mate'
                    WHEN pc.player_clock IS NOT NULL AND oc.opponent_clock IS NOT NULL
                         AND pc.player_clock < {max_own_seconds}
                         AND oc.opponent_clock - pc.player_clock >= {min_opponent_lead_seconds}
                         THEN 'time_pressure'
                    WHEN af.game_id IS NOT NULL THEN 'other'
                    ELSE 'not_analyzed' END AS reason,
               h.hung_piece, lm.eval_mate AS mate_eval
        FROM collapses c
        LEFT JOIN analyzed_flag af ON af.game_id = c.game_id
        LEFT JOIN last_mate lm ON lm.game_id = c.game_id
        LEFT JOIN last_hang h ON h.game_id = c.game_id
        LEFT JOIN last_player_clock pc ON pc.game_id = c.game_id
        LEFT JOIN last_opponent_clock oc ON oc.game_id = c.game_id
    """).fetchdf()

    if df.empty:
        empty_reason = pd.DataFrame(columns=["reason", "n", "pct"])
        empty_piece = pd.DataFrame(columns=["hung_piece", "n", "pct"])
        empty_mate = pd.DataFrame(columns=["bucket", "n", "pct"])
        return empty_reason, empty_piece, empty_mate

    total = len(df)
    reason_df = df.groupby("reason").size().reindex(
        ["hung_piece", "faced_mate", "time_pressure", "other", "not_analyzed"],
        fill_value=0).reset_index(name="n")
    reason_df["pct"] = 100.0 * reason_df.n / total

    hung = df[df.reason == "hung_piece"]
    n_hung = len(hung)
    piece_df = hung.groupby("hung_piece").size().reset_index(name="n")
    piece_df["pct"] = 100.0 * piece_df.n / n_hung if n_hung else 0.0
    piece_df = piece_df.sort_values("n", ascending=False).reset_index(drop=True)

    faced_mate = df[df.reason == "faced_mate"]
    n_mate = len(faced_mate)
    moves_to_mate = faced_mate.mate_eval.abs()
    mate_rows = []
    for label, lo, hi in MATE_DISTANCE_BUCKETS:
        n = int(((moves_to_mate >= lo) & (moves_to_mate < hi)).sum())
        if n:
            mate_rows.append((label, n, 100.0 * n / n_mate if n_mate else 0.0))
    mate_df = pd.DataFrame(mate_rows, columns=["bucket", "n", "pct"])

    return reason_df, piece_df, mate_df


def get_giant_killing_rate_trend(duck_conn):
    """Quarterly upset/collapse RATE -- honest to trend over calendar time
    by construction, unlike get_giant_killing_collapse_causes' cause mix:
    rating_diff and outcome_for_player are set at ingest from the game's
    own header data alone, with zero engine-analysis dependency and
    (confirmed live 2026-07-07) zero NULL rating_diff across all 32,295
    games on the real dev DB. This is the collapse/upset-rate counterpart
    to game_endings.get_resignation_time_pressure_trend.

    Returns one row per quarter from the first to the last dated, rated
    game, zero-filled the same way as every other calendar trend in this
    package: year, quarter, period, label, n_underdog, n_upset, pct_upset,
    n_favorite, n_collapse, pct_collapse (NaN, not 0, when a denominator
    is 0). Empty (not None) when there are no rated games yet.
    """
    df = duck_conn.execute(f"""
        SELECT year, ((month - 1) // 3) + 1 AS quarter,
               SUM(CASE WHEN rating_diff <= {GIANT_KILLING_UPSET_THRESHOLD}
                        THEN 1 ELSE 0 END) AS n_underdog,
               SUM(CASE WHEN rating_diff <= {GIANT_KILLING_UPSET_THRESHOLD}
                             AND outcome_for_player = 'win'
                        THEN 1 ELSE 0 END) AS n_upset,
               SUM(CASE WHEN rating_diff >= {GIANT_KILLING_COLLAPSE_THRESHOLD}
                        THEN 1 ELSE 0 END) AS n_favorite,
               SUM(CASE WHEN rating_diff >= {GIANT_KILLING_COLLAPSE_THRESHOLD}
                             AND outcome_for_player = 'loss'
                        THEN 1 ELSE 0 END) AS n_collapse
        FROM db.games
        WHERE rating_diff IS NOT NULL AND outcome_for_player IS NOT NULL
          AND year IS NOT NULL AND month IS NOT NULL
        GROUP BY year, quarter
    """).fetchdf()

    cols = ["year", "quarter", "period", "label", "n_underdog", "n_upset", "pct_upset",
            "n_favorite", "n_collapse", "pct_collapse"]
    if df.empty:
        return pd.DataFrame(columns=cols)

    df = _quarterly_zero_fill(df, ["n_underdog", "n_upset", "n_favorite", "n_collapse"])
    df["pct_upset"] = 100.0 * df["n_upset"] / df["n_underdog"].where(df["n_underdog"] > 0)
    df["pct_collapse"] = 100.0 * df["n_collapse"] / df["n_favorite"].where(df["n_favorite"] > 0)
    return df[cols]


def get_opponent_profile(duck_conn, opponent_name, config_path=None):
    """Per-opponent breakdown across openings, position character,
    castling/attack-side, and clock pressure -- each axis re-scopes an
    existing classification (chess_utils.classify_position_character,
    patterns._classify_castling_config/_classify_action_side,
    _shared.bucket_acpl_blunder_rate + TIME_PRESSURE_BUCKETS) to
    WHERE opponent_name = ? instead of its usual whole-database grouping.
    No new chess-analysis logic, only new grouping scope.

    Row counts per opponent are small (rarely more than a few dozen
    games), so plain pandas .apply() for the castling/position
    classifiers is fine here -- unlike the whole-database case that
    caused a real ~280x slowdown elsewhere in this codebase (see
    chess_utils.classify_position_character's caller), that anti-pattern
    is about scale, not about .apply() itself.

    Returns a dict: n_games (int, total games vs this opponent),
    openings (DataFrame: opening_family, n_games, win_pct, acpl),
    position (DataFrame: bucket, n_games, win_pct -- open/semi-open/closed),
    castling (DataFrame: castling_config, n_games, win_pct),
    action_side (DataFrame: action_side, n_games, win_pct),
    clock (DataFrame: bucket, n_moves, acpl, blunder_rate -- TIME_PRESSURE_BUCKETS).
    Every DataFrame is empty (not None) when its underlying data is empty,
    same convention as every other query function in this module.
    """
    cfg = get_config(config_path)
    middlegame_ply = cfg["analytics"]["middlegame_ply"]
    ratio = cfg["analytics"]["action_side_capture_ratio"]

    n_games = duck_conn.execute(
        "SELECT COUNT(*) FROM db.games WHERE opponent_name = ?", [opponent_name]).fetchone()[0]

    openings = duck_conn.execute("""
        SELECT g.opening_family, COUNT(DISTINCT g.id) AS n_games,
               100.0 * SUM(CASE WHEN g.outcome_for_player='win' THEN 1 ELSE 0 END) / COUNT(DISTINCT g.id) AS win_pct,
               AVG(m.cpl) AS acpl
        FROM db.games g
        LEFT JOIN db.moves m ON m.game_id = g.id AND m.is_player_move=1 AND m.cpl IS NOT NULL
        WHERE g.opponent_name = ? AND g.opening_family IS NOT NULL AND g.outcome_for_player IS NOT NULL
        GROUP BY g.opening_family
        ORDER BY n_games DESC
    """, [opponent_name]).fetchdf()

    position_ctx = duck_conn.execute(f"""
        SELECT m.game_id, m.fen_before, g.outcome_for_player
        FROM db.moves m JOIN db.games g ON g.id = m.game_id
        WHERE m.ply = {middlegame_ply} AND m.fen_before IS NOT NULL AND g.opponent_name = ?
    """, [opponent_name]).fetchdf()
    if position_ctx.empty:
        position = pd.DataFrame(columns=["bucket", "n_games", "win_pct"])
    else:
        classified = pd.DataFrame(
            position_ctx["fen_before"].apply(chess_utils.classify_position_character).tolist())
        position_ctx = pd.concat(
            [position_ctx.drop(columns=["fen_before"]), classified], axis=1)
        sub = position_ctx.dropna(subset=["outcome_for_player"])
        if sub.empty:
            position = pd.DataFrame(columns=["bucket", "n_games", "win_pct"])
        else:
            position = sub.groupby("bucket").agg(
                n_games=("game_id", "count"),
                win_pct=("outcome_for_player", lambda s: 100.0 * (s == "win").sum() / len(s)),
            ).reset_index()

    side_ctx = duck_conn.execute("""
        SELECT g.id AS game_id, g.outcome_for_player,
               MAX(CASE WHEN m.is_castle=1 AND m.color='w' THEN m.to_square END) AS white_castle_sq,
               MAX(CASE WHEN m.is_castle=1 AND m.color='b' THEN m.to_square END) AS black_castle_sq,
               SUM(CASE WHEN m.is_capture=1 AND substr(m.to_square,1,1) IN ('a','b','c','d')
                        THEN 1 ELSE 0 END) AS q_caps,
               SUM(CASE WHEN m.is_capture=1 AND substr(m.to_square,1,1) IN ('e','f','g','h')
                        THEN 1 ELSE 0 END) AS k_caps
        FROM db.games g JOIN db.moves m ON m.game_id = g.id
        WHERE g.opponent_name = ?
        GROUP BY g.id, g.outcome_for_player
    """, [opponent_name]).fetchdf()
    if side_ctx.empty:
        castling = pd.DataFrame(columns=["castling_config", "n_games", "win_pct"])
        action_side = pd.DataFrame(columns=["action_side", "n_games", "win_pct"])
    else:
        side_ctx["castling_config"] = side_ctx.apply(
            lambda r: _classify_castling_config(r["white_castle_sq"], r["black_castle_sq"]), axis=1)
        side_ctx["action_side"] = side_ctx.apply(
            lambda r: _classify_action_side(r["q_caps"], r["k_caps"], ratio), axis=1)
        sub = side_ctx.dropna(subset=["outcome_for_player"])
        if sub.empty:
            castling = pd.DataFrame(columns=["castling_config", "n_games", "win_pct"])
            action_side = pd.DataFrame(columns=["action_side", "n_games", "win_pct"])
        else:
            castling = sub.groupby("castling_config").agg(
                n_games=("game_id", "count"),
                win_pct=("outcome_for_player", lambda s: 100.0 * (s == "win").sum() / len(s)),
            ).reset_index()
            action_side = sub.groupby("action_side").agg(
                n_games=("game_id", "count"),
                win_pct=("outcome_for_player", lambda s: 100.0 * (s == "win").sum() / len(s)),
            ).reset_index()

    clock_df = duck_conn.execute("""
        SELECT m.cpl, m.classification,
               CAST(m.clock_seconds AS DOUBLE) / g.base_seconds AS time_fraction
        FROM db.moves m JOIN db.games g ON g.id = m.game_id
        WHERE m.is_player_move=1 AND m.cpl IS NOT NULL
          AND m.clock_seconds IS NOT NULL AND g.base_seconds IS NOT NULL AND g.base_seconds > 0
          AND g.opponent_name = ?
    """, [opponent_name]).fetchdf()
    clock = bucket_acpl_blunder_rate(clock_df, "time_fraction", TIME_PRESSURE_BUCKETS)

    return {
        "n_games": n_games,
        "openings": openings,
        "position": position,
        "castling": castling,
        "action_side": action_side,
        "clock": clock,
    }


def get_opponent_swindle_rate(points_ledger, opponent_name):
    """Pure pandas, no I/O -- points_ledger is the already-classified
    ledger (points.get_points_ledger + points.classify_points_ledger,
    fetched once and cached elsewhere as cached_queries.cached_points_ledger),
    which already carries opponent_name and bucket per row. Filters to
    this opponent's losses and reports what share were missed swindles.
    Returns {n_losses, n_missed_swindle, swindle_rate_pct} --
    swindle_rate_pct is None (not 0) when n_losses is 0, same
    zero-vs-no-data discipline as every other rate in this codebase."""
    sub = points_ledger[points_ledger.opponent_name == opponent_name]
    losses = sub[sub.outcome_for_player == "loss"]
    n_losses = len(losses)
    if n_losses == 0:
        return {"n_losses": 0, "n_missed_swindle": 0, "swindle_rate_pct": None}
    n_missed = int((losses.bucket == "missed_swindle").sum())
    return {"n_losses": n_losses, "n_missed_swindle": n_missed,
            "swindle_rate_pct": 100.0 * n_missed / n_losses}
