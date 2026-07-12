"""Integration tests for the FastAPI spike's data-layer reuse.

api/db.py calls dashboard/_common.py's get_connections() directly instead
of reimplementing DuckDB-snapshot safety from scratch -- that machinery
(per-PID snapshot + locked-connection wrapper) is the hard-won fix for a
real corruption incident (see the duckdb_sqlite_same_process_hazard
project memory), not something to risk reinventing. This file locks in
that get_connections() is actually safe to call from a plain process with
no active Streamlit script run, which is the whole premise api/db.py
depends on.
"""
import pathlib
import shutil
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
DASHBOARD_DIR = REPO_ROOT / "dashboard"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(DASHBOARD_DIR))


@pytest.mark.integration
def test_get_connections_works_outside_streamlit(migrated_db_path, monkeypatch, tmp_path):
    scratch_config = tmp_path / "config.yaml"
    shutil.copy(REPO_ROOT / "config.yaml", scratch_config)

    import config as _config
    # monkeypatch.setattr (not importlib.reload while CHESSWRIGHT_CONFIG_PATH
    # is monkeypatched) -- reload re-evaluates DEFAULT_CONFIG_PATH from
    # the env var but is never reloaded back, leaking this scratch path
    # into every later test in the same pytest process (confirmed live:
    # broke dashboard/test_app.py's and tests/ui/test_pages.py's real-DB
    # checks when run after this file). monkeypatch.setattr reverts
    # automatically at teardown, same as it does for setenv.
    monkeypatch.setattr(_config, "DEFAULT_CONFIG_PATH", scratch_config)
    _config.set_player_name("spike_test_player", path=str(scratch_config))
    _config.set_database_path(str(migrated_db_path), path=str(scratch_config))

    import _common
    _common.get_connections.clear()  # st.cache_resource is process-wide;
                                      # force a fresh read for this config.
    sqlite_conn, duck_conn = _common.get_connections()

    assert duck_conn.execute("SELECT COUNT(*) FROM db.games").fetchone()[0] == 0
    assert sqlite_conn.execute("SELECT COUNT(*) FROM games").fetchone()[0] == 0


from fastapi.testclient import TestClient


@pytest.fixture
def api_client(migrated_db_path, monkeypatch, tmp_path):
    scratch_config = tmp_path / "config.yaml"
    shutil.copy(REPO_ROOT / "config.yaml", scratch_config)

    import config as _config
    # See test_get_connections_works_outside_streamlit's comment above:
    # monkeypatch.setattr, not importlib.reload, so this reverts at
    # teardown instead of leaking into later tests in this process.
    monkeypatch.setattr(_config, "DEFAULT_CONFIG_PATH", scratch_config)
    _config.set_player_name("spike_test_player", path=str(scratch_config))
    _config.set_database_path(str(migrated_db_path), path=str(scratch_config))

    import _common
    _common.get_connections.clear()

    import api.main as api_main
    api_main.reset_caches()  # module-level TTL caches persist across tests
                              # in this process otherwise, since api.main is only
                              # ever imported once.
    return TestClient(api_main.app)


@pytest.mark.integration
def test_headline_stats_endpoint(api_client):
    resp = api_client.get("/api/overview/headline-stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_games"] == 0
    assert body["analyzed_games"] == 0


@pytest.mark.integration
def test_rating_trajectory_endpoint(api_client):
    resp = api_client.get("/api/overview/rating-trajectory")
    assert resp.status_code == 200
    assert resp.json() == []  # empty migrated DB has no games


@pytest.mark.integration
def test_rating_snapshot_endpoint(api_client):
    resp = api_client.get("/api/overview/rating-snapshot")
    assert resp.status_code == 200
    assert isinstance(resp.json(), dict)


@pytest.mark.integration
def test_current_streak_endpoint(api_client):
    resp = api_client.get("/api/overview/current-streak")
    assert resp.status_code == 200
    assert resp.json() == {"outcome": None, "length": 0}


@pytest.mark.integration
def test_career_findings_endpoint_empty_db(api_client):
    resp = api_client.get("/api/overview/career-findings")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.integration
def test_career_findings_endpoint_ttl_cache(api_client, monkeypatch):
    import data

    call_count = {"n": 0}

    def fake_get_headline_stats(*args, **kwargs):
        return {"total_games": 10, "analyzed_games": 10, "acpl": 45.0,
                 "blunder_rate": 5.0, "win_pct": 55.0, "n_analyzed_moves": 200}

    def fake_get_career_findings(*args, **kwargs):
        call_count["n"] += 1
        return [{"title": "Test finding", "headline": "h", "detail": "d",
                  "polarity": "strength", "severity": "low", "category": "general"}]

    monkeypatch.setattr(data, "get_headline_stats", fake_get_headline_stats)
    monkeypatch.setattr(data, "get_career_findings", fake_get_career_findings)

    resp1 = api_client.get("/api/overview/career-findings")
    resp2 = api_client.get("/api/overview/career-findings")

    assert resp1.status_code == 200
    assert resp2.status_code == 200
    assert resp1.json() == resp2.json()
    assert call_count["n"] == 1


@pytest.mark.integration
def test_narrative_endpoint_empty_db(api_client):
    resp = api_client.get("/api/overview/narrative")
    assert resp.status_code == 200
    assert resp.json() == {"narrative": "No games yet -- fetch some games to get started."}


@pytest.mark.integration
def test_narrative_endpoint_ttl_cache(api_client, monkeypatch):
    import narrative

    call_count = {"n": 0}

    def fake_generate_career_narrative(*args, **kwargs):
        call_count["n"] += 1
        return "Test narrative text."

    monkeypatch.setattr(narrative, "generate_career_narrative", fake_generate_career_narrative)

    resp1 = api_client.get("/api/overview/narrative")
    resp2 = api_client.get("/api/overview/narrative")

    assert resp1.status_code == 200
    assert resp2.status_code == 200
    assert resp1.json() == resp2.json() == {"narrative": "Test narrative text."}
    assert call_count["n"] == 1


@pytest.mark.integration
def test_achievements_endpoint_empty_db(api_client):
    resp = api_client.get("/api/overview/achievements")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.integration
def test_achievements_endpoint_returns_unlocked_achievements(api_client, monkeypatch):
    import achievements

    def fake_get_unlocked_achievements(conn, limit=4):
        assert limit == 4
        return [{"achievement_id": "first_win", "name": "First Win",
                  "description": "Win your first recorded game.",
                  "unlocked_at": "2026-01-01T00:00:00"}]

    monkeypatch.setattr(achievements, "get_unlocked_achievements", fake_get_unlocked_achievements)

    resp = api_client.get("/api/overview/achievements")
    assert resp.status_code == 200
    assert resp.json() == [{"achievement_id": "first_win", "name": "First Win",
                             "description": "Win your first recorded game.",
                             "unlocked_at": "2026-01-01T00:00:00"}]


@pytest.mark.integration
def test_config_default_path_restored_after_api_client_tests(migrated_db_path):
    """Regression test for a cross-test global-state leak: every test
    above uses the api_client fixture, which repoints config resolution
    at a scratch tmp_path config.yaml for the duration of its own test.
    That used to be done via importlib.reload(_config) while
    CHESSWRIGHT_CONFIG_PATH was monkeypatched -- reload re-evaluates
    config.py's module-level DEFAULT_CONFIG_PATH from the currently-set
    env var, but nothing ever reloaded it back, so DEFAULT_CONFIG_PATH
    stayed pointed at that test's (by-then-deleted) scratch path for the
    rest of the pytest process. Confirmed live: dashboard/test_app.py and
    tests/ui/test_pages.py's real-DB checks correctly saw the real
    ~32k-game database when run alone, but silently skipped ("0 games")
    when run in the same process after this file -- resolve_db_path()
    was reading the leaked scratch path, not config.yaml. Fixed by
    monkeypatch.setattr(config, "DEFAULT_CONFIG_PATH", ...) instead of
    importlib.reload, so pytest's own monkeypatch teardown reverts it
    automatically after each test. This test runs last in this file (by
    definition order, no test-randomization plugin is configured) and
    just checks that global reverted correctly."""
    import config
    assert config.DEFAULT_CONFIG_PATH == REPO_ROOT / "config.yaml"
