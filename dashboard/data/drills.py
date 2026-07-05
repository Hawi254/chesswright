"""Drill position queries: tactical motif misses and decisive turning-point positions.

Repertoire hole positions live in openings.py (get_repertoire_holes already returns
fen_before / most_played_san). Callers can rename most_played_san → best_move_san
and pass that DataFrame alongside these results to drills_to_pgn_study / drills_to_anki_csv.

build_drill_cards() is the one place the three sources become SRS card
dicts -- extracted from srs_drill_view's Manage Queue tab (BRIEF §6q) so
Coach Mode's drill assignment (Pro) builds a student's cards through the
IDENTICAL code path against the student's connections, instead of
re-implementing the source collection a second time. It also retired
srs_drill_view._context_str, a near-duplicate of
chess_display._drill_context that had already drifted in label wording.
"""
import pandas as pd

import analytics
from chess_display import _drill_context

from .openings import get_repertoire_holes


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


def get_decisive_moment_positions(duck_conn, top_n: int = 20) -> pd.DataFrame:
    """One position per loss: the ply with the largest win-probability drop
    in a contested position (win_prob_before between 0.30 and 0.70).

    Sorted by wp_drop descending so the most dramatic turning points come first.
    Requires worker.py (win_prob_*) and annotate.py (fen_before, best_move_san).
    """
    return duck_conn.execute("""
        WITH ranked AS (
            SELECT
                m.game_id,
                m.fen_before,
                m.best_move_san,
                m.san                                             AS actual_move_san,
                m.move_number,
                m.win_prob_before - m.win_prob_after              AS wp_drop,
                CASE WHEN m.move_number <= 12 THEN 'opening'
                     WHEN m.move_number <= 30 THEN 'middlegame'
                     ELSE 'endgame' END                           AS phase,
                g.opening_family                                  AS opening,
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
               move_number, phase, opening, ROUND(wp_drop, 3) AS wp_drop
        FROM ranked
        WHERE rn = 1
        ORDER BY wp_drop DESC
        LIMIT ?
    """, [top_n]).fetchdf()


def build_drill_cards(sqlite_conn, duck_conn,
                      include_motifs: bool = True,
                      include_moments: bool = True,
                      include_holes: bool = True,
                      top_n: int = 20) -> list[dict]:
    """Collects drill positions from the three sources into add_cards()-
    ready dicts. Shared by the SRS Manage Queue tab (own database) and
    Coach Mode's drill assignment (a student's database) -- pass whichever
    database's connections the cards should be built FROM; add_cards()
    decides where they go.

    include_holes triggers ensure_repertoire_holes_cache first (idempotent,
    count-sentinel -- a no-op unless new analysis landed), since a
    student's database may never have visited the Openings page. Views
    wanting a spinner around that put it around this whole call.
    """
    cards: list[dict] = []

    if include_motifs:
        df = get_motif_drill_positions(sqlite_conn, top_n=top_n)
        for row in df.itertuples(index=False):
            rd = row._asdict()
            if rd.get("fen_before") and rd.get("best_move_san"):
                cards.append({
                    "fen": rd["fen_before"], "source": "Missed Tactics",
                    "best_move_san": str(rd["best_move_san"]),
                    "actual_move_san": str(rd["actual_move_san"]) if rd.get("actual_move_san") else None,
                    "context": _drill_context(rd),
                })
    if include_moments:
        df = get_decisive_moment_positions(duck_conn, top_n=top_n)
        for row in df.itertuples(index=False):
            rd = row._asdict()
            if rd.get("fen_before") and rd.get("best_move_san"):
                cards.append({
                    "fen": rd["fen_before"], "source": "Decisive Moment",
                    "best_move_san": str(rd["best_move_san"]),
                    "actual_move_san": str(rd["actual_move_san"]) if rd.get("actual_move_san") else None,
                    "context": _drill_context(rd),
                })
    if include_holes:
        analytics.ensure_repertoire_holes_cache(sqlite_conn)
        df = get_repertoire_holes(sqlite_conn, min_appearances=5, top_n=top_n)
        df = df.rename(columns={"most_played_san": "best_move_san"})
        for row in df.itertuples(index=False):
            rd = row._asdict()
            if rd.get("fen_before") and rd.get("best_move_san"):
                cards.append({
                    "fen": rd["fen_before"], "source": "Repertoire Hole",
                    "best_move_san": str(rd["best_move_san"]),
                    "context": _drill_context(rd),
                })
    return cards
