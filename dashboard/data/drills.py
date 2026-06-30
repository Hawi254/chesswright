"""Drill position queries: tactical motif misses and decisive turning-point positions.

Repertoire hole positions live in openings.py (get_repertoire_holes already returns
fen_before / most_played_san). Callers can rename most_played_san → best_move_san
and pass that DataFrame alongside these results to drills_to_pgn_study / drills_to_anki_csv.
"""
import pandas as pd


def get_motif_drill_positions(duck_conn, motif: str | None = None, top_n: int = 20) -> pd.DataFrame:
    """Positions where the player missed a tactical motif, sorted by CPL descending.

    Requires worker.py (engine analysis) and annotate.py Pass 4 (motif labelling).
    Rows missing fen_before or best_move_san are excluded -- those columns are only
    populated after annotation completes.

    motif: optional filter to one type (e.g. "fork", "pin", "hanging").
    """
    motif_clause = "AND m.motif = ?" if motif else ""
    params = [motif, top_n] if motif else [top_n]
    return duck_conn.execute(f"""
        SELECT
            m.fen_before,
            m.best_move_san,
            m.motif,
            ROUND(m.cpl, 0)   AS cpl,
            g.opening_family  AS opening,
            m.game_id,
            m.move_number
        FROM db.moves m
        JOIN db.games g ON g.id = m.game_id
        WHERE m.is_player_move = 1
          AND m.motif          IS NOT NULL
          AND m.classification IN ('mistake', 'blunder')
          AND m.fen_before     IS NOT NULL
          AND m.best_move_san  IS NOT NULL
          {motif_clause}
        ORDER BY m.cpl DESC
        LIMIT ?
    """, params).fetchdf()


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
        SELECT game_id, fen_before, best_move_san, move_number, phase,
               opening, ROUND(wp_drop, 3) AS wp_drop
        FROM ranked
        WHERE rn = 1
        ORDER BY wp_drop DESC
        LIMIT ?
    """, [top_n]).fetchdf()
