"""Openings page queries."""
import pandas as pd


def get_opening_ply_accuracy(duck_conn, opening_family, player_color, min_appearances=3):
    """Per-move-number avg CPL for one (opening_family, player_color) pair.

    Groups the player's own analyzed moves by move_number within games
    that belong to the given opening.  min_appearances drops move numbers
    reached in fewer than that many games, guarding against noise from
    lines the player rarely survives into.
    """
    return duck_conn.execute("""
        SELECT
            m.move_number,
            COUNT(DISTINCT m.game_id)                                           AS n_games,
            AVG(m.cpl)                                                          AS avg_cpl,
            100.0 * AVG(CASE WHEN m.classification IN ('mistake','blunder')
                             THEN 1.0 ELSE 0.0 END)                            AS blunder_rate
        FROM db.moves m
        JOIN db.games g ON g.id = m.game_id
        WHERE g.opening_family = ?
          AND g.player_color   = ?
          AND m.is_player_move = 1
          AND m.cpl IS NOT NULL
        GROUP BY m.move_number
        HAVING COUNT(DISTINCT m.game_id) >= ?
        ORDER BY m.move_number
    """, [opening_family, player_color, min_appearances]).fetchdf()


def get_openings_table(duck_conn, sqlite_conn, min_games=5):
    """Single bulk GROUP BY for the ACPL side, not one acpl_and_blunder_rate
    call per (opening, color) row -- measured cost of the per-row version:
    74 rows x ~0.5s/full-table-scan = ~39s. moves has no index on cpl/
    opening_family, so every targeted query scans all ~2M rows; one grouped
    pass over the same rows costs ~0.5s total instead of 74x that."""
    counts = duck_conn.execute("""
        SELECT opening_family, player_color, COUNT(*) AS n,
               100.0 * SUM(CASE WHEN outcome_for_player='win' THEN 1 ELSE 0 END) / COUNT(*) AS win_pct,
               100.0 * SUM(CASE WHEN outcome_for_player='draw' THEN 1 ELSE 0 END) / COUNT(*) AS draw_pct
        FROM db.games
        WHERE opening_family IS NOT NULL AND outcome_for_player IS NOT NULL
        GROUP BY opening_family, player_color
        HAVING COUNT(*) >= ?
    """, [min_games]).fetchdf()

    acpl_rows = sqlite_conn.execute("""
        SELECT g.opening_family, g.player_color, COUNT(DISTINCT m.game_id) AS n_analyzed, AVG(m.cpl) AS acpl
        FROM moves m JOIN games g ON g.id = m.game_id
        WHERE m.is_player_move=1 AND m.cpl IS NOT NULL AND g.opening_family IS NOT NULL
        GROUP BY g.opening_family, g.player_color
    """).fetchall()
    acpl_lookup = {(family, color): (n_analyzed, acpl) for family, color, n_analyzed, acpl in acpl_rows}

    acpls, n_analyzed_list = [], []
    for row in counts.itertuples():
        n_analyzed, acpl = acpl_lookup.get((row.opening_family, row.player_color), (0, None))
        acpls.append(acpl)
        n_analyzed_list.append(n_analyzed)
    counts["acpl"] = acpls
    counts["n_analyzed"] = n_analyzed_list
    return counts.sort_values("n", ascending=False).reset_index(drop=True)


def get_repertoire_holes(duck_conn, min_appearances=5, top_n=20):
    """Positions reached many times with inconsistent move choices and high avg CPL.

    A 'hole' requires both inconsistency (≥2 distinct moves played) and poor
    quality (avg CPL > 0).  hole_score = n_distinct_moves × avg_cpl compounds
    both axes so positions that are both deeply uncertain and costly rank first.

    Only analyzed games are included (fen_before populated during annotation).
    """
    return duck_conn.execute("""
        WITH pos_stats AS (
            SELECT
                m.fen_before,
                COUNT(DISTINCT m.game_id)                           AS n_games,
                COUNT(DISTINCT m.san)                               AS n_distinct_moves,
                AVG(m.cpl)                                          AS avg_cpl,
                CAST(ROUND(AVG(m.move_number)) AS INTEGER)          AS approx_move_number,
                COUNT(DISTINCT m.san) * AVG(m.cpl)                 AS hole_score
            FROM db.moves m
            WHERE m.is_player_move = 1
              AND m.cpl            IS NOT NULL
              AND m.fen_before     IS NOT NULL
            GROUP BY m.fen_before
            HAVING COUNT(DISTINCT m.game_id) >= ?
               AND COUNT(DISTINCT m.san)     >= 2
        ),
        move_counts AS (
            SELECT
                fen_before,
                san,
                ROW_NUMBER() OVER (
                    PARTITION BY fen_before
                    ORDER BY COUNT(*) DESC
                )                                                    AS rn
            FROM db.moves
            WHERE is_player_move = 1 AND fen_before IS NOT NULL
            GROUP BY fen_before, san
        ),
        top_openings AS (
            SELECT
                m.fen_before,
                g.opening_family,
                ROW_NUMBER() OVER (
                    PARTITION BY m.fen_before
                    ORDER BY COUNT(*) DESC
                )                                                    AS rn
            FROM db.moves m
            JOIN db.games g ON g.id = m.game_id
            WHERE m.is_player_move = 1
              AND m.fen_before     IS NOT NULL
              AND g.opening_family IS NOT NULL
            GROUP BY m.fen_before, g.opening_family
        )
        SELECT
            ps.fen_before,
            ps.n_games,
            ps.n_distinct_moves,
            ROUND(ps.avg_cpl, 1)    AS avg_cpl,
            ps.approx_move_number,
            ROUND(ps.hole_score, 1) AS hole_score,
            mc.san                   AS most_played_san,
            tof.opening_family       AS opening
        FROM pos_stats ps
        LEFT JOIN move_counts  mc  ON mc.fen_before  = ps.fen_before AND mc.rn  = 1
        LEFT JOIN top_openings tof ON tof.fen_before = ps.fen_before AND tof.rn = 1
        ORDER BY ps.hole_score DESC
        LIMIT ?
    """, [min_appearances, top_n]).fetchdf()


def get_most_repeated_positions(duck_conn, top_n=20, min_games=5):
    nodes = duck_conn.execute("""
        SELECT m.ply, m.zobrist_hash, COUNT(DISTINCT m.game_id) AS n
        FROM db.moves m WHERE m.zobrist_hash IS NOT NULL
        GROUP BY m.ply, m.zobrist_hash
        HAVING COUNT(DISTINCT m.game_id) >= ?
        ORDER BY n DESC LIMIT ?
    """, [min_games, top_n]).fetchdf()

    if nodes.empty:
        # No (ply, zobrist_hash) node has reached min_games yet -- expected
        # on a fresh install with few analyzed games (BRIEF.md's Phase B
        # starter-batch onboarding makes this the COMMON case, not a rare
        # edge case, unlike the original project's large existing dataset
        # where this never came up). An empty IN (...) below is invalid
        # SQL, not just an empty result -- short-circuit before building it.
        return pd.DataFrame(columns=["ply", "zobrist_hash", "n_games", "win_pct", "draw_pct", "loss_pct", "common_opening"])

    # One bulk query for all top_n nodes' outcomes, not one point-lookup
    # query per node -- each separate (ply, zobrist_hash) point lookup
    # against the ATTACHed SQLite file measured ~0.46s (no persistent
    # index across the sqlite_scanner boundary), so 20 of them cost ~9s;
    # this VALUES-join does the same work in one pass.
    value_pairs = ", ".join(f"({row.ply}, {row.zobrist_hash})" for row in nodes.itertuples())
    detail = duck_conn.execute(f"""
        SELECT m.ply, m.zobrist_hash, g.outcome_for_player, g.opening_family
        FROM db.moves m JOIN db.games g ON g.id = m.game_id
        WHERE (m.ply, m.zobrist_hash) IN ({value_pairs})
    """).fetchdf()

    rows = []
    for row in nodes.itertuples():
        games = detail[(detail.ply == row.ply) & (detail.zobrist_hash == row.zobrist_hash)]
        n = len(games)
        win = 100.0 * (games.outcome_for_player == "win").sum() / n
        draw = 100.0 * (games.outcome_for_player == "draw").sum() / n
        loss = 100.0 * (games.outcome_for_player == "loss").sum() / n
        common_opening = games.opening_family.mode().iat[0] if not games.opening_family.mode().empty else None
        rows.append((row.ply, row.zobrist_hash, n, win, draw, loss, common_opening))
    return pd.DataFrame(rows, columns=["ply", "zobrist_hash", "n_games", "win_pct", "draw_pct", "loss_pct", "common_opening"])


def get_position_fen(duck_conn, ply: int, zobrist_hash: int):
    """Return any stored fen_before for the given (ply, zobrist_hash) position."""
    row = duck_conn.execute("""
        SELECT fen_before FROM db.moves
        WHERE zobrist_hash = ? AND ply = ? AND fen_before IS NOT NULL
        LIMIT 1
    """, [zobrist_hash, ply]).fetchone()
    return row[0] if row else None
