"""GET/POST /api/opening-tree/* -- the Pro Opening Tree explorer (moves,
map, timeline, changes, jump-to-representative-line, add-SRS-card) (moved
from api/main.py,
docs/superpowers/specs/2026-07-17-api-main-router-split-design.md).
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.db import get_db_connections

import data
import pro_gate

router = APIRouter()


@router.get("/api/opening-tree/moves")
def opening_tree_moves(fen: str, ply: int, color: str, min_games: int = 3):
    if not pro_gate.is_pro_active():
        raise HTTPException(status_code=403, detail="Pro is not licensed")
    try:
        from chesswright_pro import opening_tree_api
    except ImportError:
        raise HTTPException(status_code=501, detail="chesswright_pro not installed")
    sqlite_conn, _ = get_db_connections()
    return opening_tree_api.moves(sqlite_conn, fen, ply, color, min_games)


@router.get("/api/opening-tree/map")
def opening_tree_map(color: str, min_games: int = 3):
    if not pro_gate.is_pro_active():
        raise HTTPException(status_code=403, detail="Pro is not licensed")
    try:
        from chesswright_pro import opening_tree_api
    except ImportError:
        raise HTTPException(status_code=501, detail="chesswright_pro not installed")
    sqlite_conn, duck_conn = get_db_connections()
    return opening_tree_api.map_nodes(sqlite_conn, duck_conn, color, min_games)


@router.get("/api/opening-tree/timeline")
def opening_tree_timeline(fen: str, color: str):
    if not pro_gate.is_pro_active():
        raise HTTPException(status_code=403, detail="Pro is not licensed")
    try:
        from chesswright_pro import opening_tree_api
    except ImportError:
        raise HTTPException(status_code=501, detail="chesswright_pro not installed")
    sqlite_conn, _ = get_db_connections()
    return opening_tree_api.timeline(sqlite_conn, fen, color)


@router.get("/api/opening-tree/changes")
def opening_tree_changes(color: str, min_games: int = 3, split_year: int | None = None):
    if not pro_gate.is_pro_active():
        raise HTTPException(status_code=403, detail="Pro is not licensed")
    try:
        from chesswright_pro import opening_tree_api
    except ImportError:
        raise HTTPException(status_code=501, detail="chesswright_pro not installed")
    sqlite_conn, duck_conn = get_db_connections()
    return opening_tree_api.changes(sqlite_conn, duck_conn, color, min_games, split_year)


@router.get("/api/opening-tree/jump")
def opening_tree_jump(opening_family: str, color: str):
    # Not Pro-gated: calls a core primitive directly. The page itself
    # stays inaccessible to non-Pro users (full-page upsell), so this
    # doesn't leak the feature -- same reasoning as /srs below.
    sqlite_conn, _ = get_db_connections()
    path = data.get_representative_path_for_family(sqlite_conn, opening_family, color)
    if path is None:
        raise HTTPException(status_code=404, detail="No games found for this opening in this color")
    return {"path": path}


class AddOpeningSrsCardRequest(BaseModel):
    fen: str
    best_move_san: str
    context: str | None = None


@router.post("/api/opening-tree/srs")
def opening_tree_add_srs(body: AddOpeningSrsCardRequest):
    sqlite_conn, _ = get_db_connections()
    count = data.add_cards(sqlite_conn, [{
        "fen": body.fen,
        "source": "opening_tree",
        "best_move_san": body.best_move_san,
        "context": body.context,
    }])
    return {"added": count}
