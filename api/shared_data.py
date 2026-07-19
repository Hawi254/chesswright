"""Caches shared across router-module boundaries -- each of these three
TTLCache instances is read from two or more api/routers/*.py files, so it
must be a single shared object rather than a private module-level variable
in whichever router "owns" the endpoint that primarily fills it (see
docs/superpowers/specs/2026-07-17-api-main-router-split-design.md and the
router-split plan's Deviations section for why each of the three is here).

get_headline_stats_cached() is a real behavior change (data.get_headline_stats
is a full moves-JOIN-games aggregate scan, called at 9 sites with no cache of
its own today, two of them uncached on every Overview page load, two more
each doing their own redundant call inside their own separate _TTLCache) --
unifying those 9 sites onto one cached wrapper is the fix.

_career_findings_cache and _points_ledger_cache are NOT behavior changes --
they already are one shared cache today; they're plain exported TTLCache
instances (not wrapped in an accessor function) so each of their existing
call sites can keep its own compute() closure exactly as written, since the
closures differ slightly between call sites (e.g. career_findings() has a
zero-analyzed-games guard baked into its closure that the /generate call
sites don't) and collapsing them onto one shared function would either
change behavior or require guessing which shape is "correct."
"""
from api.cache import TTLCache
from api.db import get_db_connections

import data

_headline_stats_cache = TTLCache(60)
_career_findings_cache = TTLCache(60)
_points_ledger_cache = TTLCache(60)


def get_headline_stats_cached():
    sqlite_conn, duck_conn = get_db_connections()
    return _headline_stats_cache.get(lambda: data.get_headline_stats(duck_conn, sqlite_conn))


def reset_caches():
    """Test-only hook, mirrors api.main's own reset_caches() -- api.shared_data
    is a singleton module shared across every test in a pytest process."""
    _headline_stats_cache.clear()
    _career_findings_cache.clear()
    _points_ledger_cache.clear()
