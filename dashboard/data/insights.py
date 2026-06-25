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
from . import patterns, tactical, matchups, game_endings
from ._shared import TIME_PRESSURE_BUCKETS, THINKING_TIME_BUCKETS, bucket_acpl_blunder_rate

# Minimum sample sizes below are deliberately conservative and ad hoc --
# there's no statistical test here, just "enough rows that one outlier
# move/game can't dominate the number," consistent with how thin a
# starter dataset (BRIEF.md Phase B) is expected to be early on.
MIN_PIECE_MOVES = 20
MIN_BUCKET_MOVES = 20
MIN_BACKRANK_MOVES = 20
MIN_OPPONENT_GAMES = 5
MIN_CASTLE_GAMES = 5


def _fetch_move_correlates(duck_conn):
    """One scan of the moves table backing the four findings below (piece
    hot-spot, sharpness, thinking-time, clock-pressure) -- each used to
    independently re-run patterns.py's own query, all four starting from
    the exact same "is_player_move=1 AND cpl IS NOT NULL" base set and
    only differing in which extra column they bucket by. Measured at
    ~10-12s for this page alone against a real ~32k-game/1,497-analyzed
    database (vs ~3-4s for any single other page) before this change --
    the moves table is by far the largest in the schema, so collapsing
    four full scans into one is the single biggest win available without
    touching patterns.py's own functions (Patterns & Tendencies and
    Tactical Highlights still call those individually, unchanged)."""
    return duck_conn.execute("""
        SELECT m.cpl, m.classification, m.piece, m.sharpness, m.time_spent_seconds,
               m.clock_seconds, g.base_seconds
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
    grouped = grouped[grouped.n_moves >= MIN_PIECE_MOVES]
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
    }


def _sharpness(moves_df):
    df = moves_df.dropna(subset=["sharpness"])
    bucketed = bucket_acpl_blunder_rate(df, "sharpness", patterns.SHARPNESS_BUCKETS)
    bucketed = bucketed[bucketed.n_moves >= MIN_BUCKET_MOVES]
    if len(bucketed) < 2:
        return None
    flat, forcing = bucketed.iloc[0], bucketed.iloc[-1]
    return {
        "title": "Sharp positions and blunder rate",
        "headline": f"Blunder rate climbs from {flat.blunder_rate:.1f}% to {forcing.blunder_rate:.1f}%",
        "detail": f"Comparing your flattest positions ({flat.bucket}) to your most forcing "
                  f"ones ({forcing.bucket}) -- sharpness is how much the best move beats the "
                  f"second-best, a high gap meaning only one move was actually good.",
    }


def _thinking_time(moves_df):
    df = moves_df[moves_df.time_spent_seconds.notna() & (moves_df.time_spent_seconds >= 0)]
    bucketed = bucket_acpl_blunder_rate(df, "time_spent_seconds", THINKING_TIME_BUCKETS)
    bucketed = bucketed[bucketed.n_moves >= MIN_BUCKET_MOVES]
    if len(bucketed) < 2:
        return None
    worst = bucketed.loc[bucketed.blunder_rate.idxmax()]
    best = bucketed.loc[bucketed.blunder_rate.idxmin()]
    return {
        "title": "Thinking time vs. blunder rate",
        "headline": f"Your worst blunder rate ({worst.blunder_rate:.1f}%) is on \"{worst.bucket}\" moves",
        "detail": f"Your best ({best.blunder_rate:.1f}%) is on \"{best.bucket}\" moves -- "
                  f"not always the slowest bucket that's safest.",
    }


def _time_pressure(moves_df):
    df = moves_df.dropna(subset=["clock_seconds", "base_seconds"])
    df = df[df.base_seconds > 0]
    if df.empty:
        return None
    df = df.copy()
    df["time_fraction"] = df.clock_seconds / df.base_seconds
    bucketed = bucket_acpl_blunder_rate(df, "time_fraction", TIME_PRESSURE_BUCKETS)
    bucketed = bucketed[bucketed.n_moves >= MIN_BUCKET_MOVES]
    if len(bucketed) < 2:
        return None
    worst = bucketed.loc[bucketed.blunder_rate.idxmax()]
    best = bucketed.loc[bucketed.blunder_rate.idxmin()]
    return {
        "title": "Clock pressure and blunder rate",
        "headline": f"Blunder rate peaks at {worst.blunder_rate:.1f}% with \"{worst.bucket}\" clock left",
        "detail": f"vs. {best.blunder_rate:.1f}% with \"{best.bucket}\" clock left.",
    }


def _castling(duck_conn, config_path=None):
    win_df, _acpl_df = patterns.get_castling_performance(duck_conn, config_path=config_path)
    if win_df.empty or len(win_df) < 2 or (win_df.n_games < MIN_CASTLE_GAMES).any():
        return None
    castled = win_df[win_df.status == "castled"].iloc[0]
    not_castled = win_df[win_df.status == "did not castle"].iloc[0]
    return {
        "title": "Castling and win rate",
        "headline": f"{castled.win_pct:.1f}% win rate when you castle",
        "detail": f"vs. {not_castled.win_pct:.1f}% in games where you don't, "
                  f"in games long enough for castling to be a real option.",
    }


def _backrank(duck_conn):
    df = patterns.get_rook_king_backrank_performance(duck_conn)
    df = df[df.n_moves >= MIN_BACKRANK_MOVES]
    if df.empty:
        return None
    king = df[df.piece == "K"]
    if len(king) < 2:
        return None
    back = king[king.is_back_rank].iloc[0]
    elsewhere = king[~king.is_back_rank].iloc[0]
    return {
        "title": "King moves off the back rank",
        "headline": f"King ACPL off the back rank: {elsewhere.acpl:.1f}",
        "detail": f"vs. {back.acpl:.1f} on the back rank -- the average centipawn loss per move.",
    }


def _nemesis(duck_conn):
    df = matchups.get_nemesis_opponents(duck_conn, min_games=MIN_OPPONENT_GAMES)
    if df.empty:
        return None
    toughest = df.loc[df.score_pct.idxmin()]
    return {
        "title": "Toughest opponent",
        "headline": f"{toughest.score_pct:.1f}% score against {toughest.opponent_name}",
        "detail": f"Over {int(toughest.n)} games (win + 0.5 x draw, standard tournament scoring).",
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
    return {
        "title": "Giant-killing and collapses",
        "headline": f"{gk['n_upsets']} upset win(s) on record",
        "detail": " and ".join(parts) + ".",
    }


def _tactical_highlights(duck_conn):
    brilliant = tactical.get_brilliant_candidates(duck_conn, top_n=10**9)
    hangs = tactical.get_hallucination_blunders(duck_conn)
    blown = tactical.get_blown_mates(duck_conn)
    n_brilliant, n_hangs, n_blown_loss = (
        len(brilliant), len(hangs), int((blown.outcome_for_player == "loss").sum()) if len(blown) else 0)
    if not (n_brilliant or n_hangs or n_blown_loss):
        return None
    return {
        "title": "Tactical highlights so far",
        "headline": f"{n_brilliant} brilliant-move candidate(s) found",
        "detail": f"{n_hangs} hanging-piece blunder(s), {n_blown_loss} forced mate(s) blown "
                  f"and lost anyway.",
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
    }


def get_career_findings(duck_conn, baseline_blunder_rate, config_path=None):
    """Returns a list of {title, headline, detail} dicts, one per finding
    that currently has enough data to say something -- order is the
    fixed display order, not a ranking by "significance" (no principled
    way to rank across domains this different)."""
    moves_df = _fetch_move_correlates(duck_conn)
    candidates = [
        _piece_hotspot(moves_df, baseline_blunder_rate),
        _sharpness(moves_df),
        _thinking_time(moves_df),
        _time_pressure(moves_df),
        _castling(duck_conn, config_path),
        _backrank(duck_conn),
        _nemesis(duck_conn),
        _giant_killing(duck_conn),
        _tactical_highlights(duck_conn),
        _game_endings(duck_conn),
    ]
    return [f for f in candidates if f is not None]
