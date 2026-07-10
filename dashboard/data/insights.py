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

PIECE_MOVES_THRESHOLDS = default_thresholds(MIN_PIECE_MOVES)
BUCKET_MOVES_THRESHOLDS = default_thresholds(MIN_BUCKET_MOVES)
BACKRANK_MOVES_THRESHOLDS = default_thresholds(MIN_BACKRANK_MOVES)
OPPONENT_GAMES_THRESHOLDS = default_thresholds(MIN_OPPONENT_GAMES)
CASTLE_GAMES_THRESHOLDS = default_thresholds(MIN_CASTLE_GAMES)

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
    return {
        "title": "Sharp positions and blunder rate",
        "headline": f"Blunder rate climbs from {flat.blunder_rate:.1f}% to {forcing.blunder_rate:.1f}%",
        "detail": f"Comparing your flattest positions ({flat.bucket}) to your most forcing "
                  f"ones ({forcing.bucket}) -- sharpness is how much the best move beats the "
                  f"second-best, a high gap meaning only one move was actually good.",
        "confidence": confidence_tier(min(flat.n_moves, forcing.n_moves), BUCKET_MOVES_THRESHOLDS),
        "severity": confidence_tier(forcing.blunder_rate - flat.blunder_rate, BLUNDER_GAP_SEVERITY_THRESHOLDS),
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
        "category": "general",
    }


def get_career_findings(duck_conn, baseline_blunder_rate, config_path=None):
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
      from _giant_killing, _tactical_highlights, _game_endings)."""
    moves_df = _fetch_move_correlates(duck_conn)
    candidates = [
        _piece_hotspot(moves_df, baseline_blunder_rate),
        _sharpness(moves_df),
        _thinking_time(moves_df),
        _time_pressure(moves_df),
        _castling(duck_conn, config_path),
        _backrank(moves_df),
        _nemesis(duck_conn),
        _giant_killing(duck_conn),
        _tactical_highlights(duck_conn, moves_df, config_path),
        _game_endings(duck_conn),
    ]
    return [f for f in candidates if f is not None]
