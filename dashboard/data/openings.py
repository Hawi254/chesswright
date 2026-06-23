"""Openings page queries."""
import pandas as pd


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
        return pd.DataFrame(columns=["ply", "n_games", "win_pct", "draw_pct", "loss_pct", "common_opening"])

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
        rows.append((row.ply, n, win, draw, loss, common_opening))
    return pd.DataFrame(rows, columns=["ply", "n_games", "win_pct", "draw_pct", "loss_pct", "common_opening"])
