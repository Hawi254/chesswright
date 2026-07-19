"""Engine-backed position analysis queries: stored-analysis lookup,
move-square resolution, and the interactive-probe cache write -- the
third topic module split out of the former dashboard/data/openings.py.
"""
import chess

import config


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
