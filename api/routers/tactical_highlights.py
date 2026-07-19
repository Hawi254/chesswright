"""GET /api/tactical-highlights/reel -- the tactical highlights reel (moved
from api/main.py,
docs/superpowers/specs/2026-07-17-api-main-router-split-design.md; router
added per that plan's Deviation #1 -- this page shipped 2026-07-15 and the
spec's own file-layout list predates it). No cache -- reads directly on
every call, same as the original.
"""
from fastapi import APIRouter

from api.db import get_db_connections
from api.serialization import _json_safe

import data

router = APIRouter()


@router.get("/api/tactical-highlights/reel")
def tactical_highlights_reel():
    sqlite_conn, duck_conn = get_db_connections()
    return _json_safe(data.build_highlight_reel(sqlite_conn, duck_conn))
