"""GET /api/overview/* -- the Overview page: engine status, win rate,
headline stats, rating/ACPL trajectory, rating snapshot, headline trend,
current streak, career findings, achievements, career narrative, career
highlight, coaching-plan status (moved from api/main.py,
docs/superpowers/specs/2026-07-17-api-main-router-split-design.md).
"""
from fastapi import APIRouter

from api.cache import TTLCache
from api.db import get_db_connections
import api.shared_data as shared_data

import achievements
import data
import engine_status
import narrative
import snapshots
from version import __version__ as _app_version

router = APIRouter()

_narrative_cache = TTLCache(60)
_career_highlight_cache = TTLCache(60)


def reset_caches():
    """Test-only hook, mirrors api.main's own reset_caches()."""
    _narrative_cache.clear()
    _career_highlight_cache.clear()


@router.get("/api/overview/engine-status")
def engine_status_endpoint():
    status = engine_status.get_engine_status_summary()
    return {"connected": status["connected"], "version": status["version"], "app_version": _app_version}


@router.get("/api/overview/win-rate-by-color")
def win_rate_by_color():
    _, duck_conn = get_db_connections()
    df = data.get_win_rate_by_color(duck_conn)
    return df.to_dict(orient="records")


@router.get("/api/overview/headline-stats")
def headline_stats():
    return shared_data.get_headline_stats_cached()


@router.get("/api/overview/rating-trajectory")
def rating_trajectory():
    _, duck_conn = get_db_connections()
    df = data.get_rating_trajectory(duck_conn)
    return df.to_dict(orient="records")


@router.get("/api/overview/acpl-trajectory")
def acpl_trajectory():
    _, duck_conn = get_db_connections()
    df = data.get_acpl_trajectory(duck_conn)
    return df.to_dict(orient="records")


@router.get("/api/overview/rating-snapshot")
def rating_snapshot():
    _, duck_conn = get_db_connections()
    return data.get_rating_snapshot(duck_conn)


@router.get("/api/overview/headline-trend")
def headline_trend():
    sqlite_conn, _ = get_db_connections()
    stats = shared_data.get_headline_stats_cached()
    return snapshots.get_headline_trend(sqlite_conn, stats)


@router.get("/api/overview/current-streak")
def current_streak():
    _, duck_conn = get_db_connections()
    return data.get_current_streak(duck_conn)


@router.get("/api/overview/career-findings")
def career_findings():
    def compute():
        sqlite_conn, duck_conn = get_db_connections()
        stats = shared_data.get_headline_stats_cached()
        if stats.get("analyzed_games", 0) == 0:
            return []
        return data.get_career_findings(duck_conn, sqlite_conn, stats.get("blunder_rate"))
    return shared_data._career_findings_cache.get(compute)


@router.get("/api/overview/achievements")
def achievements_endpoint():
    sqlite_conn, _ = get_db_connections()
    return achievements.get_unlocked_achievements(sqlite_conn, limit=4)


@router.get("/api/overview/narrative")
def narrative_endpoint():
    def compute():
        _, duck_conn = get_db_connections()
        stats = shared_data.get_headline_stats_cached()
        rating_df = data.get_rating_trajectory(duck_conn)
        explorer_df = data.get_game_explorer_table(duck_conn)
        top_game = explorer_df.iloc[0] if len(explorer_df) else None
        return {"narrative": narrative.generate_career_narrative(stats, rating_df, top_game)}
    return _narrative_cache.get(compute)


@router.get("/api/overview/career-highlight")
def career_highlight():
    def compute():
        _, duck_conn = get_db_connections()
        explorer_df = data.get_game_explorer_table(duck_conn)
        top = explorer_df.head(3)
        return [
            {
                "game_id": row["game_id"],
                "opponent_name": row["opponent_name"],
                "utc_date": row["utc_date"],
                "outcome_for_player": row["outcome_for_player"],
                "is_comeback": bool(row["is_comeback"]),
                "is_giant_killing": bool(row["is_giant_killing"]),
                "is_brilliant_find": bool(row["is_brilliant_find"]),
                "is_blunder_fest": bool(row["is_blunder_fest"]),
                "is_nail_biter": bool(row["is_nail_biter"]),
            }
            for _, row in top.iterrows()
        ]
    return _career_highlight_cache.get(compute)


@router.get("/api/overview/coaching-plan-status")
def coaching_plan_status():
    sqlite_conn, _ = get_db_connections()
    return {"cached": bool(data.get_cached_narrative(sqlite_conn, "coaching", "recommendations"))}
