"""Material-structure context computation (middlegame_sig/endgame_sig per
game) -- one of four sibling modules split out of analytics.py (largest-
file modularization, 2026-07-17). A leaf module: no dependency on this
split's other three siblings, only top-level chess_utils.
"""
from chess_utils import non_pawn_piece_count


def player_relative_sig(material_sig, player_color):
    """material_signature() always returns "WhiteSidevBlackSide" -- reorder
    to "playerSidevOpponentSide" so the same lived structure (e.g. "I have
    the bishop, opponent has the knight") doesn't fragment into two
    different buckets depending on which color the player happened to be."""
    if player_color == "white":
        return material_sig
    white_side, black_side = material_sig.split("v", 1)
    return f"{black_side}v{white_side}"


def compute_structure_context(conn, middlegame_ply, endgame_max_pieces):
    """One pass over ALL moves (any analysis status -- material_sig is
    board-derivable, not engine-dependent) building, per game:
    middlegame_sig (player-relative material_sig at the fixed ply
    checkpoint) and endgame_sig/endgame_ply (player-relative material_sig
    and ply number at the FIRST ply whose total non-pawn piece count drops
    to endgame_max_pieces or below). Games that never reach the checkpoint
    ply, or never simplify that far, simply contribute no row for that field."""
    colors = dict(conn.execute("SELECT id, player_color FROM games").fetchall())
    rows = conn.execute(
        "SELECT game_id, ply, material_sig FROM moves WHERE material_sig IS NOT NULL ORDER BY game_id, ply"
    ).fetchall()

    context = []
    cur_game = None
    middlegame_sig = None
    endgame_sig = None
    endgame_ply = None
    endgame_found = False

    def flush():
        if cur_game is not None:
            context.append((cur_game, middlegame_sig, endgame_sig, endgame_ply))

    for game_id, ply, sig in rows:
        if game_id != cur_game:
            flush()
            cur_game = game_id
            middlegame_sig = None
            endgame_sig = None
            endgame_ply = None
            endgame_found = False
        color = colors.get(game_id)
        rel_sig = player_relative_sig(sig, color) if color else sig
        if ply == middlegame_ply:
            middlegame_sig = rel_sig
        if not endgame_found and non_pawn_piece_count(sig) <= endgame_max_pieces:
            endgame_found = True
            endgame_sig = rel_sig
            endgame_ply = ply
    flush()
    return context


def ensure_structure_ctx(conn, cfg):
    """Idempotent within a connection.

    Fast path (after migration 0023): if structure_ctx_cache is current (game
    count unchanged since last build), the TEMP TABLE is created from the
    32k-row cache in <100ms instead of running compute_structure_context()
    (~11-12s cold on 32k games / 2.3M moves).  Stale or absent cache falls
    back to a full rebuild and persists the result for the next start.
    """
    if conn.execute("SELECT name FROM sqlite_temp_master WHERE name='structure_ctx'").fetchone():
        return

    game_count = conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]
    meta = conn.execute("SELECT structure_game_count FROM ctx_cache_meta WHERE id=1").fetchone()
    cache_current = (meta and meta[0] == game_count and game_count > 0
                     and conn.execute("SELECT COUNT(*) FROM structure_ctx_cache").fetchone()[0] > 0)

    if cache_current:
        conn.execute("""CREATE TEMP TABLE structure_ctx (
            game_id TEXT PRIMARY KEY, middlegame_sig TEXT, endgame_sig TEXT, endgame_ply INTEGER
        )""")
        conn.execute("INSERT INTO structure_ctx SELECT * FROM structure_ctx_cache")
        return

    context = compute_structure_context(
        conn, cfg["analytics"]["middlegame_ply"], cfg["analytics"]["endgame_max_pieces"])

    conn.execute("DELETE FROM structure_ctx_cache")
    conn.executemany("INSERT INTO structure_ctx_cache VALUES (?,?,?,?)", context)
    conn.execute("UPDATE ctx_cache_meta SET structure_game_count=?, built_at=CURRENT_TIMESTAMP WHERE id=1",
                 (game_count,))
    conn.commit()

    conn.execute("""CREATE TEMP TABLE structure_ctx (
        game_id TEXT PRIMARY KEY, middlegame_sig TEXT, endgame_sig TEXT, endgame_ply INTEGER
    )""")
    conn.execute("INSERT INTO structure_ctx SELECT * FROM structure_ctx_cache")
