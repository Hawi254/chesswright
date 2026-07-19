"""Drill-position queries built on the points ledger: failed-conversion
cause classification and the Conversion/Defense trainer drill sources --
the other topic module split out of the former dashboard/data/points.py.
"""
import pandas as pd

from _common import get_config

from .._shared import TIME_PRESSURE_BUCKETS
from ..game_endings import MATE_DISTANCE_BUCKETS
from .ledger import EVEN_WP, get_points_ledger, classify_points_ledger


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
