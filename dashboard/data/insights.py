"""Insights page query -- composes existing per-domain functions
(patterns.py, tactical.py, matchups.py, game_endings.py) into a small set
of "what stands out" findings, computed live from however much data is
currently analyzed.

This replaces, in spirit, the old findings_view.py dropped in Phase A
(see BRIEF.md S6a): that page depended on a hand-curated FINDINGS.md and
an analysis/ subprocess, neither of which generalizes to an arbitrary
fresh install. This version has no curated file at all -- every finding
below is recomputed from whatever's in the database right now, so it's
naturally "live" with no separate refresh mechanism of its own (the
existing sidebar "Refresh data" button / st.cache_data already cover it).

Each finding is independently SKIPPED (returns None), not rendered with
a placeholder, when its underlying data is too thin to say anything real
-- this page is reachable with as few as 1-3 analyzed games, so "no
findings yet" must be a normal, common state, not a crash or a wall of
"--" placeholders.
"""
import pandas as pd

import analytics
import chess_utils
from . import patterns, matchups, game_endings
from ._shared import TIME_PRESSURE_BUCKETS, THINKING_TIME_BUCKETS, bucket_acpl_blunder_rate
from _common import get_config
from confidence import confidence_tier, default_thresholds

# Minimum sample sizes below are deliberately conservative and ad hoc --
# there's no statistical test here, just "enough rows that one outlier
# move/game can't dominate the number," consistent with how thin a
# starter dataset (BRIEF.md Phase B) is expected to be early on. Each
# constant is still the exact hard gate used below (unchanged); it now
# also doubles as confidence.py's "low" tier threshold via
# default_thresholds(), so medium/high tiers exist for future badge use
# without changing which rows/findings pass the gate today.
MIN_PIECE_MOVES = 20
MIN_BUCKET_MOVES = 20
MIN_BACKRANK_MOVES = 20
MIN_OPPONENT_GAMES = 5
MIN_CASTLE_GAMES = 5
MIN_BISHOP_ENDING_MOVES = 20

PIECE_MOVES_THRESHOLDS = default_thresholds(MIN_PIECE_MOVES)
BUCKET_MOVES_THRESHOLDS = default_thresholds(MIN_BUCKET_MOVES)
BACKRANK_MOVES_THRESHOLDS = default_thresholds(MIN_BACKRANK_MOVES)
OPPONENT_GAMES_THRESHOLDS = default_thresholds(MIN_OPPONENT_GAMES)
CASTLE_GAMES_THRESHOLDS = default_thresholds(MIN_CASTLE_GAMES)
BISHOP_ENDING_MOVES_THRESHOLDS = default_thresholds(MIN_BISHOP_ENDING_MOVES)

# Severity thresholds are magnitude-based (percentage-point gaps, ratios,
# rate deltas), not sample-size gates -- reusing confidence_tier()'s
# generic (value, {tier: cutoff}) mechanism for a different axis rather
# than inventing a second tiering scheme. "low" cutoff is always 0 so
# every finding that reaches severity scoring gets at least "low" (a
# finding that already passed its confidence gate is never "insufficient"
# severity -- it's already established as real, just maybe small).
RATIO_SEVERITY_THRESHOLDS = {"low": 0, "medium": 1.5, "high": 2.5}
BLUNDER_GAP_SEVERITY_THRESHOLDS = {"low": 0, "medium": 5, "high": 10}
WINRATE_GAP_SEVERITY_THRESHOLDS = {"low": 0, "medium": 10, "high": 20}
ACPL_GAP_SEVERITY_THRESHOLDS = {"low": 0, "medium": 10, "high": 20}
NEMESIS_SURPRISE_SEVERITY_THRESHOLDS = {"low": 0, "medium": 15, "high": 30}
NEMESIS_FALLBACK_SEVERITY_THRESHOLDS = {"low": 0, "medium": 20, "high": 35}
COLLAPSE_RATE_SEVERITY_THRESHOLDS = {"low": 0, "medium": 10, "high": 25}


def _fetch_move_correlates(duck_conn):
    """Single moves scan shared by all findings in get_career_findings.

    Extended beyond the original 7 columns to also cover the backrank,
    brilliant-candidate, and blown-mate findings -- each was previously a
    separate DuckDB query (~600-1300ms each against the 2.3M-row moves
    table). Adding the columns here costs ~540ms extra (more bytes
    transferred per row) but eliminates 3 separate SQLITE_SCANs totalling
    ~2.6s. Net savings on a 32k-game database: ~2s per career-findings
    call."""
    return duck_conn.execute("""
        SELECT m.cpl, m.classification, m.piece, m.sharpness, m.time_spent_seconds,
               m.clock_seconds, g.base_seconds,
               m.to_square, m.color,
               m.is_brilliant_candidate, m.eval_mate, m.san, m.best_move_san,
               g.outcome_for_player
        FROM db.moves m JOIN db.games g ON g.id = m.game_id
        WHERE m.is_player_move=1 AND m.cpl IS NOT NULL
    """).fetchdf()


def _piece_hotspot(moves_df, baseline_blunder_rate):
    if not baseline_blunder_rate:
        return None
    df = moves_df.dropna(subset=["piece"])
    if df.empty:
        return None
    grouped = df.groupby("piece").agg(
        n_moves=("cpl", "size"),
        blunder_rate=("classification", lambda s: 100.0 * (s == "blunder").sum() / len(s)),
    ).reset_index()
    grouped = grouped[grouped.n_moves.map(
        lambda n: confidence_tier(n, PIECE_MOVES_THRESHOLDS) != "insufficient")]
    if grouped.empty:
        return None
    row = grouped.loc[grouped.blunder_rate.idxmax()]
    piece_name = patterns.PIECE_NAME.get(row.piece, row.piece)
    ratio = row.blunder_rate / baseline_blunder_rate
    return {
        "title": "Piece blunder hot-spot",
        "headline": f"{piece_name.capitalize()} moves blunder at {row.blunder_rate:.1f}%",
        "detail": f"{ratio:.1f}x your overall blunder rate of {baseline_blunder_rate:.1f}%, "
                  f"over {int(row.n_moves)} analyzed {piece_name} moves.",
        "confidence": confidence_tier(row.n_moves, PIECE_MOVES_THRESHOLDS),
        "severity": confidence_tier(ratio, RATIO_SEVERITY_THRESHOLDS),
        "polarity": "weakness",
        "category": "tactical",
    }


def _safest_piece(moves_df, baseline_blunder_rate):
    """Mirrors _piece_hotspot but picks the piece with the LOWEST blunder
    rate instead of the highest -- same already-fetched moves_df, same
    grouping, zero extra query cost. A real strength finding: which piece
    you handle best relative to your own baseline."""
    if not baseline_blunder_rate:
        return None
    df = moves_df.dropna(subset=["piece"])
    if df.empty:
        return None
    grouped = df.groupby("piece").agg(
        n_moves=("cpl", "size"),
        blunder_rate=("classification", lambda s: 100.0 * (s == "blunder").sum() / len(s)),
    ).reset_index()
    grouped = grouped[grouped.n_moves.map(
        lambda n: confidence_tier(n, PIECE_MOVES_THRESHOLDS) != "insufficient")]
    if grouped.empty:
        return None
    row = grouped.loc[grouped.blunder_rate.idxmin()]
    piece_name = patterns.PIECE_NAME.get(row.piece, row.piece)
    inverse_ratio = (baseline_blunder_rate / row.blunder_rate) if row.blunder_rate > 0 else 999
    return {
        "title": "Safest piece",
        "headline": f"{piece_name.capitalize()} moves blunder at only {row.blunder_rate:.1f}%",
        "detail": f"vs. your overall blunder rate of {baseline_blunder_rate:.1f}%, "
                  f"over {int(row.n_moves)} analyzed {piece_name} moves.",
        "confidence": confidence_tier(row.n_moves, PIECE_MOVES_THRESHOLDS),
        "severity": confidence_tier(inverse_ratio, RATIO_SEVERITY_THRESHOLDS),
        "polarity": "strength",
        "category": "tactical",
    }


def _sharpness(moves_df):
    df = moves_df.dropna(subset=["sharpness"])
    bucketed = bucket_acpl_blunder_rate(df, "sharpness", patterns.SHARPNESS_BUCKETS)
    bucketed = bucketed[bucketed.n_moves.map(
        lambda n: confidence_tier(n, BUCKET_MOVES_THRESHOLDS) != "insufficient")]
    if len(bucketed) < 2:
        return None
    flat, forcing = bucketed.iloc[0], bucketed.iloc[-1]
    delta = forcing.blunder_rate - flat.blunder_rate
    if delta >= 0:
        headline = f"Blunder rate climbs from {flat.blunder_rate:.1f}% to {forcing.blunder_rate:.1f}%"
        polarity = "weakness"
    else:
        headline = (f"Blunder rate holds steady or falls, from {flat.blunder_rate:.1f}% (flattest) "
                    f"to {forcing.blunder_rate:.1f}% (most forcing)")
        polarity = "strength"
    return {
        "title": "Sharp positions and blunder rate",
        "headline": headline,
        "detail": f"Comparing your flattest positions ({flat.bucket}) to your most forcing "
                  f"ones ({forcing.bucket}) -- sharpness is how much the best move beats the "
                  f"second-best, a high gap meaning only one move was actually good.",
        "confidence": confidence_tier(min(flat.n_moves, forcing.n_moves), BUCKET_MOVES_THRESHOLDS),
        "severity": confidence_tier(abs(delta), BLUNDER_GAP_SEVERITY_THRESHOLDS),
        "polarity": polarity,
        "category": "tactical",
    }


def _thinking_time(moves_df):
    df = moves_df[moves_df.time_spent_seconds.notna() & (moves_df.time_spent_seconds >= 0)]
    bucketed = bucket_acpl_blunder_rate(df, "time_spent_seconds", THINKING_TIME_BUCKETS)
    bucketed = bucketed[bucketed.n_moves.map(
        lambda n: confidence_tier(n, BUCKET_MOVES_THRESHOLDS) != "insufficient")]
    if len(bucketed) < 2:
        return None
    worst = bucketed.loc[bucketed.blunder_rate.idxmax()]
    best = bucketed.loc[bucketed.blunder_rate.idxmin()]
    return {
        "title": "Thinking time vs. blunder rate",
        "headline": f"Your worst blunder rate ({worst.blunder_rate:.1f}%) is on \"{worst.bucket}\" moves",
        "detail": f"Your best ({best.blunder_rate:.1f}%) is on \"{best.bucket}\" moves -- "
                  f"not always the slowest bucket that's safest.",
        "confidence": confidence_tier(min(worst.n_moves, best.n_moves), BUCKET_MOVES_THRESHOLDS),
        "severity": confidence_tier(worst.blunder_rate - best.blunder_rate, BLUNDER_GAP_SEVERITY_THRESHOLDS),
        "polarity": "mixed",
        "category": "time",
    }


def _time_pressure(moves_df):
    df = moves_df.dropna(subset=["clock_seconds", "base_seconds"])
    df = df[df.base_seconds > 0]
    if df.empty:
        return None
    df = df.copy()
    df["time_fraction"] = df.clock_seconds / df.base_seconds
    bucketed = bucket_acpl_blunder_rate(df, "time_fraction", TIME_PRESSURE_BUCKETS)
    bucketed = bucketed[bucketed.n_moves.map(
        lambda n: confidence_tier(n, BUCKET_MOVES_THRESHOLDS) != "insufficient")]
    if len(bucketed) < 2:
        return None
    worst = bucketed.loc[bucketed.blunder_rate.idxmax()]
    best = bucketed.loc[bucketed.blunder_rate.idxmin()]
    return {
        "title": "Clock pressure and blunder rate",
        "headline": f"Blunder rate peaks at {worst.blunder_rate:.1f}% with \"{worst.bucket}\" clock left",
        "detail": f"vs. {best.blunder_rate:.1f}% with \"{best.bucket}\" clock left.",
        "confidence": confidence_tier(min(worst.n_moves, best.n_moves), BUCKET_MOVES_THRESHOLDS),
        "severity": confidence_tier(worst.blunder_rate - best.blunder_rate, BLUNDER_GAP_SEVERITY_THRESHOLDS),
        "polarity": "mixed",
        "category": "time",
    }


def _castling(duck_conn, config_path=None):
    win_df, _acpl_df = patterns.get_castling_performance(duck_conn, config_path=config_path)
    if win_df.empty or len(win_df) < 2 or win_df.n_games.map(
            lambda n: confidence_tier(n, CASTLE_GAMES_THRESHOLDS) == "insufficient").any():
        return None
    castled = win_df[win_df.status == "castled"].iloc[0]
    not_castled = win_df[win_df.status == "did not castle"].iloc[0]
    return {
        "title": "Castling and win rate",
        "headline": f"{castled.win_pct:.1f}% win rate when you castle",
        "detail": f"vs. {not_castled.win_pct:.1f}% in games where you don't, "
                  f"in games long enough for castling to be a real option.",
        "confidence": confidence_tier(min(castled.n_games, not_castled.n_games), CASTLE_GAMES_THRESHOLDS),
        "severity": confidence_tier(abs(castled.win_pct - not_castled.win_pct), WINRATE_GAP_SEVERITY_THRESHOLDS),
        "polarity": "strength" if castled.win_pct >= not_castled.win_pct else "weakness",
        "category": "defense",
    }


def _backrank(moves_df):
    """Compute king back-rank performance from the pre-fetched moves_df
    instead of firing a separate DuckDB query -- the required columns
    (piece, to_square, color, cpl) are already in the DataFrame."""
    df = moves_df[
        (moves_df.piece == "K") & moves_df.to_square.notna() & moves_df.color.notna()
    ].copy()
    if df.empty:
        return None
    rank = df.to_square.str[1]
    back_rank_char = df.color.map({"w": "1", "b": "8"})
    df["is_back_rank"] = rank == back_rank_char
    result = df.groupby("is_back_rank").agg(n_moves=("cpl", "size"), acpl=("cpl", "mean")).reset_index()
    result = result[result.n_moves.map(
        lambda n: confidence_tier(n, BACKRANK_MOVES_THRESHOLDS) != "insufficient")]
    if len(result) < 2:
        return None
    back = result[result.is_back_rank].iloc[0]
    elsewhere = result[~result.is_back_rank].iloc[0]
    return {
        "title": "King moves off the back rank",
        "headline": f"King ACPL off the back rank: {elsewhere.acpl:.1f}",
        "detail": f"vs. {back.acpl:.1f} on the back rank -- the average centipawn loss per move.",
        "confidence": confidence_tier(min(elsewhere.n_moves, back.n_moves), BACKRANK_MOVES_THRESHOLDS),
        "severity": confidence_tier(abs(elsewhere.acpl - back.acpl), ACPL_GAP_SEVERITY_THRESHOLDS),
        "polarity": "weakness" if elsewhere.acpl > back.acpl else "strength",
        "category": "defense",
    }


def _nemesis(duck_conn):
    """Ranked by surprise_pct (score_pct minus the Elo-expected score for
    each game's own rating_diff), not raw score_pct -- picking the lowest
    raw score would usually just surface "the opponent you happen to be
    most out-rated by," which raw score% alone can't distinguish from a
    genuinely lopsided result against a similarly- or lower-rated player
    (see matchups.get_nemesis_opponents' docstring for the live example
    that motivated this). Falls back to raw score_pct only if every
    opponent's expected_score_pct is unavailable (no rated games at all)."""
    df = matchups.get_nemesis_opponents(duck_conn, min_games=MIN_OPPONENT_GAMES)
    if df.empty:
        return None
    rated = df[df.surprise_pct.notna()]
    toughest = (rated.loc[rated.surprise_pct.idxmin()] if len(rated)
                else df.loc[df.score_pct.idxmin()])
    detail = f"Over {int(toughest.n)} games (win + 0.5 x draw, standard tournament scoring)."
    if pd.notna(toughest.get("expected_score_pct")):
        detail += (f" The rating gap alone predicted {toughest.expected_score_pct:.1f}% -- "
                   "this is a real surprise, not just a stronger opponent.")
        severity = confidence_tier(
            toughest.expected_score_pct - toughest.score_pct, NEMESIS_SURPRISE_SEVERITY_THRESHOLDS)
    else:
        severity = confidence_tier(
            max(0, 50 - toughest.score_pct), NEMESIS_FALLBACK_SEVERITY_THRESHOLDS)
    return {
        "title": "Toughest opponent",
        "headline": f"{toughest.score_pct:.1f}% score against {toughest.opponent_name}",
        "detail": detail,
        "opponent_name": toughest.opponent_name,
        # Gates the "Scout this opponent" deep link -- see the all_lichess
        # comment in matchups.get_nemesis_opponents.
        "opponent_on_lichess": bool(toughest.all_lichess),
        "confidence": confidence_tier(toughest.n, OPPONENT_GAMES_THRESHOLDS),
        "severity": severity,
        "polarity": "weakness",
        "category": "matchup",
    }


def _best_matchup(duck_conn):
    """Mirrors _nemesis but picks the opponent with the HIGHEST surprise_pct
    (biggest positive overperformance vs. Elo-expected) instead of the
    lowest -- same query (matchups.get_nemesis_opponents), opposite
    direction. A real strength finding: who you beat more than the rating
    gap alone would predict."""
    df = matchups.get_nemesis_opponents(duck_conn, min_games=MIN_OPPONENT_GAMES)
    if df.empty:
        return None
    rated = df[df.surprise_pct.notna()]
    best = (rated.loc[rated.surprise_pct.idxmax()] if len(rated)
            else df.loc[df.score_pct.idxmax()])
    detail = f"Over {int(best.n)} games (win + 0.5 x draw, standard tournament scoring)."
    if pd.notna(best.get("expected_score_pct")):
        detail += (f" The rating gap alone predicted {best.expected_score_pct:.1f}% -- "
                   "you're overperforming, not just facing a weaker opponent.")
        severity = confidence_tier(
            best.score_pct - best.expected_score_pct, NEMESIS_SURPRISE_SEVERITY_THRESHOLDS)
    else:
        severity = confidence_tier(
            max(0, best.score_pct - 50), NEMESIS_FALLBACK_SEVERITY_THRESHOLDS)
    return {
        "title": "Best matchup",
        "headline": f"{best.score_pct:.1f}% score against {best.opponent_name}",
        "detail": detail,
        "opponent_name": best.opponent_name,
        "confidence": confidence_tier(best.n, OPPONENT_GAMES_THRESHOLDS),
        "severity": severity,
        "polarity": "strength",
        "category": "matchup",
    }


def _giant_killing(duck_conn):
    gk = matchups.get_giant_killing_counts(duck_conn)
    if not gk["n_underdog_games"] and not gk["n_favorite_games"]:
        return None
    parts = []
    if gk["n_underdog_games"]:
        parts.append(f"{gk['n_upsets']} of {gk['n_underdog_games']} as a 300+ underdog")
    if gk["n_favorite_games"]:
        parts.append(f"{gk['n_collapses']} losses of {gk['n_favorite_games']} as a 300+ favorite")
    collapse_rate = 100.0 * gk["n_collapses"] / gk["n_favorite_games"] if gk["n_favorite_games"] else 0
    return {
        "title": "Giant-killing and collapses",
        "headline": f"{gk['n_upsets']} upset win(s) on record",
        "detail": " and ".join(parts) + ".",
        "severity": confidence_tier(collapse_rate, COLLAPSE_RATE_SEVERITY_THRESHOLDS),
        "polarity": "mixed",
        "category": "giant_killer",
    }


def _tactical_highlights(duck_conn, moves_df, config_path=None):
    """Compute tactical highlight counts for the insights finding.

    n_brilliant and n_blown_loss come from the pre-fetched moves_df (no
    extra DuckDB scan needed). n_hangs still requires the self-join query
    in get_hallucination_blunders -- there's no way to compute it from the
    per-move DataFrame without re-joining moves against moves."""
    n_brilliant = int(moves_df.is_brilliant_candidate.sum())
    blown_mask = (
        moves_df.eval_mate.notna() & (moves_df.eval_mate > 0) &
        moves_df.best_move_san.notna() & (moves_df.san != moves_df.best_move_san) &
        (moves_df.outcome_for_player == "loss"))
    n_blown_loss = int(blown_mask.sum())
    cfg = get_config(config_path)
    min_delta = cfg["analytics"]["hallucination_min_material_delta"]
    n_hangs = duck_conn.execute(f"""
        SELECT COUNT(*) FROM db.moves m
        JOIN db.moves m2 ON m2.game_id = m.game_id AND m2.ply = m.ply + 1
        WHERE m.is_player_move=1 AND m.classification='blunder' AND m.cpl IS NOT NULL
          AND m2.is_capture=1 AND m2.to_square=m.to_square
          AND m2.material_delta >= {min_delta}
    """).fetchone()[0]
    if not (n_brilliant or n_hangs or n_blown_loss):
        return None
    return {
        "title": "Tactical highlights so far",
        "headline": f"{n_brilliant} brilliant-move candidate(s) found",
        "detail": f"{n_hangs} hanging-piece blunder(s), {n_blown_loss} forced mate(s) blown "
                  f"and lost anyway.",
        # Informational round-up, not a ranked weakness -- brilliant moves
        # are good news, hangs/blown mates are bad, they can't net into one
        # magnitude, so this is always "low" rather than computed.
        "severity": "low",
        "polarity": "neutral",
        "category": "tactical",
    }


def _game_endings(duck_conn):
    overall_df, _by_tc = game_endings.get_game_end_type_breakdown(duck_conn)
    if overall_df is None or overall_df.empty:
        return None
    total = overall_df.n.sum()
    top = overall_df.iloc[0]
    return {
        "title": "How your games end",
        "headline": f"{100.0 * top.n / total:.0f}% end in {top.game_end_type}",
        "detail": f"Based on {int(total)} games with a recorded ending type.",
        # Informational distribution stat, not inherently good or bad --
        # there's no "worse" direction for how games end to rank against.
        "severity": "low",
        "polarity": "neutral",
        "category": "general",
    }


def _bishop_color_endings(duck_conn, sqlite_conn, config_path=None):
    """Classifies each game's endgame-checkpoint position (structure_ctx's
    endgame_ply -- the same access pattern get_position_character_
    performance uses for pawn-structure classification) as same-color or
    opposite-color bishop, the one axis material_sig can never express
    (piece COUNTS only, no square color) -- Material Structure Explorer
    Tier 2's gap (roadmap §17 Q1), delivered here as an Insights finding
    rather than a Patterns-page addition since patterns.py/patterns_view.py/
    _shared.py are this session's frozen files, still pending review from
    the Tier 1 unit (§18). Only meaningful when each side has exactly one
    bishop at that checkpoint (chess_utils.classify_bishop_color_ending
    returns None otherwise) -- those games are excluded, same "no row"
    convention as every other structure_ctx consumer.

    ACPL is measured over player moves from endgame_ply ONWARD (the actual
    ending itself), not the whole game or just the single transition move --
    checked empirically against the real dev DB before picking this
    definition: the transition-move-only ACPL (n=82/125) actually reverses
    direction (opposite 39.3 < same 43.0 -- too thin and noisy to trust),
    whole-game ACPL (n=3482/5629) shows a real but modest 7.8 CPL gap
    diluted by opening/middlegame play unrelated to the ending, while
    restricting to moves >= endgame_ply isolates the technique difference
    chess theory actually predicts: opposite 125.8 vs. same 95.5 ACPL
    (n=1224/2364) -- the definition used below. Win/draw rate were checked
    too and show no real signal on the real dev DB (draw rate 7.5% vs.
    8.6%, win rate 47.8% vs. 47.6%) -- ACPL, not outcome, is the real
    finding here."""
    cfg = get_config(config_path)
    analytics.ensure_structure_ctx(sqlite_conn, cfg)

    ctx = duck_conn.execute("""
        SELECT m.game_id, m.fen_before
        FROM db.structure_ctx_cache sc
        JOIN db.moves m ON m.game_id = sc.game_id AND m.ply = sc.endgame_ply
        WHERE sc.endgame_ply IS NOT NULL AND m.fen_before IS NOT NULL
    """).fetchdf()
    if ctx.empty:
        return None
    ctx["bucket"] = ctx.fen_before.apply(chess_utils.classify_bishop_color_ending)
    ctx = ctx.dropna(subset=["bucket"])
    if ctx.bucket.nunique() < 2:
        return None

    moves = duck_conn.execute("""
        SELECT m.game_id, m.cpl
        FROM db.moves m JOIN db.structure_ctx_cache sc ON sc.game_id = m.game_id
        WHERE m.is_player_move = 1 AND m.cpl IS NOT NULL
          AND sc.endgame_ply IS NOT NULL AND m.ply >= sc.endgame_ply
    """).fetchdf()
    merged = moves.merge(ctx[["game_id", "bucket"]], on="game_id")
    if merged.empty:
        return None
    result = merged.groupby("bucket").agg(
        n_moves=("cpl", "size"), acpl=("cpl", "mean")).reset_index()
    result = result[result.n_moves.map(
        lambda n: confidence_tier(n, BISHOP_ENDING_MOVES_THRESHOLDS) != "insufficient")]
    opp = result[result.bucket == "opposite"]
    same = result[result.bucket == "same"]
    if opp.empty or same.empty:
        return None
    opp, same = opp.iloc[0], same.iloc[0]
    return {
        "title": "Opposite-color bishop endings",
        "headline": f"ACPL {opp.acpl:.1f} in opposite-color-bishop endings",
        "detail": f"vs. {same.acpl:.1f} when both bishops are on the same color, "
                  f"measured from the point each ending was reached.",
        "confidence": confidence_tier(min(opp.n_moves, same.n_moves), BISHOP_ENDING_MOVES_THRESHOLDS),
        "severity": confidence_tier(abs(opp.acpl - same.acpl), ACPL_GAP_SEVERITY_THRESHOLDS),
        "polarity": "weakness" if opp.acpl > same.acpl else "strength",
        # "tactical" (not "defense"/"King safety" -- that label is specific
        # to castling/back-rank king safety, not a fit here), matching
        # _piece_hotspot/_safest_piece's category for the same shape of
        # finding: move-quality (ACPL/blunder rate) varying by a structural
        # feature, not a king-safety concept.
        "category": "tactical",
    }


def get_career_findings(duck_conn, sqlite_conn, baseline_blunder_rate, config_path=None):
    """Returns a list of {title, headline, detail} dicts, one per finding
    that currently has enough data to say something -- order is the
    fixed display order, not a ranking by "significance" (no principled
    way to rank across domains this different).

    Each finding also carries:
    - severity: "low"/"medium"/"high", always present -- a magnitude-based
      tier (percentage-point gap, ratio, or rate) scored via
      confidence_tier() reused for this different axis, not the sample-size
      axis. Findings without a natural single-direction magnitude
      (_tactical_highlights, _game_endings) get a literal "low" instead of
      a computed value.
    - category: always present, one of "tactical"/"time"/"defense"/
      "matchup"/"giant_killer"/"general" -- a coarse tag for grouping/
      filtering, not used for ranking.
    - confidence: "insufficient"/"low"/"medium"/"high", present only where
      a natural sample-size gate already existed for that finding (absent
      from _giant_killing, _tactical_highlights, _game_endings).
    - polarity: "strength"/"weakness"/"mixed"/"neutral", always present --
      "mixed" for findings that already bundle a good and a bad data point
      into one card (_thinking_time, _time_pressure, _giant_killing),
      "neutral" for purely informational round-ups/distributions with no
      "worse" direction (_tactical_highlights, _game_endings), otherwise
      "strength" or "weakness" per that finding's own data.

    sqlite_conn is needed only by _bishop_color_endings (it calls
    analytics.ensure_structure_ctx, which requires a real sqlite
    connection, not a DuckDB one) -- every other finding is duck_conn-only,
    same as before this parameter was added."""
    moves_df = _fetch_move_correlates(duck_conn)
    candidates = [
        _piece_hotspot(moves_df, baseline_blunder_rate),
        _safest_piece(moves_df, baseline_blunder_rate),
        _sharpness(moves_df),
        _thinking_time(moves_df),
        _time_pressure(moves_df),
        _castling(duck_conn, config_path),
        _backrank(moves_df),
        _nemesis(duck_conn),
        _best_matchup(duck_conn),
        _giant_killing(duck_conn),
        _tactical_highlights(duck_conn, moves_df, config_path),
        _game_endings(duck_conn),
        _bishop_color_endings(duck_conn, sqlite_conn, config_path),
    ]
    return [f for f in candidates if f is not None]
