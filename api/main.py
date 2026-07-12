"""FastAPI service wrapping existing, Streamlit-free dashboard/data/*.py
and dashboard/narrative.py functions. No new business logic; no auth; no
write paths. See
docs/superpowers/specs/2026-07-12-frontend-rewrite-spike-design.md and
docs/superpowers/specs/2026-07-12-overview-identity-zone-port-design.md.
"""
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.db import get_db_connections

import data
import narrative
import achievements

app = FastAPI(title="Chesswright API")

# The Vite dev server (5173) and this API (8123) are different origins,
# so the browser blocks the frontend's fetch() calls without this --
# found live while verifying Task 7 (requests failed with a CORS error,
# page stuck on "Loading..." forever). Wide open on purpose: spike-only,
# localhost-bound, no auth, read-only endpoints (see module docstring).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
)


class _TTLCache:
    """Small hand-written cache for one expensive, argument-less
    computation -- not a general caching framework. 60s bounds staleness
    to roughly one minute after a mid-session sync/analysis batch changes
    the underlying data, rather than caching until process restart
    (functools.lru_cache with no TTL was considered and rejected for this
    reason -- see the Overview identity-zone port design spec)."""

    def __init__(self, ttl_seconds):
        self._ttl_seconds = ttl_seconds
        self._value = None
        self._computed_at = None

    def get(self, compute):
        now = time.monotonic()
        if self._computed_at is None or (now - self._computed_at) > self._ttl_seconds:
            self._value = compute()
            self._computed_at = now
        return self._value

    def clear(self):
        self._value = None
        self._computed_at = None


_narrative_cache = _TTLCache(60)
_career_findings_cache = _TTLCache(60)


def reset_caches():
    """Test-only hook: api.main is a singleton module shared across every
    test in a pytest process, so a cache populated by one test would
    otherwise leak into the next one."""
    _narrative_cache.clear()
    _career_findings_cache.clear()


@app.get("/api/overview/headline-stats")
def headline_stats():
    sqlite_conn, duck_conn = get_db_connections()
    return data.get_headline_stats(duck_conn, sqlite_conn)


@app.get("/api/overview/rating-trajectory")
def rating_trajectory():
    _, duck_conn = get_db_connections()
    df = data.get_rating_trajectory(duck_conn)
    return df.to_dict(orient="records")


@app.get("/api/overview/rating-snapshot")
def rating_snapshot():
    _, duck_conn = get_db_connections()
    return data.get_rating_snapshot(duck_conn)


@app.get("/api/overview/current-streak")
def current_streak():
    _, duck_conn = get_db_connections()
    return data.get_current_streak(duck_conn)


@app.get("/api/overview/career-findings")
def career_findings():
    def compute():
        sqlite_conn, duck_conn = get_db_connections()
        stats = data.get_headline_stats(duck_conn, sqlite_conn)
        if stats.get("analyzed_games", 0) == 0:
            return []
        return data.get_career_findings(duck_conn, sqlite_conn, stats.get("blunder_rate"))
    return _career_findings_cache.get(compute)


@app.get("/api/overview/achievements")
def achievements_endpoint():
    sqlite_conn, _ = get_db_connections()
    return achievements.get_unlocked_achievements(sqlite_conn, limit=4)


@app.get("/api/overview/narrative")
def narrative_endpoint():
    def compute():
        sqlite_conn, duck_conn = get_db_connections()
        stats = data.get_headline_stats(duck_conn, sqlite_conn)
        rating_df = data.get_rating_trajectory(duck_conn)
        explorer_df = data.get_game_explorer_table(duck_conn)
        top_game = explorer_df.iloc[0] if len(explorer_df) else None
        return {"narrative": narrative.generate_career_narrative(stats, rating_df, top_game)}
    return _narrative_cache.get(compute)


@app.get("/api/nav/pages")
def nav_pages():
    return data.PAGE_CANDIDATES + data.SETTINGS_CANDIDATES
