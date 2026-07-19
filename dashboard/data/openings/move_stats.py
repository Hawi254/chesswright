"""Move-history opening queries: per-position move stats, the Openings
table, repertoire holes, and path reconstruction -- one of three topic
modules split out of the former dashboard/data/openings.py.
"""
import chess
import pandas as pd

import config
from chess_utils import signed_zobrist
from confidence import default_thresholds

INITIAL_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"

# Must match analytics.ensure_opening_position_stats's default max_ply --
# positions deeper than this aren't in opening_position_stats_cache
# (migration 0029), so get_opening_moves_from_fen falls back to a live
# query for them.
_MAX_CACHED_PLY = 40

_EMPTY_OPENING_MOVES = pd.DataFrame(
    columns=["san", "is_player_move", "n_games", "n_wins", "n_draws", "n_losses", "avg_cpl"]
)


def get_opening_moves_from_fen(sqlite_conn, fen: str, ply: int, player_color: str,
                                min_games: int = 3) -> pd.DataFrame:
    """All moves played from *fen* (reached at 1-indexed *ply*) in games
    where the player played *player_color*.

    Returns one row per distinct SAN move with:
      is_player_move  — 1 if it was the player's turn at this FEN, 0 if opponent's
      n_games         — distinct games reaching this move
      n_wins/draws/losses — outcomes from the player's perspective
      avg_cpl         — average centipawn loss (only meaningful for player moves)

    Results are ordered by frequency descending, filtered to moves seen in at
    least *min_games* distinct games.

    Two-tier lookup:

    - ply <= _MAX_CACHED_PLY (the opening phase): served from
      opening_position_stats_cache (migration 0029, built by
      analytics.ensure_opening_position_stats) -- a precomputed aggregate
      keyed by (zobrist_hash, ply, player_color). Turns this from a live
      GROUP BY/COUNT DISTINCT into a plain indexed point lookup on rows
      that are already aggregated. Needed because even an index seek
      (idx_moves_fen_before, migration 0028) still leaves the aggregation
      itself to run live -- measured ~0.2s for a popular early position
      (e.g. ~16k games reaching the starting position) vs ~0.02-0.1ms
      against the cache, since the seek was never the bottleneck for those,
      the aggregation over the matched rows was.
    - ply > _MAX_CACHED_PLY: live query via idx_moves_fen_before. Deep
      positions are rare enough (typically single-digit game counts) that
      the live indexed query is already fast; caching them would just
      bloat opening_position_stats_cache for positions nobody revisits.

    Takes sqlite_conn, not duck_conn, for the live-query tier -- DuckDB's
    ATTACHed sqlite_scanner doesn't push filter predicates down as index
    seeks across the ATTACH boundary (confirmed live via EXPLAIN: full
    SQLITE_SCAN of all of moves regardless of any index, same phenomenon
    already documented for zobrist_hash lookups in
    get_most_repeated_positions below).
    """
    # games.player_color stores 'white'/'black'; convert 'w'/'b' shorthand
    db_color = "white" if player_color == "w" else "black"
    # min_games is the hard SQL gate below (unchanged); it doubles as
    # confidence.py's "low" tier threshold via default_thresholds() -- see
    # confidence.py's module docstring for the shared 3x/8x scheme. Not
    # attached to the returned frame as a visible column here: this
    # result flows straight into st.dataframe calls (Opening Tree) with
    # no column allowlist, so an extra column would leak into the UI --
    # left as a future badge hook, not wired in by this change.
    _thresholds = default_thresholds(min_games)  # noqa: F841 (future badge hook)

    if ply <= _MAX_CACHED_PLY:
        zobrist = signed_zobrist(chess.Board(fen))
        result = pd.read_sql_query("""
            SELECT san, is_player_move, n_games, n_wins, n_draws, n_losses, avg_cpl
            FROM opening_position_stats_cache
            WHERE zobrist_hash = ? AND ply = ? AND player_color = ?
              AND n_games >= ?
            ORDER BY n_games DESC
        """, sqlite_conn, params=[zobrist, ply, db_color, min_games])
        return result if result is not None else _EMPTY_OPENING_MOVES

    result = pd.read_sql_query("""
        SELECT
            m.san,
            MAX(m.is_player_move)                                                       AS is_player_move,
            COUNT(DISTINCT m.game_id)                                                   AS n_games,
            COUNT(DISTINCT CASE WHEN g.outcome_for_player = 'win'  THEN m.game_id END) AS n_wins,
            COUNT(DISTINCT CASE WHEN g.outcome_for_player = 'draw' THEN m.game_id END) AS n_draws,
            COUNT(DISTINCT CASE WHEN g.outcome_for_player = 'loss' THEN m.game_id END) AS n_losses,
            ROUND(AVG(CASE WHEN m.is_player_move = 1 THEN m.cpl END), 0)               AS avg_cpl
        FROM moves m
        JOIN games g ON g.id = m.game_id
        WHERE m.fen_before    = ?
          AND g.player_color  = ?
          AND m.fen_before IS NOT NULL
        GROUP BY m.san
        HAVING COUNT(DISTINCT m.game_id) >= ?
        ORDER BY n_games DESC
    """, sqlite_conn, params=[fen, db_color, min_games])
    return result if result is not None else _EMPTY_OPENING_MOVES


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


def get_openings_table(duck_conn, sqlite_conn, min_games: int | None = None):
    """Single bulk GROUP BY for the ACPL side, not one acpl_and_blunder_rate
    call per (opening, color) row -- measured cost of the per-row version:
    74 rows x ~0.5s/full-table-scan = ~39s. moves has no index on cpl/
    opening_family, so every targeted query scans all ~2M rows; one grouped
    pass over the same rows costs ~0.5s total instead of 74x that.

    min_games defaults to analytics.min_sample_size when not passed
    explicitly (this file's own config.load_config() precedent, matching
    this file's existing interactive_engine lookup elsewhere, rather than
    the get_config() convention used in the rest of dashboard/data/). It
    doubles as confidence.py's "low" tier threshold via
    default_thresholds(). Not attached to the returned frame as a column:
    openings_view.py renders it via st.dataframe with no column allowlist,
    so a new column would leak into the UI -- left as a future badge hook,
    not wired in here."""
    if min_games is None:
        min_games = config.load_config()["analytics"]["min_sample_size"]
    _thresholds = default_thresholds(min_games)  # noqa: F841 (future badge hook)
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


def get_repertoire_holes(sqlite_conn, min_appearances=5, top_n=20):
    """Positions reached many times with inconsistent move choices and high avg CPL.

    A 'hole' requires both inconsistency (≥2 distinct moves played) and poor
    quality (avg CPL > 0).  hole_score = n_distinct_moves × avg_cpl compounds
    both axes so positions that are both deeply uncertain and costly rank first.

    Only analyzed games are included (fen_before populated during annotation).

    Reads from repertoire_holes_cache (migration 0030, built by
    analytics.ensure_repertoire_holes_cache) instead of aggregating live --
    the live version scanned all of moves/games via duck_conn on every
    distinct (min_appearances, top_n) slider combination, even though the
    expensive GROUP BY doesn't depend on either value, only the
    HAVING/LIMIT applied on top of it did. min_appearances below the
    cache's own baked-in floor (ensure_repertoire_holes_cache's
    min_appearances=3 default) can't be served from the cache -- no caller
    in this codebase ever requests that (checked all three call sites).
    """
    return pd.read_sql_query("""
        SELECT fen_before, n_games, n_distinct_moves, avg_cpl,
               approx_move_number, hole_score, most_played_san, opening
        FROM repertoire_holes_cache
        WHERE n_games >= ?
        ORDER BY hole_score DESC
        LIMIT ?
    """, sqlite_conn, params=[min_appearances, top_n])


def get_most_repeated_positions(sqlite_conn, top_n=20, min_games=5):
    """Reads from repeated_positions_cache (migration 0030, built by
    analytics.ensure_repeated_positions_cache) instead of aggregating live
    -- same reasoning as get_repertoire_holes above. min_games below the
    cache's own baked-in floor (ensure_repeated_positions_cache's
    min_games=5 default, the only value any caller in this codebase ever
    uses) can't be served from the cache.

    Naturally returns an empty (but correctly-columned) DataFrame when no
    node has reached min_games yet -- expected on a fresh install with few
    analyzed games (BRIEF.md's Phase B starter-batch onboarding makes this
    the COMMON case, not a rare edge case).

    min_games is the hard SQL gate below (unchanged); it doubles as
    confidence.py's "low" tier threshold via default_thresholds(). Not
    attached to the returned frame as a column: openings_view.py renders
    it via st.dataframe with no column allowlist, so a new column would
    leak into the UI -- left as a future badge hook, not wired in here.
    """
    _thresholds = default_thresholds(min_games)  # noqa: F841 (future badge hook)
    return pd.read_sql_query("""
        SELECT ply, zobrist_hash, n_games, win_pct, draw_pct, loss_pct, common_opening
        FROM repeated_positions_cache
        WHERE n_games >= ?
        ORDER BY n_games DESC
        LIMIT ?
    """, sqlite_conn, params=[min_games, top_n])


def get_path_to_position(sqlite_conn, zobrist_hash: int, ply: int) -> list[str] | None:
    """Reconstruct a real move path (list of SANs) from the starting
    position to the position identified by (zobrist_hash, ply), by replaying
    the opening of an actual game that reached it.

    The Opening Tree's Explorer is path-keyed while the What Changed scan is
    zobrist-keyed, and transpositions mean some positions have no canonical
    path -- so the path comes from a game that really reached the position,
    then gets verified by replay (every SAN legal, final zobrist matches).
    Returns None when no verified path exists; callers must degrade to a
    board preview instead of offering an Explorer jump. Two indexed point
    lookups (idx_moves_zobrist, idx_moves_game) -- ~1ms.
    """
    row = sqlite_conn.execute(
        "SELECT game_id FROM moves WHERE zobrist_hash = ? AND ply = ? LIMIT 1",
        [zobrist_hash, ply]).fetchone()
    if not row:
        return None
    sans = [r[0] for r in sqlite_conn.execute(
        "SELECT san FROM moves WHERE game_id = ? AND ply < ? ORDER BY ply",
        [row[0], ply]).fetchall()]
    if len(sans) != ply - 1:
        return None
    board = chess.Board()
    try:
        for san in sans:
            board.push_san(san)
    except ValueError:
        return None
    if signed_zobrist(board) != zobrist_hash:
        return None
    return sans


def get_representative_path_for_family(sqlite_conn, opening_family: str, player_color: str,
                                        max_ply: int = 12) -> list[str] | None:
    """Reverse-maps a free-text opening family name to a concrete move
    path. ECO classification only works forward (moves -> name, via each
    game's already-computed opening_family column) -- so this finds the
    most common opening move sequence among the player's own games
    already tagged with that family, verified by replay (mirrors
    get_path_to_position's replay-verification approach). Used by the
    Opening Tree's jump-to-opening search.

    player_color is the 'w'/'b' shorthand (converted to the DB's stored
    'white'/'black' internally, same convention as
    get_opening_moves_from_fen). Returns None when no games match --
    callers must surface an explicit empty state, not a silent no-op.
    """
    db_color = "white" if player_color == "w" else "black"
    game_ids = [r[0] for r in sqlite_conn.execute(
        "SELECT id FROM games WHERE opening_family = ? AND player_color = ?",
        [opening_family, db_color]).fetchall()]
    if not game_ids:
        return None

    path_counts: dict[tuple[str, ...], int] = {}
    for game_id in game_ids:
        sans = tuple(r[0] for r in sqlite_conn.execute(
            "SELECT san FROM moves WHERE game_id = ? AND ply <= ? ORDER BY ply",
            [game_id, max_ply]).fetchall())
        if sans:
            path_counts[sans] = path_counts.get(sans, 0) + 1
    if not path_counts:
        return None

    best_path = max(path_counts, key=path_counts.get)

    board = chess.Board()
    try:
        for san in best_path:
            board.push_san(san)
    except ValueError:
        return None
    return list(best_path)
