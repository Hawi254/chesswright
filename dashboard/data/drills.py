"""Drill position queries: tactical motif misses and decisive turning-point positions.

Repertoire hole positions live in openings.py (get_repertoire_holes already returns
fen_before / most_played_san). Callers can rename most_played_san → best_move_san
and pass that DataFrame alongside these results to drills_to_pgn_study / drills_to_anki_csv.

build_drill_cards() is the one place the drill sources become SRS card
dicts -- extracted from srs_drill_view's Manage Queue tab (BRIEF §6q) so
Coach Mode's drill assignment (Pro) builds a student's cards through the
IDENTICAL code path against the student's connections, instead of
re-implementing the source collection a second time. It also retired
srs_drill_view._context_str, a near-duplicate of
chess_display._drill_context that had already drifted in label wording.

build_drill_cards takes a `sources: set[str]` (see _SOURCE_ORDER below)
rather than one bool param per source -- the prior include_motifs/
include_moments/include_holes/include_endgame_moments shape silently
drifted out of sync the moment a 4th source (Endgame Trainer) shipped:
chesswright_pro/coach_view.py's assign-to-student caller kept passing
only the original 3 kwargs and never picked up include_endgame_moments.
A single explicit set forces every caller to state its sources, so a new
source can never again go silently missing from an existing call site.
"""
import pandas as pd

import analytics
import chess_utils
from chess_display import _drill_context
from _common import get_config

from ._shared import GIANT_KILLING_COLLAPSE_THRESHOLD, TIME_PRESSURE_BUCKETS
from .openings import get_repertoire_holes

# Ordered list of valid build_drill_cards() source keys, and the display
# label each produces on a card's "source" field. Order is meaningful --
# it is the collection order in build_drill_cards, which in turn decides
# which label wins when add_cards() dedupes by UNIQUE(fen) (INSERT OR
# IGNORE: first occurrence in the list wins). Leave room to append new
# keys here as future trainers (Conversion, Defense) land -- nothing else
# in this module hardcodes the list's length.
_SOURCE_ORDER = ["motifs", "endgame_moments", "collapse_moments", "time_pressure", "moments", "holes"]
_SOURCE_LABELS = {
    "motifs": "Missed Tactics",
    "endgame_moments": "Endgame Turning Point",
    "collapse_moments": "Collapse",
    "time_pressure": "Time Pressure",
    "moments": "Decisive Moment",
    "holes": "Repertoire Hole",
}


def drill_source_options() -> list[tuple[str, str]]:
    """(key, label) pairs in _SOURCE_ORDER order -- for UI layers building
    a source picker (e.g. a multiselect over labels) without duplicating
    _SOURCE_ORDER/_SOURCE_LABELS themselves. Callers map a chosen label
    back to its key via dict(zip(labels, keys)) or similar."""
    return [(key, _SOURCE_LABELS[key]) for key in _SOURCE_ORDER]


def get_motif_drill_positions(sqlite_conn, motif: str | None = None,
                              top_n: int | None = 20) -> pd.DataFrame:
    """Positions where the player missed a tactical motif, sorted by CPL descending.

    Requires worker.py (engine analysis) and annotate.py Pass 4 (motif labelling).
    Rows missing fen_before or best_move_san are excluded -- those columns are only
    populated after annotation completes.

    motif: optional filter to one type (e.g. "fork", "pin", "hanging").
    top_n=None returns every qualifying row (bounded by how many
    mistakes/blunders ever got a motif label -- ~1.2k rows on a 32k-game
    database) -- lets the view layer cache ONE full fetch per session and
    apply the motif filter + top_n slice in pandas instead of re-running
    the query per distinct filter/slider combo.

    Takes sqlite_conn, not duck_conn -- with idx_moves_motif (partial
    index, migration 0031) plus real ANALYZE statistics this is a ~4-10ms
    index seek on sqlite, vs ~0.8s as a full SQLITE_SCAN via duck_conn
    (whose ATTACH boundary never uses sqlite indexes anyway -- the same
    phenomenon documented in openings.py's point-lookup fixes).
    """
    motif_clause = "AND m.motif = ?" if motif else ""
    limit_clause = "" if top_n is None else "LIMIT ?"
    params = ([motif] if motif else []) + ([] if top_n is None else [top_n])
    return pd.read_sql_query(f"""
        SELECT
            m.fen_before,
            m.best_move_san,
            m.san             AS actual_move_san,
            m.motif,
            ROUND(m.cpl, 0)   AS cpl,
            g.opening_family  AS opening,
            m.game_id,
            m.move_number
        FROM moves m
        JOIN games g ON g.id = m.game_id
        WHERE m.is_player_move = 1
          AND m.motif          IS NOT NULL
          AND m.classification IN ('mistake', 'blunder')
          AND m.fen_before     IS NOT NULL
          AND m.best_move_san  IS NOT NULL
          {motif_clause}
        ORDER BY m.cpl DESC
        {limit_clause}
    """, sqlite_conn, params=params)


def get_time_pressure_drill_positions(sqlite_conn, top_n: int | None = 20) -> pd.DataFrame:
    """Positions where the player made a mistake/blunder while their own
    clock was already in TIME_PRESSURE_BUCKETS' "critical (<5%)" band,
    sorted by CPL descending.

    Verified against the real dev DB: **145 rows** qualify -- a real,
    usable drill source. Unlike get_motif_drill_positions, this does NOT
    gate on m.motif -- the practical advantage is real today, not just in
    principle: moves.motif IS NOT NULL is currently 0 rows on this DB (the
    motif backfill hasn't run), which makes Missed Tactics empty, while
    this source works right now off classification/cpl/clock_seconds
    alone, columns worker.py and annotate.py already populate.

    top_n=None returns every qualifying row -- same client-cache-then-slice
    rationale as get_motif_drill_positions.

    Takes sqlite_conn, not duck_conn, for the same reason
    get_motif_drill_positions does: this is a small point-lookup-shaped
    query (mistakes/blunders only, via idx_moves_player_cpl's
    is_player_move filter) against a real sqlite connection, vs. a full
    SQLITE_SCAN through DuckDB's ATTACH boundary, which never uses
    sqlite indexes anyway.
    """
    limit_clause = "" if top_n is None else "LIMIT ?"
    critical_fraction = TIME_PRESSURE_BUCKETS[0][2]  # 0.05, "critical (<5%)"
    params = [critical_fraction] + ([] if top_n is None else [top_n])
    return pd.read_sql_query(f"""
        SELECT
            m.fen_before,
            m.best_move_san,
            m.san             AS actual_move_san,
            ROUND(m.cpl, 0)   AS cpl,
            g.opening_family  AS opening,
            m.game_id,
            m.move_number
        FROM moves m
        JOIN games g ON g.id = m.game_id
        WHERE m.is_player_move = 1
          AND m.classification IN ('mistake', 'blunder')
          AND m.fen_before     IS NOT NULL
          AND m.best_move_san  IS NOT NULL
          AND m.clock_seconds  IS NOT NULL
          AND g.base_seconds   IS NOT NULL AND g.base_seconds > 0
          AND CAST(m.clock_seconds AS DOUBLE) / g.base_seconds < ?
        ORDER BY m.cpl DESC
        {limit_clause}
    """, sqlite_conn, params=params)


def get_decisive_moment_positions(duck_conn, top_n: int = 20, phase: str | None = None,
                                   collapse_only: bool = False,
                                   config_path=None) -> pd.DataFrame:
    """One position per loss: the ply with the largest win-probability drop
    in a contested position (win_prob_before between 0.30 and 0.70).

    Sorted by wp_drop descending so the most dramatic turning points come first.
    Requires worker.py (win_prob_*) and annotate.py (fen_before, best_move_san).

    phase: optional filter to one of 'opening' / 'middlegame' / 'endgame'
    (the same move-number-derived bucket already computed by the query).
    When phase == "endgame", an ADDITIONAL material check is applied:
    non_pawn_piece_count(material_sig) <= config's analytics.endgame_max_pieces.
    This is necessary because the move-number phase alone is a poor endgame
    detector -- checked directly against the real dev DB, 28 of 180 (15.6%)
    phase='endgame' rows (move_number > 30) still had more than
    endgame_max_pieces non-pawn pieces on the board, i.e. a long middlegame
    mislabeled as an endgame by move count alone. The config load for that
    threshold only happens when phase == "endgame", to avoid extra work on
    the (far more common) unfiltered/non-endgame call paths.

    collapse_only: when True, additionally restricts to rows where
    g.rating_diff >= GIANT_KILLING_COLLAPSE_THRESHOLD (300) -- a loss as a
    300+-rated favorite, i.e. a "collapse." Verified against the real dev
    DB: 304 rows qualify (comparable to Endgame's 180 and Time
    Management's 145 -- a real, usable drill source). The mirror case,
    upset *wins* (rating_diff <= -300, "Giant-Killing"), has zero possible
    drill content here by construction -- this query is loss-only (a win
    has no losing move to learn from) -- so this ships as a "Collapse
    Trainer," not a "Giant-Killer & Collapse Trainer."

    The SQL no longer LIMITs server-side -- it already fully sorts by
    wp_drop DESC, so top_n is applied client-side, AFTER any phase/collapse
    filter. Limiting before filtering could silently return fewer than
    top_n rows (or zero) when the unfiltered top-N window doesn't happen
    to contain enough matching positions.
    """
    df = duck_conn.execute("""
        WITH ranked AS (
            SELECT
                m.game_id,
                m.fen_before,
                m.best_move_san,
                m.san                                             AS actual_move_san,
                m.move_number,
                m.material_sig,
                m.win_prob_before - m.win_prob_after              AS wp_drop,
                CASE WHEN m.move_number <= 12 THEN 'opening'
                     WHEN m.move_number <= 30 THEN 'middlegame'
                     ELSE 'endgame' END                           AS phase,
                g.opening_family                                  AS opening,
                g.rating_diff                                     AS rating_diff,
                ROW_NUMBER() OVER (
                    PARTITION BY m.game_id
                    ORDER BY m.win_prob_before - m.win_prob_after DESC
                )                                                 AS rn
            FROM db.moves m
            JOIN db.games g ON g.id = m.game_id
            WHERE g.outcome_for_player = 'loss'
              AND m.is_player_move     = 1
              AND m.win_prob_before    IS NOT NULL
              AND m.win_prob_after     IS NOT NULL
              AND m.win_prob_before    BETWEEN 0.30 AND 0.70
              AND m.win_prob_before    > m.win_prob_after
              AND m.fen_before         IS NOT NULL
              AND m.best_move_san      IS NOT NULL
        )
        SELECT game_id, fen_before, best_move_san, actual_move_san,
               move_number, phase, opening, material_sig, rating_diff,
               ROUND(wp_drop, 3) AS wp_drop
        FROM ranked
        WHERE rn = 1
        ORDER BY wp_drop DESC
    """).fetchdf()

    if phase is not None:
        df = df[df.phase == phase]
        if phase == "endgame":
            cfg = get_config(config_path)
            max_pieces = cfg["analytics"]["endgame_max_pieces"]
            df = df[df.material_sig.apply(chess_utils.non_pawn_piece_count) <= max_pieces]

    if collapse_only:
        df = df[df.rating_diff >= GIANT_KILLING_COLLAPSE_THRESHOLD]

    return df.drop(columns=["material_sig", "rating_diff"]).head(top_n)


def build_drill_cards(sqlite_conn, duck_conn, sources: set[str],
                      top_n: int = 20) -> list[dict]:
    """Collects drill positions from `sources` into add_cards()-ready
    dicts. Shared by the SRS Manage Queue tab (own database) and Coach
    Mode's drill assignment (a student's database) -- pass whichever
    database's connections the cards should be built FROM; add_cards()
    decides where they go.

    sources: a set of keys from _SOURCE_ORDER (e.g. {"motifs", "moments",
    "holes"}). No default -- every caller must state its sources
    explicitly. This replaced a one-bool-param-per-source signature
    (include_motifs/include_moments/include_holes/include_endgame_moments)
    after real drift was found: chesswright_pro/coach_view.py's
    assign-to-student caller kept only the original 3 kwargs and silently
    never picked up include_endgame_moments when Endgame Trainer shipped a
    4th. Raises ValueError on any key not in _SOURCE_ORDER (typo guard --
    this is an internal API, a strict contract is correct here).

    "holes" triggers ensure_repertoire_holes_cache first (idempotent,
    count-sentinel -- a no-op unless new analysis landed), since a
    student's database may never have visited the Openings page. Views
    wanting a spinner around that put it around this whole call.

    Sources are collected in _SOURCE_ORDER: motifs, then endgame_moments,
    then collapse_moments, then time_pressure, then moments, then holes.
    add_cards() dedupes by UNIQUE(fen) via INSERT OR IGNORE, so when a
    position qualifies for more than one source, whichever is collected
    first wins the label. collapse_moments sits between endgame_moments
    and time_pressure because it's more specific than a generic decisive
    moment but less specific than a real-material endgame turning point
    -- mirrors the existing endgame-vs-moments ordering (endgame first,
    since it's the more specific label). time_pressure sits right after
    collapse_moments and before moments because it's a specific "why"
    signal read straight off the moves table (like Missed Tactics), more
    specific than a generic Decisive Moment -- and leaves room for
    Conversion and Defense (future trainers) to slot in between
    time_pressure and moments too.
    """
    unknown = sources - set(_SOURCE_ORDER)
    if unknown:
        raise ValueError(f"Unknown build_drill_cards source(s): {sorted(unknown)}")

    cards: list[dict] = []

    for source in _SOURCE_ORDER:
        if source not in sources:
            continue

        if source == "motifs":
            df = get_motif_drill_positions(sqlite_conn, top_n=top_n)
        elif source == "endgame_moments":
            df = get_decisive_moment_positions(duck_conn, top_n=top_n, phase="endgame")
        elif source == "collapse_moments":
            df = get_decisive_moment_positions(duck_conn, top_n=top_n, collapse_only=True)
        elif source == "time_pressure":
            df = get_time_pressure_drill_positions(sqlite_conn, top_n=top_n)
        elif source == "moments":
            df = get_decisive_moment_positions(duck_conn, top_n=top_n)
        elif source == "holes":
            analytics.ensure_repertoire_holes_cache(sqlite_conn)
            df = get_repertoire_holes(sqlite_conn, min_appearances=5, top_n=top_n)
            df = df.rename(columns={"most_played_san": "best_move_san"})

        label = _SOURCE_LABELS[source]
        for row in df.itertuples(index=False):
            rd = row._asdict()
            if rd.get("fen_before") and rd.get("best_move_san"):
                cards.append({
                    "fen": rd["fen_before"], "source": label,
                    "best_move_san": str(rd["best_move_san"]),
                    "actual_move_san": str(rd["actual_move_san"]) if rd.get("actual_move_san") else None,
                    "context": _drill_context(rd),
                })
    return cards
