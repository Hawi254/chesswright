"""Integration test for api/shared_data.py's get_headline_stats_cached() --
docs/superpowers/specs/2026-07-17-api-main-router-split-design.md's Testing
section: confirms the fix for the finding that data.get_headline_stats was
being called at 9 separate uncached/redundantly-cached sites. Mirrors the
existing pattern for _career_findings_cache etc. (see
tests/integration/test_api_points.py::TestPointsSummary::test_reset_caches_between_tests_ttl_cache).
"""
import pathlib
import shutil
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
DASHBOARD_DIR = REPO_ROOT / "dashboard"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(DASHBOARD_DIR))


@pytest.fixture
def api_client(migrated_db_path, monkeypatch, tmp_path):
    scratch_config = tmp_path / "config.yaml"
    shutil.copy(REPO_ROOT / "config.yaml", scratch_config)

    import config as _config
    monkeypatch.setattr(_config, "DEFAULT_CONFIG_PATH", scratch_config)
    _config.set_player_name("spike_test_player", path=str(scratch_config))
    _config.set_database_path(str(migrated_db_path), path=str(scratch_config))

    import connections
    connections.clear_cache()

    import api.main as api_main
    api_main.reset_caches()
    return api_main


@pytest.mark.integration
def test_get_headline_stats_cached_computes_once_within_ttl(api_client):
    import data
    import api.shared_data as shared_data

    call_count = {"n": 0}
    real = data.get_headline_stats

    def _counting(*args, **kwargs):
        call_count["n"] += 1
        return real(*args, **kwargs)

    try:
        data.get_headline_stats = _counting
        shared_data.get_headline_stats_cached()
        shared_data.get_headline_stats_cached()
        assert call_count["n"] == 1
        api_client.reset_caches()
        shared_data.get_headline_stats_cached()
        assert call_count["n"] == 2
    finally:
        data.get_headline_stats = real


@pytest.mark.integration
def test_overview_headline_stats_and_headline_trend_share_one_cached_call(api_client):
    """The real bug this fix closes: two endpoints hit directly on one
    Overview page load (headline-stats, headline-trend) must now compute the
    underlying scan once between them, not twice."""
    import data
    from fastapi.testclient import TestClient

    call_count = {"n": 0}
    real = data.get_headline_stats

    def _counting(*args, **kwargs):
        call_count["n"] += 1
        return real(*args, **kwargs)

    try:
        data.get_headline_stats = _counting
        client = TestClient(api_client.app)
        client.get("/api/overview/headline-stats")
        client.get("/api/overview/headline-trend")
        assert call_count["n"] == 1
    finally:
        data.get_headline_stats = real


@pytest.mark.integration
def test_reset_caches_clears_every_router(api_client):
    """One cache per router group that owns at least one, poked directly by
    populating it then confirming api_main.reset_caches() clears all of
    them -- guards against a cache being silently orphaned during a future
    router move (docs/superpowers/specs/2026-07-17-api-main-router-split-
    design.md's Testing section)."""
    import api.routers.ask as ask
    import api.routers.evolution as evolution
    import api.routers.game_endings as game_endings
    import api.routers.games as games
    import api.routers.insights as insights
    import api.routers.matchups as matchups
    import api.routers.openings as openings
    import api.routers.overview as overview
    import api.routers.patterns as patterns
    import api.routers.points as points
    import api.shared_data as shared_data

    # Populate one representative TTLCache per router group that owns one.
    shared_data._headline_stats_cache.get(lambda: {"probe": True})
    shared_data._career_findings_cache.get(lambda: ["probe"])
    shared_data._points_ledger_cache.get(lambda: "probe")
    overview._narrative_cache.get(lambda: "probe")
    overview._career_highlight_cache.get(lambda: "probe")
    games._game_explorer_cache.get(lambda: "probe")
    openings._openings_table_cache.get(lambda: "probe")
    game_endings._ending_summary_cache.get(lambda: "probe")
    points._points_summary_cache[None].get(lambda: "probe")
    evolution._evolution_counts_cache.get(lambda: "probe")
    insights._insights_synthesis_cache.get(lambda: "probe")  # dead cache -- see Deviation #5, still cleared
    ask._ask_brief_cache.get(lambda: "probe")
    matchups._matchups_static_cache.get(lambda: "probe")
    patterns._patterns_summary_cache.get(lambda: "probe")

    api_client.reset_caches()

    assert shared_data._headline_stats_cache._value is None
    assert shared_data._career_findings_cache._value is None
    assert shared_data._points_ledger_cache._value is None
    assert overview._narrative_cache._value is None
    assert overview._career_highlight_cache._value is None
    assert games._game_explorer_cache._value is None
    assert openings._openings_table_cache._value is None
    assert game_endings._ending_summary_cache._value is None
    assert points._points_summary_cache[None]._value is None
    assert evolution._evolution_counts_cache._value is None
    assert insights._insights_synthesis_cache._value is None
    assert ask._ask_brief_cache._value is None
    assert matchups._matchups_static_cache._value is None
    assert patterns._patterns_summary_cache._value is None
