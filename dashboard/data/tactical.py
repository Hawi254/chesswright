"""Tactical Highlights page queries -- puzzle sequences, brilliant
candidates, best-move streaks, blown forced mates, knight-on-the-rim,
hallucinated hanging-piece blunders.
"""
import pandas as pd

import analytics
from connections import get_config

from ._shared import TIME_PRESSURE_BUCKETS, THINKING_TIME_BUCKETS
from .game_explorer import get_position_and_lastmove

RIM_SQL = "(substr(to_square,1,1) IN ('a','h') OR substr(to_square,2,1) IN ('1','8'))"


def get_puzzle_sequences(duck_conn, top_n=15):
    """Mirrors analysis/puzzle_summary.py's trigger half -- 191 sequences
    computed in Phase 3b, never surfaced anywhere including the
    dashboard until now.

    top_n=None returns every qualifying row (the trigger flag bounds this
    to a few hundred rows) -- used by the view layer to cache ONE full
    fetch per session and slice per slider value in pandas, instead of
    re-running this full-table duck scan (~0.65s on the real 2.3M-row
    moves table) on every distinct top_n slider position."""
    limit = "" if top_n is None else "LIMIT ?"
    params = [] if top_n is None else [top_n]
    return duck_conn.execute(f"""
        SELECT game_id, ply, san, classification, is_player_move, puzzle_sequence_length
        FROM db.moves WHERE is_puzzle_trigger=1
        ORDER BY puzzle_sequence_length DESC {limit}
    """, params).fetchdf()


def get_brilliant_candidates(duck_conn, top_n=15):
    """Mirrors analysis/puzzle_summary.py's brilliant half -- 146
    candidates computed in Phase 3b, never surfaced anywhere including
    the dashboard until now.

    top_n=None returns every qualifying row -- same fetch-once/slice-in-
    pandas contract as get_puzzle_sequences above."""
    limit = "" if top_n is None else "LIMIT ?"
    params = [] if top_n is None else [top_n]
    return duck_conn.execute(f"""
        SELECT game_id, ply, san, material_delta FROM db.moves
        WHERE is_brilliant_candidate=1 {limit}
    """, params).fetchdf()


def get_best_move_streaks(duck_conn, top_n=15, min_unforced=1):
    """New feature (2026-06): best-move streaks -- the player matching the
    engine's literal top move for 3+ consecutive own turns, computed by
    annotate.py. Every qualifying row already has
    best_move_streak_unforced_count >= 1 by construction (a streak's
    FIRST move must itself be "unforced" -- a real choice, not the only
    sensible move -- to qualify at all); min_unforced raises that bar
    further, toward "every move in the streak was a real choice," not
    just the minimum required to qualify.

    top_n=None returns every qualifying row -- the view layer caches one
    full fetch at min_unforced=1 (the qualifying minimum, so a superset
    of every stricter setting) and applies both sliders in pandas."""
    limit = "" if top_n is None else "LIMIT ?"
    params = [min_unforced] if top_n is None else [min_unforced, top_n]
    return duck_conn.execute(f"""
        SELECT game_id, ply, san, is_player_move, best_move_streak_length,
               best_move_streak_unforced_count
        FROM db.moves
        WHERE is_best_move_streak_trigger=1 AND best_move_streak_unforced_count >= ?
        ORDER BY best_move_streak_length DESC {limit}
    """, params).fetchdf()


def get_blown_mates(duck_conn):
    """New query (not in any analysis/*.py script -- first computed
    during the Phase 5 gap-analysis report). A forced mate was available
    (eval_mate>0 before the player's move) but the player deviated from
    the engine's mating line. Most of these still won eventually (just a
    less efficient mate); the truly dramatic subset is the 3 that ended
    in an outright loss despite a forced mate having been on the board."""
    df = duck_conn.execute("""
        SELECT m.game_id, m.ply, m.san, m.best_move_san, m.eval_mate, g.outcome_for_player
        FROM db.moves m JOIN db.games g ON g.id = m.game_id
        WHERE m.is_player_move=1 AND m.eval_mate IS NOT NULL AND m.eval_mate > 0
          AND m.san != m.best_move_san
        ORDER BY g.outcome_for_player = 'loss' DESC, m.eval_mate DESC
    """).fetchdf()
    return df


def get_knight_rim_performance(sqlite_conn, config_path=None):
    """Mirrors analysis/knight_rim_performance.py -- "a knight on the rim
    is dim" tested directly, by game phase. Found the proverb holds in
    the opening/middlegame but flips in the endgame (interior moves
    riskier there, 8.3% vs. 5.8% -- a thin 69-move rim-endgame cell).
    Returns (overall_df, phase_df)."""
    cfg = get_config(config_path)
    analytics.ensure_structure_ctx(sqlite_conn, cfg)
    middlegame_ply = cfg["analytics"]["middlegame_ply"]

    overall_rows = sqlite_conn.execute(f"""
        SELECT {RIM_SQL} AS is_rim, COUNT(*) AS n_moves, AVG(cpl) AS acpl,
               100.0 * SUM(CASE WHEN classification='blunder' THEN 1 ELSE 0 END) / COUNT(*) AS blunder_rate
        FROM moves
        WHERE is_player_move=1 AND piece='N' AND cpl IS NOT NULL AND to_square IS NOT NULL
        GROUP BY is_rim
    """).fetchall()
    overall_df = pd.DataFrame(overall_rows, columns=["is_rim", "n_moves", "acpl", "blunder_rate"])
    overall_df["location"] = overall_df.is_rim.map({1: "rim", 0: "interior"})

    phase_rows = sqlite_conn.execute(f"""
        SELECT {RIM_SQL} AS is_rim,
               CASE WHEN m.ply < {middlegame_ply} THEN 'opening'
                    WHEN sc.endgame_ply IS NULL OR m.ply < sc.endgame_ply THEN 'middlegame'
                    ELSE 'endgame' END AS phase,
               COUNT(*) AS n_moves, AVG(m.cpl) AS acpl,
               100.0 * SUM(CASE WHEN m.classification='blunder' THEN 1 ELSE 0 END) / COUNT(*) AS blunder_rate
        FROM moves m JOIN structure_ctx sc ON sc.game_id = m.game_id
        WHERE m.is_player_move=1 AND m.piece='N' AND m.cpl IS NOT NULL AND m.to_square IS NOT NULL
        GROUP BY is_rim, phase
    """).fetchall()
    phase_df = pd.DataFrame(phase_rows, columns=["is_rim", "phase", "n_moves", "acpl", "blunder_rate"])
    phase_df["location"] = phase_df.is_rim.map({1: "rim", 0: "interior"})
    return overall_df, phase_df


def get_motif_breakdown(sqlite_conn):
    """Frequency and avg CPL for each tactical motif the player missed.

    Only covers is_player_move=1 moves classified mistake/blunder where
    annotate.py's Pass 4 was able to identify a motif. Returns an empty
    DataFrame (not None) when no motifs have been classified yet.

    Takes sqlite_conn, not duck_conn -- idx_moves_motif (partial index,
    migration 0031, needs ANALYZE stats to be chosen) makes this a ~4ms
    seek over the ~1.2k motif-bearing rows, vs ~0.5s as a full
    SQLITE_SCAN of all of moves via duck_conn.
    """
    return pd.read_sql_query("""
        SELECT
            motif,
            COUNT(*)                                                                  AS n_missed,
            COUNT(DISTINCT game_id)                                                   AS n_games,
            AVG(cpl)                                                                  AS avg_cpl,
            100.0 * SUM(CASE WHEN classification='blunder' THEN 1 ELSE 0 END)
                  / COUNT(*)                                                           AS blunder_pct
        FROM moves
        WHERE is_player_move = 1
          AND motif IS NOT NULL
          AND classification IN ('mistake', 'blunder')
        GROUP BY motif
        ORDER BY n_missed DESC
    """, sqlite_conn)


# Minimum number of mistake/blunder candidates before an all-zero motif
# count is trusted as "annotation predates motif classification" rather
# than "coincidentally none of a handful of blunders matched a pattern" --
# classify_motif() legitimately returns None for plenty of real blunders
# (anything that isn't a clean fork/pin/skewer/discovery/hanging
# piece/back-rank mate), so zero motifs on a small sample isn't unusual on
# its own. Zero motifs across dozens+ of candidates is not a coincidence.
MOTIF_BACKFILL_MIN_CANDIDATES = 20


def motif_backfill_needed(duck_conn) -> bool:
    """True when this database has real mistake/blunder moves that were
    never run through motif classification at all -- i.e. games analyzed
    before annotate.py's Pass 4 (v0.1.9) existed, and never re-annotated
    since. annotate.run(game_id=None) already recomputes motif for every
    previously-analyzed game (idempotent, see annotate.py's
    fetch_games_to_annotate), so this is purely a detection signal for the
    empty state -- the fix already exists, it just needs to be reachable
    and correctly explained."""
    row = duck_conn.execute("""
        SELECT
            COUNT(*)                                            AS n_candidates,
            SUM(CASE WHEN motif IS NOT NULL THEN 1 ELSE 0 END)  AS n_with_motif
        FROM db.moves
        WHERE is_player_move = 1 AND classification IN ('mistake', 'blunder')
    """).fetchone()
    if row is None:
        return False
    n_candidates, n_with_motif = row
    return n_candidates >= MOTIF_BACKFILL_MIN_CANDIDATES and not n_with_motif


def get_hallucination_blunders(duck_conn, config_path=None):
    """Mirrors analysis/hallucination_blunders.py -- detects hanging a
    real piece (player move classified 'blunder', opponent's IMMEDIATE
    next move recaptures on the exact same square for >=
    hallucination_min_material_delta) and flags whether it was followed
    by a quick resignation. One row per hanging-piece blunder; the view
    layer derives the resilience breakdown and example lists from this
    directly rather than re-querying."""
    cfg = get_config(config_path)
    min_material_delta = cfg["analytics"]["hallucination_min_material_delta"]
    max_moves_to_resign = cfg["analytics"]["hallucination_max_moves_to_resign"]
    max_plies_to_resign = max_moves_to_resign * 2

    hangs = duck_conn.execute(f"""
        SELECT m.game_id, m.ply AS blunder_ply, m.san AS blunder_san,
               g.num_plies, g.outcome_for_player, g.game_end_type,
               g.num_plies - m.ply AS plies_remaining
        FROM db.moves m
        JOIN db.moves m2 ON m2.game_id = m.game_id AND m2.ply = m.ply + 1
        JOIN db.games g ON g.id = m.game_id
        WHERE m.is_player_move = 1 AND m.classification = 'blunder' AND m.cpl IS NOT NULL
          AND m2.is_capture = 1 AND m2.to_square = m.to_square
          AND m2.material_delta >= {min_material_delta}
    """).fetchdf()
    if len(hangs):
        hangs["resigned_quickly"] = (
            (hangs.outcome_for_player == "loss") & (hangs.game_end_type == "resignation") &
            (hangs.plies_remaining <= max_plies_to_resign))
    return hangs


def get_hallucination_context(duck_conn, hangs):
    """Mirrors analysis/hallucination_context.py -- resolves "hallucination
    vs. mouse-slip" using time_spent_seconds on the blundering move, and
    checks whether hangs are concentrated under time pressure. Compares
    against the baseline of ALL analyzed player blunders. Found these are
    genuine hallucinations (NOT skewed toward instant/careless moves) and
    NOT concentrated under time pressure. Returns (time_spent_df, time_pressure_df).

    Takes the already-fetched `hangs` DataFrame (from get_hallucination_blunders)
    rather than re-querying it -- that self-join is the most expensive part
    of this whole panel (~1.3-1.5s), and the view layer already has it
    cached separately; re-running it here would cost that twice per page
    load for no reason."""
    if len(hangs) == 0:
        empty = pd.DataFrame(columns=["bucket", "hang_pct", "baseline_pct"])
        return empty, empty

    detail = duck_conn.execute("""
        SELECT m.game_id, m.ply, m.time_spent_seconds,
               CAST(m.clock_seconds AS DOUBLE) / g.base_seconds AS time_fraction
        FROM db.moves m JOIN db.games g ON g.id = m.game_id
        WHERE m.is_player_move=1 AND m.classification='blunder' AND m.cpl IS NOT NULL
    """).fetchdf()
    hangs_keyed = hangs.merge(
        detail, left_on=["game_id", "blunder_ply"], right_on=["game_id", "ply"], how="left")

    def bucket_compare(hang_vals, baseline_vals, buckets):
        rows = []
        for label, lo, hi in buckets:
            hang_n = int(((hang_vals >= lo) & (hang_vals < hi)).sum())
            base_n = int(((baseline_vals >= lo) & (baseline_vals < hi)).sum())
            hang_pct = 100.0 * hang_n / len(hang_vals) if len(hang_vals) else 0.0
            base_pct = 100.0 * base_n / len(baseline_vals) if len(baseline_vals) else 0.0
            rows.append((label, hang_n, hang_pct, base_n, base_pct))
        return pd.DataFrame(rows, columns=["bucket", "hang_n", "hang_pct", "baseline_n", "baseline_pct"])

    time_spent_df = bucket_compare(hangs_keyed.time_spent_seconds.dropna(),
                                   detail.time_spent_seconds.dropna(), THINKING_TIME_BUCKETS)
    time_pressure_df = bucket_compare(hangs_keyed.time_fraction.dropna(),
                                      detail.time_fraction.dropna(), TIME_PRESSURE_BUCKETS)
    return time_spent_df, time_pressure_df


CATEGORY_CAP = 15

# Scaling caps for the 0-1 "strength" used to interleave 5 different units
# in the 'All' view -- a heuristic, same spirit as Game Explorer's
# drama_score, not held to a higher bar. Not the observed max in this DB,
# so strength stays stable across accounts.
_STRENGTH_CAPS = {
    "brilliant": 900.0,           # a queen, in centipawns (see POINT_VALUE below)
    "puzzle_conversion": 10.0,    # sequence length
    "best_move_streak": 12.0,     # streak length
    "blown_mate": 10.0,           # mate-in depth
    "great_escape": 20.0,         # plies survived
}

# cp values confirmed live against material_delta on real brilliant-
# candidate rows' next-ply recapture (900/500/300) -- standard piece
# values, same scale as chess_utils.POINT_VALUE. Knight and bishop are
# both 300 and indistinguishable from cp alone, hence "a minor piece."
_MATERIAL_PHRASE_BY_CP = {900: "a queen", 500: "a rook", 300: "a minor piece", 100: "a pawn"}


def _material_phrase(cp):
    return _MATERIAL_PHRASE_BY_CP.get(cp, "material")


def _capitalized_material_name(phrase):
    # phrase is "a rook"/"a queen"/"a minor piece"/"a pawn"/"material" --
    # str.capitalize() alone would give "A rook", not "Rook", since it
    # capitalizes the phrase's own first letter (the article), not the
    # noun after it.
    name = phrase[2:] if phrase.startswith("a ") else phrase
    return name[:1].upper() + name[1:]


def _won_or_drew(outcome_for_player):
    return "won" if outcome_for_player == "win" else "drew"


def _caption_and_label(category, row):
    move = int(row["move_number"])
    magnitude = row["magnitude"]
    if category == "brilliant":
        phrase = _material_phrase(magnitude)
        return (f"Sacrificed {phrase} on move {move} — it worked.",
                f"{_capitalized_material_name(phrase)} sacrifice")
    if category == "puzzle_conversion":
        n = int(magnitude)
        return (f"{row['opponent_name']} blundered on move {move} — "
                f"{n} accurate replies in a row closed it out.",
                f"{n} in a row")
    if category == "best_move_streak":
        n = int(magnitude)
        return (f"Matched the engine's top move {n} times running, starting move {move}.",
                f"{n}-move streak")
    if category == "blown_mate":
        n = int(magnitude)
        return (f"Mate in {n} was on the board at move {move} — played something else, lost anyway.",
                f"Mate in {n}")
    n = int(magnitude)  # great_escape
    return (f"Hung a piece on move {move} — survived {n} more moves and "
            f"{_won_or_drew(row['outcome_for_player'])} anyway.",
            f"{n} plies survived")


def _brilliant_rows(duck_conn, top_n=CATEGORY_CAP):
    """A real sacrifice's magnitude is invisible on the flagged move's OWN
    material_delta (always < brilliant_threshold by construction -- see
    annotate.py's detect_best_move_streaks-adjacent brilliant-flagging
    logic) -- it shows up as the OPPONENT's next-ply recapture on the
    same square. Confirmed live against the real dev DB: this self-join's
    material_delta takes exactly the standard piece values (900/500/300),
    unlike is_brilliant_candidate rows' own material_delta (0 or 100
    only). Does its own query rather than calling get_brilliant_candidates
    -- that function's material_delta column is the wrong field for this
    purpose. Real dev DB has 198 rows tied at the max value (900, a queen)
    out of 1279 qualifying rows -- ORDER BY material_delta alone leaves
    LIMIT to pick an arbitrary subset of the tie on every call (found live:
    two identical requests returned different games in the same slot).
    game_id/move_number break the tie deterministically so the same 15
    rows are returned every time, matching every other category here
    (none of which has a tie anywhere near this wide at the cutoff)."""
    return duck_conn.execute("""
        SELECT m.game_id, m.move_number, m.san, m.fen_before,
               m.from_square AS lastmove_from, m.to_square AS lastmove_to,
               m2.material_delta AS magnitude,
               g.opponent_name, g.utc_date, g.outcome_for_player, g.player_color
        FROM db.moves m
        JOIN db.moves m2 ON m2.game_id = m.game_id AND m2.ply = m.ply + 1
        JOIN db.games g ON g.id = m.game_id
        WHERE m.is_brilliant_candidate = 1
        ORDER BY m2.material_delta DESC, m.game_id, m.move_number
        LIMIT ?
    """, [top_n]).fetchdf()


def _puzzle_conversion_rows(duck_conn, top_n=CATEGORY_CAP):
    """Narrows get_puzzle_sequences to is_player_move=0 -- the opponent
    blundered, the player converted -- the reel-worthy half; the other
    half (player's own blunder, still narrowly a 'trigger') is diagnostic,
    not reel material (spec's Non-goals)."""
    return duck_conn.execute("""
        SELECT m.game_id, m.move_number, m.san, m.fen_before,
               m.from_square AS lastmove_from, m.to_square AS lastmove_to,
               m.puzzle_sequence_length AS magnitude,
               g.opponent_name, g.utc_date, g.outcome_for_player, g.player_color
        FROM db.moves m JOIN db.games g ON g.id = m.game_id
        WHERE m.is_puzzle_trigger = 1 AND m.is_player_move = 0
        ORDER BY m.puzzle_sequence_length DESC
        LIMIT ?
    """, [top_n]).fetchdf()


def _best_move_streak_rows(duck_conn, top_n=CATEGORY_CAP):
    """Same unforced_count>=1 qualifying floor get_best_move_streaks
    already applies by construction (is_best_move_streak_trigger=1 implies
    it); the trigger row IS the streak's first ply (annotate.py's
    detect_best_move_streaks anchors one row per streak at its start), so
    'starting move' in the caption is this row's own move_number, no
    offset math needed."""
    return duck_conn.execute("""
        SELECT m.game_id, m.move_number, m.san, m.fen_before,
               m.from_square AS lastmove_from, m.to_square AS lastmove_to,
               m.best_move_streak_length AS magnitude,
               g.opponent_name, g.utc_date, g.outcome_for_player, g.player_color
        FROM db.moves m JOIN db.games g ON g.id = m.game_id
        WHERE m.is_best_move_streak_trigger = 1 AND m.best_move_streak_unforced_count >= 1
        ORDER BY m.best_move_streak_length DESC
        LIMIT ?
    """, [top_n]).fetchdf()


def _blown_mate_rows(duck_conn, top_n=CATEGORY_CAP):
    """Narrows get_blown_mates to outcome_for_player='loss' only -- the
    truly dramatic subset where the missed mate cost the game (most blown
    mates still won eventually, just less efficiently)."""
    return duck_conn.execute("""
        SELECT m.game_id, m.move_number, m.san, m.fen_before,
               m.from_square AS lastmove_from, m.to_square AS lastmove_to,
               m.eval_mate AS magnitude,
               g.opponent_name, g.utc_date, g.outcome_for_player, g.player_color
        FROM db.moves m JOIN db.games g ON g.id = m.game_id
        WHERE m.is_player_move = 1 AND m.eval_mate IS NOT NULL AND m.eval_mate > 0
          AND m.san != m.best_move_san AND g.outcome_for_player = 'loss'
        ORDER BY m.eval_mate DESC
        LIMIT ?
    """, [top_n]).fetchdf()


def _great_escape_rows(duck_conn, sqlite_conn, config_path=None, top_n=CATEGORY_CAP):
    """Narrows get_hallucination_blunders to resigned_quickly=False AND a
    win/draw outcome -- survived the hung piece and it didn't cost the
    game. Reuses get_hallucination_blunders as-is (its resigned_quickly
    column, config-driven thresholds, and self-join are non-trivial to
    re-derive) -- does NOT call get_hallucination_context, which computes
    unrelated time-pressure breakdowns and never touches resigned_quickly.
    get_hallucination_blunders doesn't join games or select fen/squares,
    so those are attached here: opponent_name/utc_date via one small
    IN-list query on the already-narrowed ≤15 game_ids, fen/squares/
    move_number via one point lookup per row (cheap -- see
    get_position_and_lastmove's docstring)."""
    hangs = get_hallucination_blunders(duck_conn, config_path)
    if len(hangs) == 0 or "resigned_quickly" not in hangs.columns:
        return pd.DataFrame(columns=[
            "game_id", "move_number", "san", "fen_before", "lastmove_from",
            "lastmove_to", "magnitude", "opponent_name", "utc_date",
            "outcome_for_player", "player_color"])

    # resigned_quickly's own formula (tactical.py's get_hallucination_blunders)
    # is only ever True when outcome_for_player=='loss', so it's structurally
    # always False on a win/draw row -- the isin(["win", "draw"]) filter
    # alone is what actually excludes rows here. The ~resigned_quickly term
    # is kept anyway to match the spec's stated narrowing rule verbatim and
    # stay correct if that formula's definition ever changes.
    narrowed = hangs[
        (~hangs["resigned_quickly"]) & hangs["outcome_for_player"].isin(["win", "draw"])
    ].sort_values("plies_remaining", ascending=False).head(top_n).copy()
    if len(narrowed) == 0:
        return pd.DataFrame(columns=[
            "game_id", "move_number", "san", "fen_before", "lastmove_from",
            "lastmove_to", "magnitude", "opponent_name", "utc_date",
            "outcome_for_player", "player_color"])

    game_ids = narrowed["game_id"].unique().tolist()
    placeholders = ",".join("?" * len(game_ids))
    games_df = duck_conn.execute(
        f"SELECT id AS game_id, opponent_name, utc_date, player_color "
        f"FROM db.games WHERE id IN ({placeholders})", game_ids).fetchdf()
    merged = narrowed.merge(games_df, on="game_id", how="left")
    merged["magnitude"] = merged["plies_remaining"]

    fens, froms, tos, move_numbers = [], [], [], []
    for _, row in merged.iterrows():
        snapshot = get_position_and_lastmove(sqlite_conn, row["game_id"], int(row["blunder_ply"]))
        fen, frm, to, move_number = snapshot if snapshot else (None, None, None, None)
        fens.append(fen)
        froms.append(frm)
        tos.append(to)
        move_numbers.append(move_number)
    merged["fen_before"] = fens
    merged["lastmove_from"] = froms
    merged["lastmove_to"] = tos
    merged["move_number"] = move_numbers
    merged["san"] = merged["blunder_san"]
    return merged


def build_highlight_reel(sqlite_conn, duck_conn, config_path=None):
    """Merges the 5 narrowed highlight queries into one ranked reel. Each
    row gets a category tag, a fen+arrow for a static board thumbnail, a
    rendered one-line caption, and a 0-1 strength for interleaving in the
    'All' view. Capped at CATEGORY_CAP rows per category before merge.

    No caching layer -- this data only changes after a new analysis batch
    finishes, and every underlying query is already bounded (top_n=15 or
    a narrow join), matching e.g. /api/matchups/nemesis's uncached style."""
    frames = {
        "brilliant": _brilliant_rows(duck_conn),
        "puzzle_conversion": _puzzle_conversion_rows(duck_conn),
        "best_move_streak": _best_move_streak_rows(duck_conn),
        "blown_mate": _blown_mate_rows(duck_conn),
        "great_escape": _great_escape_rows(duck_conn, sqlite_conn, config_path),
    }

    moments = []
    counts = {}
    for category, df in frames.items():
        counts[category] = len(df)
        cap = _STRENGTH_CAPS[category]
        for _, row in df.iterrows():
            caption, magnitude_label = _caption_and_label(category, row)
            magnitude = float(row["magnitude"])
            moments.append({
                "game_id": row["game_id"],
                "category": category,
                "move_number": int(row["move_number"]),
                "san": row["san"],
                "magnitude": magnitude,
                "magnitude_label": magnitude_label,
                "strength": min(magnitude / cap, 1.0),
                "caption": caption,
                "opponent_name": row.get("opponent_name"),
                "utc_date": row.get("utc_date"),
                "outcome_for_player": row.get("outcome_for_player"),
                "player_color": row.get("player_color"),
                "fen": row.get("fen_before"),
                "lastmove_from": row.get("lastmove_from"),
                "lastmove_to": row.get("lastmove_to"),
            })
    return {"moments": moments, "counts": counts}
