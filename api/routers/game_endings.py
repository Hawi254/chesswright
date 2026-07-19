"""GET /api/game-endings/* -- the "how do my games actually end" tree
(moved from api/main.py,
docs/superpowers/specs/2026-07-17-api-main-router-split-design.md; router
added per that plan's Deviation #1 -- this page shipped 2026-07-15 and the
spec's own file-layout list predates it).
"""
from fastapi import APIRouter, HTTPException

from api.cache import TTLCache
from api.db import get_db_connections
from api.serialization import _json_safe

import data

router = APIRouter()

_PIECE_ORDER = ["Q", "R", "B", "N", "P", "K"]
_PIECE_NAME = {"Q": "queen", "R": "rook", "B": "bishop", "N": "knight", "P": "pawn", "K": "king"}
_VALID_TIME_CONTROLS = ("bullet", "blitz", "rapid", "classical")

_ending_tree_cache = {tc: TTLCache(60) for tc in (None,) + _VALID_TIME_CONTROLS}
_ending_summary_cache = TTLCache(60)


def reset_caches():
    """Test-only hook, mirrors api.main's own reset_caches()."""
    for _cache in _ending_tree_cache.values():
        _cache.clear()
    _ending_summary_cache.clear()


@router.get("/api/game-endings/tree")
def game_endings_tree(time_control: str | None = None):
    tc = time_control if time_control in _VALID_TIME_CONTROLS else None

    def compute():
        sqlite_conn, duck_conn = get_db_connections()
        return data.build_ending_tree(sqlite_conn, duck_conn, time_control=tc)
    return _ending_tree_cache[tc].get(compute)


@router.get("/api/game-endings/games")
def game_endings_games(path: str, time_control: str | None = None):
    tc = time_control if time_control in _VALID_TIME_CONTROLS else None
    sqlite_conn, duck_conn = get_db_connections()
    try:
        result = data.get_games_for_ending_node(sqlite_conn, duck_conn, path, time_control=tc)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    kind = result["secondary_chart_kind"]
    rows = result["secondary_chart"] or []
    if kind == "piece":
        order = {p: i for i, p in enumerate(_PIECE_ORDER)}
        rows.sort(key=lambda r: order.get(r["hung_piece"], len(_PIECE_ORDER)))
        normalized = [
            {"label": _PIECE_NAME.get(r["hung_piece"], r["hung_piece"]).title(), "n": r["n"], "pct": r["pct"]}
            for r in rows
        ]
    elif kind in ("mate", "scramble"):
        normalized = [{"label": r["bucket"], "n": r["n"], "pct": r["pct"]} for r in rows]
    else:
        normalized = None

    return _json_safe({
        "game_ids": result["game_ids"],
        "total": result["total"],
        "secondary_chart": normalized,
        "secondary_chart_kind": kind,
    })


@router.get("/api/game-endings/summary")
def game_endings_summary():
    def compute():
        sqlite_conn, duck_conn = get_db_connections()
        return _json_safe(data.build_ending_summary(sqlite_conn, duck_conn))
    return _ending_summary_cache.get(compute)
