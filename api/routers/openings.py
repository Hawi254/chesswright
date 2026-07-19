"""GET/POST /api/openings/* -- the openings table, per-opening Claude
narrative (+generate), repeated positions, position-by-FEN lookup,
repertoire holes, and ply accuracy (moved from api/main.py,
docs/superpowers/specs/2026-07-17-api-main-router-split-design.md).
"""
import pandas as pd
from fastapi import APIRouter, HTTPException

from api.cache import TTLCache
from api.db import get_db_connections
from api.serialization import _json_safe
import api.shared_data as shared_data

import analytics
import claude_narrative
import data

router = APIRouter()

_openings_table_cache = TTLCache(60)


def reset_caches():
    """Test-only hook, mirrors api.main's own reset_caches()."""
    _openings_table_cache.clear()


@router.get("/api/openings/table")
def openings_table():
    def compute():
        sqlite_conn, duck_conn = get_db_connections()
        return _json_safe(
            data.get_openings_table(duck_conn, sqlite_conn, min_games=1).to_dict(orient="records"))
    return _openings_table_cache.get(compute)


@router.get("/api/openings/{family}/{color}/narrative")
def get_opening_narrative(family: str, color: str):
    sqlite_conn, _ = get_db_connections()
    cached = data.get_cached_narrative(sqlite_conn, "opening", f"{family}|{color}")
    if cached is None:
        return {"narrative": None, "generated_at": None}
    response_text, generated_at = cached
    return {"narrative": response_text, "generated_at": generated_at}


@router.post("/api/openings/{family}/{color}/narrative/generate")
def generate_opening_narrative(family: str, color: str):
    sqlite_conn, duck_conn = get_db_connections()
    table_rows = _openings_table_cache.get(
        lambda: _json_safe(
            data.get_openings_table(duck_conn, sqlite_conn, min_games=1).to_dict(orient="records")))
    row = next((r for r in table_rows
                if r["opening_family"] == family and r["player_color"] == color), None)
    if row is None:
        raise HTTPException(status_code=404, detail="Unknown opening")
    stats = shared_data.get_headline_stats_cached()
    try:
        response_text = claude_narrative.generate_opening_commentary(
            pd.Series(row), stats["win_pct"], stats["analyzed_games"], stats["total_games"])
    except claude_narrative.MissingApiKeyError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Claude API call failed: {e}")
    data.save_narrative(sqlite_conn, "opening", f"{family}|{color}", response_text, claude_narrative.MODEL)
    return {"narrative": response_text}


@router.get("/api/openings/repeated-positions")
def repeated_positions(top_n: int = 20):
    sqlite_conn, _ = get_db_connections()
    analytics.ensure_repeated_positions_cache(sqlite_conn)
    rows = data.get_most_repeated_positions(sqlite_conn, top_n=top_n).to_dict(orient="records")
    # zobrist_hash is a 64-bit signed int -- routinely exceeds JS's
    # Number.MAX_SAFE_INTEGER (2^53), so a JSON number silently loses
    # precision on the client (found live: a real row's hash arrived
    # off by hundreds, and /api/openings/position-fen's exact-match SQL
    # then 404'd on every click). Round-tripped as an opaque string
    # instead -- the frontend never does arithmetic on it.
    for row in rows:
        row["zobrist_hash"] = str(row["zobrist_hash"])
    return rows


@router.get("/api/openings/position-fen")
def position_fen(ply: int, zobrist_hash: str):
    sqlite_conn, _ = get_db_connections()
    fen = data.get_position_fen(sqlite_conn, ply, int(zobrist_hash))
    if fen is None:
        raise HTTPException(status_code=404, detail="Position not found")
    return {"fen": fen}


@router.get("/api/openings/repertoire-holes")
def repertoire_holes(min_appearances: int = 5, top_n: int = 20):
    sqlite_conn, _ = get_db_connections()
    analytics.ensure_repertoire_holes_cache(sqlite_conn)
    return _json_safe(data.get_repertoire_holes(
        sqlite_conn, min_appearances=min_appearances, top_n=top_n).to_dict(orient="records"))


@router.get("/api/openings/ply-accuracy")
def ply_accuracy(opening_family: str, player_color: str, min_appearances: int = 3):
    _, duck_conn = get_db_connections()
    return data.get_opening_ply_accuracy(
        duck_conn, opening_family, player_color, min_appearances=min_appearances).to_dict(orient="records")
