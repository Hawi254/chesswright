"""GET/POST /api/insights/synthesis and /api/insights/coaching -- the
Insights page's two Claude-generated narrative panels (moved from
api/main.py,
docs/superpowers/specs/2026-07-17-api-main-router-split-design.md).

_insights_synthesis_cache and _insights_coaching_cache are declared and
cleared in reset_caches() but never actually used to cache anything --
insights_synthesis()/insights_coaching() call data.get_cached_narrative()
directly with no in-memory caching layer at all. This is pre-existing dead
code (confirmed by grep before this router split -- see the plan's
Deviation #5), preserved verbatim here rather than removed, since removing
it would be a behavior-preserving-but-unrequested cleanup this refactor
wasn't asked to make.
"""
from fastapi import APIRouter, HTTPException

from api.cache import TTLCache
from api.db import get_db_connections
from api.serialization import _narrative_response
import api.shared_data as shared_data

import claude_narrative
import data

router = APIRouter()

_insights_synthesis_cache = TTLCache(60)
_insights_coaching_cache = TTLCache(60)


def reset_caches():
    """Test-only hook, mirrors api.main's own reset_caches()."""
    _insights_synthesis_cache.clear()
    _insights_coaching_cache.clear()


@router.get("/api/insights/synthesis")
def insights_synthesis():
    sqlite_conn, _ = get_db_connections()
    return _narrative_response(data.get_cached_narrative(sqlite_conn, "findings", "summary"))


@router.post("/api/insights/synthesis/generate")
def generate_insights_synthesis():
    sqlite_conn, duck_conn = get_db_connections()
    stats = shared_data.get_headline_stats_cached()
    findings = shared_data._career_findings_cache.get(
        lambda: data.get_career_findings(duck_conn, sqlite_conn, stats.get("blunder_rate")))
    try:
        response_text = claude_narrative.generate_insights_synthesis(
            findings, stats["win_pct"], stats["analyzed_games"], stats["total_games"])
    except claude_narrative.MissingApiKeyError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Claude API call failed: {e}")
    data.save_narrative(sqlite_conn, "findings", "summary", response_text, claude_narrative.MODEL)
    return {"narrative": response_text}


@router.get("/api/insights/coaching")
def insights_coaching():
    sqlite_conn, _ = get_db_connections()
    return _narrative_response(data.get_cached_narrative(sqlite_conn, "coaching", "recommendations"))


@router.post("/api/insights/coaching/generate")
def generate_insights_coaching():
    sqlite_conn, duck_conn = get_db_connections()
    stats = shared_data.get_headline_stats_cached()
    findings = shared_data._career_findings_cache.get(
        lambda: data.get_career_findings(duck_conn, sqlite_conn, stats.get("blunder_rate")))
    try:
        response_text = claude_narrative.generate_coaching_recommendations(
            findings, stats["win_pct"], stats["analyzed_games"], stats["total_games"])
    except claude_narrative.MissingApiKeyError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Claude API call failed: {e}")
    data.save_narrative(sqlite_conn, "coaching", "recommendations", response_text, claude_narrative.MODEL)
    return {"narrative": response_text}
