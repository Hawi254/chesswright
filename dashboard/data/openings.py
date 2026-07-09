"""Openings page queries."""
import chess
import pandas as pd

import config
from chess_utils import signed_zobrist

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


# ── Time-sliced repertoire evolution (Opening Tree, Pro) ─────────────────────
#
# The "What Changed" scan bakes in a total-games floor so the bulk query
# returns tens of thousands of rows instead of ~900k. It must stay <=
# 2 x the What Changed tab's min-games-per-era slider FLOOR (3): a position
# with fewer than 6 total games can never satisfy >=3 games on each side of
# a split, so pruning at 6 can't hide a result any slider value can reach.
FLIP_SCAN_MIN_TOTAL_GAMES = 6

_EMPTY_FLIPS = pd.DataFrame(columns=[
    "ply", "zobrist_hash", "fen", "total_games",
    "before_san", "before_n", "before_total", "before_share", "before_win_pct", "before_cpl",
    "after_san", "after_n", "after_total", "after_share", "after_win_pct", "after_cpl",
])


def get_opening_moves_by_year(sqlite_conn, fen: str, player_color: str) -> pd.DataFrame:
    """Per-year breakdown of every move played from *fen* in games where
    the player had *player_color* ('w'/'b') -- the time-sliced companion to
    get_opening_moves_from_fen, for the Opening Tree's timeline panel.

    Returns one row per (san, year): n_games, n_wins/draws/losses (outcomes
    from the player's perspective), cpl_sum/cpl_n (player moves only --
    callers derive era-weighted avg CPL as cpl_sum/cpl_n, which stays exact
    under any regrouping of years; a pre-averaged avg_cpl column wouldn't).

    Deliberately live, not materialized: measured on the real 2.3M-move DB,
    the worst case (the starting position, ~16k games/color) runs in ~175ms
    via idx_moves_fen_before, a popular ply-6 position in ~20ms, and it only
    gets cheaper deeper. Takes sqlite_conn, not duck_conn -- same
    index-pushdown reasoning as get_opening_moves_from_fen above.
    """
    db_color = "white" if player_color == "w" else "black"
    return pd.read_sql_query("""
        SELECT
            m.san,
            g.year,
            MAX(m.is_player_move)                                                       AS is_player_move,
            COUNT(DISTINCT m.game_id)                                                   AS n_games,
            COUNT(DISTINCT CASE WHEN g.outcome_for_player = 'win'  THEN m.game_id END) AS n_wins,
            COUNT(DISTINCT CASE WHEN g.outcome_for_player = 'draw' THEN m.game_id END) AS n_draws,
            COUNT(DISTINCT CASE WHEN g.outcome_for_player = 'loss' THEN m.game_id END) AS n_losses,
            SUM(CASE WHEN m.is_player_move = 1 THEN m.cpl END)                          AS cpl_sum,
            COUNT(CASE WHEN m.is_player_move = 1 THEN m.cpl END)                        AS cpl_n
        FROM moves m
        JOIN games g ON g.id = m.game_id
        WHERE m.fen_before   = ?
          AND g.player_color = ?
        GROUP BY m.san, g.year
        ORDER BY g.year, n_games DESC
    """, sqlite_conn, params=[fen, db_color])


def get_player_move_year_stats(duck_conn, player_color: str, max_ply: int = 40) -> pd.DataFrame:
    """Per-(position, move, year) aggregates of the PLAYER's own opening
    moves for one color -- the bulk input to compute_dominant_move_flips.

    One grouped scan over analyzed moves (~2-3s on the real DB), keyed by
    color only: the What Changed tab's split-year/min-games sliders are
    applied in pandas on top of this frame, never baked into the scan, so
    slider moves are free (the audit-established rule: don't key a cache on
    args the expensive part ignores). max_ply=40 matches the Opening Tree
    cache's opening-phase boundary. Positions with fewer than
    FLIP_SCAN_MIN_TOTAL_GAMES total player-move games are pruned in SQL --
    see that constant's comment for why this can't hide a reachable result.
    """
    db_color = "white" if player_color == "w" else "black"
    return duck_conn.execute("""
        SELECT ply, zobrist_hash, san, year, n_games, n_wins, cpl_sum, cpl_n, fen_before
        FROM (
            SELECT
                m.ply, m.zobrist_hash, m.san, g.year,
                COUNT(DISTINCT m.game_id)                                                   AS n_games,
                COUNT(DISTINCT CASE WHEN g.outcome_for_player = 'win' THEN m.game_id END)  AS n_wins,
                SUM(m.cpl)                                                                  AS cpl_sum,
                COUNT(m.cpl)                                                                AS cpl_n,
                MIN(m.fen_before)                                                           AS fen_before,
                SUM(COUNT(DISTINCT m.game_id))
                    OVER (PARTITION BY m.ply, m.zobrist_hash)                               AS position_total
            FROM db.moves m
            JOIN db.games g ON g.id = m.game_id
            WHERE m.zobrist_hash IS NOT NULL
              AND m.ply <= ?
              AND m.is_player_move = 1
              AND g.player_color = ?
            GROUP BY m.ply, m.zobrist_hash, m.san, g.year
        ) t
        WHERE position_total >= ?
        ORDER BY ply, zobrist_hash, year
    """, [max_ply, db_color, FLIP_SCAN_MIN_TOTAL_GAMES]).fetchdf()


def _era_dominants(df: pd.DataFrame, split_year: int) -> pd.DataFrame:
    """Collapse a per-(position, san, year) frame into one row per
    (position, era) holding that era's dominant (most-played) move plus the
    era's total game count. Ties break to SAN alphabetical order so results
    are deterministic run to run."""
    df = df.assign(era=df["year"].lt(split_year).map({True: "before", False: "after"}))
    era = (df.groupby(["ply", "zobrist_hash", "era", "san"], as_index=False)
             .agg(n_games=("n_games", "sum"), n_wins=("n_wins", "sum"),
                  cpl_sum=("cpl_sum", "sum"), cpl_n=("cpl_n", "sum"),
                  fen=("fen_before", "min")))
    totals = era.groupby(["ply", "zobrist_hash", "era"], as_index=False)["n_games"] \
                .sum().rename(columns={"n_games": "era_total"})
    # mergesort = stable, so the (n_games desc, san asc) order survives the
    # drop_duplicates pick of each group's first (= dominant) row.
    era = era.sort_values(["n_games", "san"], ascending=[False, True], kind="mergesort")
    dom = era.drop_duplicates(["ply", "zobrist_hash", "era"])
    return dom.merge(totals, on=["ply", "zobrist_hash", "era"])


def compute_dominant_move_flips(year_stats: pd.DataFrame, split_year: int,
                                min_games_each_era: int = 5) -> pd.DataFrame:
    """Positions whose dominant (most-played) player move DIFFERS between
    the games before *split_year* and the games from *split_year* on.

    Pure pandas over get_player_move_year_stats output -- unit-testable and
    cheap enough to re-run on every slider move. A position qualifies only
    when both eras have >= min_games_each_era player-move games, so a
    three-game "era" can't masquerade as a repertoire change.

    Returns _EMPTY_FLIPS's columns, sorted by total_games descending.
    share/win_pct are percentages of the era's games; *_cpl is the era's
    weighted avg CPL for the dominant move (NaN when unanalyzed).
    """
    if year_stats.empty:
        return _EMPTY_FLIPS.copy()

    dom = _era_dominants(year_stats, split_year)
    before = dom[dom["era"] == "before"].drop(columns="era")
    after = dom[dom["era"] == "after"].drop(columns="era")
    m = before.merge(after, on=["ply", "zobrist_hash"], suffixes=("_b", "_a"))
    m = m[(m["era_total_b"] >= min_games_each_era)
          & (m["era_total_a"] >= min_games_each_era)
          & (m["san_b"] != m["san_a"])]
    if m.empty:
        return _EMPTY_FLIPS.copy()

    out = pd.DataFrame({
        "ply": m["ply"], "zobrist_hash": m["zobrist_hash"], "fen": m["fen_b"],
        "total_games": m["era_total_b"] + m["era_total_a"],
        "before_san": m["san_b"], "before_n": m["n_games_b"],
        "before_total": m["era_total_b"],
        "before_share": 100.0 * m["n_games_b"] / m["era_total_b"],
        "before_win_pct": 100.0 * m["n_wins_b"] / m["n_games_b"],
        "before_cpl": m["cpl_sum_b"] / m["cpl_n_b"].where(m["cpl_n_b"] > 0),
        "after_san": m["san_a"], "after_n": m["n_games_a"],
        "after_total": m["era_total_a"],
        "after_share": 100.0 * m["n_games_a"] / m["era_total_a"],
        "after_win_pct": 100.0 * m["n_wins_a"] / m["n_games_a"],
        "after_cpl": m["cpl_sum_a"] / m["cpl_n_a"].where(m["cpl_n_a"] > 0),
    })
    return out.sort_values("total_games", ascending=False).reset_index(drop=True)


def summarize_position_timeline(year_df: pd.DataFrame,
                                min_games_each_era: int = 5) -> dict | None:
    """Detect the single clearest move switch at ONE position, for the
    Explorer timeline panel's plain-language headline.

    Tries every candidate split year present in the data and keeps the one
    where the dominant move genuinely differs on both sides (each side
    >= min_games_each_era games), preferring the split with the largest
    smaller-era -- i.e. the most evenly evidenced switch, not the one that
    shaves off a single noisy year. Returns None when no split qualifies
    (the common case: a stable repertoire).

    year_df is get_opening_moves_by_year output (single position, one side
    to move throughout, so no is_player_move filtering is needed here).
    """
    if year_df.empty:
        return None
    df = year_df.assign(ply=0, zobrist_hash=0, fen_before="")
    years = sorted(df["year"].unique())
    best, best_evidence = None, -1
    for split in years[1:]:
        flips = compute_dominant_move_flips(df, int(split), min_games_each_era)
        if flips.empty:
            continue
        row = flips.iloc[0]
        evidence = min(int(row["before_total"]), int(row["after_total"]))
        if evidence > best_evidence:
            best_evidence = evidence
            best = {"split_year": int(split)}
            best.update({k: row[k] for k in (
                "before_san", "before_n", "before_total", "before_share",
                "before_win_pct", "before_cpl",
                "after_san", "after_n", "after_total", "after_share",
                "after_win_pct", "after_cpl")})
    return best


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
    """
    return pd.read_sql_query("""
        SELECT ply, zobrist_hash, n_games, win_pct, draw_pct, loss_pct, common_opening
        FROM repeated_positions_cache
        WHERE n_games >= ?
        ORDER BY n_games DESC
        LIMIT ?
    """, sqlite_conn, params=[min_games, top_n])


def get_position_fen(sqlite_conn, ply: int, zobrist_hash: int):
    """Return any stored fen_before for the given (ply, zobrist_hash) position.

    Takes sqlite_conn, not duck_conn -- same point-lookup-via-ATTACHed-
    sqlite_scanner issue as get_opening_moves_from_fen/get_game_detail
    (DuckDB doesn't push this filter down as an index seek across the
    ATTACH boundary, so it was a full SQLITE_SCAN of all of moves on every
    call). idx_moves_zobrist already exists -- no new index needed.
    """
    row = sqlite_conn.execute("""
        SELECT fen_before FROM moves
        WHERE zobrist_hash = ? AND ply = ? AND fen_before IS NOT NULL
        LIMIT 1
    """, [zobrist_hash, ply]).fetchone()
    return row[0] if row else None


def resolve_move_squares(fen: str, best_move_san):
    """Return (best_move_from, best_move_to) plain square strings (e.g.
    ("b1", "d2")) for best_move_san in the position given by fen, or
    (None, None) if best_move_san is missing or unparseable (e.g. a
    mate/no-move position).

    Exists so callers never have to re-derive which piece/squares a bare
    SAN string like "Nd2" refers to via their own (unreliable) board
    visualization -- a real bug in Board Chat's show_arrow tool traced
    back to exactly that: the LLM reconstructed "Nd2" as the wrong
    knight. Computed on demand from the (fen, best_move_san) pair that's
    already persisted, rather than as new stored columns -- cheap, and
    the source data (fen_before + best_move_san) is already durable.
    """
    if not best_move_san:
        return None, None
    try:
        board = chess.Board(fen)
        move = board.parse_san(best_move_san)
    except Exception:
        return None, None
    uci = move.uci()
    return uci[:2], uci[2:4]


def get_position_analysis(sqlite_conn, fen_before: str):
    """Return stored Stockfish analysis for a position, or None if unanalyzed.

    Checks the moves table first (batch worker results -- authoritative),
    then falls back to position_cache (interactive probe results stored by
    store_position_analysis).  The 'source' key in the returned dict
    distinguishes the two ('stored' vs 'cached').

    eval_cp is centipawns from the side-to-move's perspective (positive =
    the player about to move is better) -- same convention as the batch
    worker so both sources display consistently.

    best_move_from/best_move_to are plain square strings (e.g. "b1"/"d2"),
    resolved via resolve_move_squares() from fen_before + best_move_san --
    see that function's docstring for why this exists (a real show_arrow
    illegal-move bug).

    Takes sqlite_conn, not duck_conn -- same point-lookup issue as
    get_opening_moves_from_fen/get_game_detail; idx_moves_fen_before
    (migration 0028) already exists, so this is a plain index seek here
    instead of a full scan on every "Most-repeated positions"/"Repertoire
    holes" row click.
    """
    row = sqlite_conn.execute("""
        SELECT eval_cp, eval_mate, best_move_san, pv_json
        FROM moves
        WHERE fen_before = ? AND best_move_san IS NOT NULL
        LIMIT 1
    """, [fen_before]).fetchone()
    if row:
        best_move_from, best_move_to = resolve_move_squares(fen_before, row[2])
        return {"eval_cp": row[0], "eval_mate": row[1],
                "best_move_san": row[2], "pv_json": row[3],
                "best_move_from": best_move_from, "best_move_to": best_move_to,
                "depth": None, "source": "stored"}

    row = sqlite_conn.execute("""
        SELECT eval_cp, eval_mate, best_move_san, pv_json, engine_depth
        FROM position_cache
        WHERE fen_before = ? AND best_move_san IS NOT NULL
        LIMIT 1
    """, [fen_before]).fetchone()
    if row:
        best_move_from, best_move_to = resolve_move_squares(fen_before, row[2])
        return {"eval_cp": row[0], "eval_mate": row[1],
                "best_move_san": row[2], "pv_json": row[3],
                "best_move_from": best_move_from, "best_move_to": best_move_to,
                "depth": row[4], "source": "cached"}

    return None


def store_position_analysis(sqlite_conn, fen_before: str, result) -> None:
    """Write a LiveResult to position_cache if depth >= store_threshold.

    Uses sqlite_conn directly (not DuckDB) because DuckDB's sqlite_scanner
    is read-only -- writes must go through the native sqlite3 connection.
    Does nothing if the result didn't reach store_threshold depth.

    Does NOT persist best_move_from/best_move_to as separate columns --
    position_cache's schema doesn't have them, and doesn't need to:
    get_position_analysis() re-derives them on every read via
    resolve_move_squares(fen_before, best_move_san), which is exactly the
    (fen_before, best_move_san) pair this function already persists. That
    recomputation is cheap and always in sync with what's stored, so a
    schema migration for two redundant columns isn't worth it here.
    """
    threshold = config.load_config().get("interactive_engine", {}).get(
        "store_threshold", 20)
    if result.depth < threshold:
        return
    sqlite_conn.execute("""
        INSERT OR REPLACE INTO position_cache
            (fen_before, eval_cp, eval_mate, best_move_san, pv_json,
             engine_depth, engine_version)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, [fen_before, result.eval_cp, result.eval_mate, result.best_move_san,
          result.pv_json, result.depth, result.engine_version])
    sqlite_conn.commit()
