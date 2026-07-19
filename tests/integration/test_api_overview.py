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
def test_open_connections_works_outside_streamlit(migrated_db_path, monkeypatch, tmp_path):
    scratch_config = tmp_path / "config.yaml"
    shutil.copy(REPO_ROOT / "config.yaml", scratch_config)

    import config as _config
    monkeypatch.setattr(_config, "DEFAULT_CONFIG_PATH", scratch_config)
    _config.set_player_name("spike_test_player", path=str(scratch_config))
    _config.set_database_path(str(migrated_db_path), path=str(scratch_config))

    import connections
    connections.clear_cache()  # process-wide singleton; force a fresh read for this config.
    sqlite_conn, duck_conn = connections.open_connections()

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

    import connections
    connections.clear_cache()

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
    # acpl is None on an empty DB -> both gated fields stay None too.
    assert body["implied_rating"] is None
    assert body["rating_confidence"] is None


@pytest.mark.integration
def test_headline_stats_endpoint_omits_rating_below_move_threshold(api_client, monkeypatch):
    import analytics

    def fake_acpl_and_blunder_rate(*args, **kwargs):
        # n_moves=15 is below MIN_ANALYZED_MOVES_FOR_RATING_BENCHMARK (20).
        return (15, 3, 50.0, 5.0)

    monkeypatch.setattr(analytics, "acpl_and_blunder_rate", fake_acpl_and_blunder_rate)

    resp = api_client.get("/api/overview/headline-stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body["acpl"] == 50.0
    assert body["implied_rating"] is None
    assert body["rating_confidence"] is None


@pytest.mark.integration
def test_headline_stats_endpoint_includes_rating_above_move_threshold(api_client, monkeypatch):
    import analytics

    def fake_acpl_and_blunder_rate(*args, **kwargs):
        # n_moves=25 clears the "low" threshold (20) but not "medium" (60).
        return (25, 5, 50.0, 5.0)

    monkeypatch.setattr(analytics, "acpl_and_blunder_rate", fake_acpl_and_blunder_rate)

    resp = api_client.get("/api/overview/headline-stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body["acpl"] == 50.0
    # 3100 * e^(-0.01 * 50) ~= 1880.24 -> rounds to 1880.
    assert body["implied_rating"] == 1880
    assert body["rating_confidence"] == "low"


@pytest.mark.integration
def test_rating_trajectory_endpoint(api_client):
    resp = api_client.get("/api/overview/rating-trajectory")
    assert resp.status_code == 200
    assert resp.json() == []  # empty migrated DB has no games


@pytest.mark.integration
def test_acpl_trajectory_endpoint(api_client):
    resp = api_client.get("/api/overview/acpl-trajectory")
    assert resp.status_code == 200
    assert resp.json() == []  # empty migrated DB has no analyzed games


@pytest.mark.integration
def test_rating_snapshot_endpoint(api_client):
    resp = api_client.get("/api/overview/rating-snapshot")
    assert resp.status_code == 200
    assert isinstance(resp.json(), dict)


@pytest.mark.integration
def test_headline_trend_endpoint_gated_when_no_old_snapshot(api_client):
    resp = api_client.get("/api/overview/headline-trend")
    assert resp.status_code == 200
    assert resp.json() == {
        "compared_to_date": None, "acpl_delta": None, "blunder_rate_delta": None,
        "win_pct_delta": None, "implied_rating_delta": None,
    }


@pytest.mark.integration
def test_headline_trend_endpoint_populated(api_client, migrated_db_path, monkeypatch):
    import datetime
    import sqlite3

    import analytics

    def fake_acpl_and_blunder_rate(*args, **kwargs):
        # n_moves=200 clears every rating-confidence threshold, so
        # implied_rating on the "current" side is guaranteed non-None.
        return (200, 10, 40.0, 5.0)
    monkeypatch.setattr(analytics, "acpl_and_blunder_rate", fake_acpl_and_blunder_rate)

    old_date = (datetime.date.today() - datetime.timedelta(days=120)).isoformat()
    conn = sqlite3.connect(migrated_db_path)
    conn.execute("""
        INSERT INTO metric_snapshots
            (snapshot_date, total_games, analyzed_games, acpl, blunder_rate, win_pct,
             n_analyzed_moves, implied_rating, rating_confidence)
        VALUES (?, 5, 5, 50.0, 8.0, 45.0, 100, 1900, 'medium')
    """, (old_date,))
    conn.commit()
    conn.close()

    resp = api_client.get("/api/overview/headline-trend")
    assert resp.status_code == 200
    body = resp.json()
    assert body["compared_to_date"] == old_date
    assert body["acpl_delta"] == pytest.approx(40.0 - 50.0)
    assert body["blunder_rate_delta"] == pytest.approx(5.0 - 8.0)
    # win_pct on an empty-games migrated DB is None regardless of the
    # acpl_and_blunder_rate monkeypatch (it comes from a separate duck_conn
    # query over db.games) -- asserting None here, not a fabricated value,
    # avoids depending on DuckDB-snapshot-refresh timing for a games row
    # inserted after the api_client fixture already opened its connections
    # (see the duckdb_sqlite_same_process_hazard project memory).
    assert body["win_pct_delta"] is None
    assert body["implied_rating_delta"] is not None


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
def test_career_highlight_endpoint_empty_db(api_client):
    resp = api_client.get("/api/overview/career-highlight")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.integration
def test_career_highlight_endpoint_returns_top_3(api_client, monkeypatch):
    import pandas as pd
    import data

    call_count = {"n": 0}

    def fake_get_game_explorer_table(*args, **kwargs):
        call_count["n"] += 1
        return pd.DataFrame([
            {"game_id": f"game{i}", "opponent_name": f"Opponent{i}", "utc_date": "2026-01-01",
             "outcome_for_player": "win", "is_comeback": i == 0, "is_giant_killing": False,
             "is_brilliant_find": False, "is_blunder_fest": False, "is_nail_biter": False,
             "drama_score": 300 - i}
            for i in range(5)
        ])

    monkeypatch.setattr(data, "get_game_explorer_table", fake_get_game_explorer_table)

    resp1 = api_client.get("/api/overview/career-highlight")
    resp2 = api_client.get("/api/overview/career-highlight")

    assert resp1.status_code == 200
    body = resp1.json()
    assert len(body) == 3
    assert [g["game_id"] for g in body] == ["game0", "game1", "game2"]
    assert body[0]["is_comeback"] is True
    assert body[1]["is_comeback"] is False
    assert resp2.json() == body
    assert call_count["n"] == 1  # TTL cache still in effect


@pytest.mark.integration
def test_career_highlight_endpoint_returns_fewer_than_3_when_db_has_fewer(api_client, monkeypatch):
    import pandas as pd
    import data

    def fake_get_game_explorer_table(*args, **kwargs):
        return pd.DataFrame([{
            "game_id": "only_game", "opponent_name": "TestOpponent", "utc_date": "2026-01-01",
            "outcome_for_player": "win", "is_comeback": True, "is_giant_killing": False,
            "is_brilliant_find": False, "is_blunder_fest": False, "is_nail_biter": True,
            "drama_score": 250,
        }])

    monkeypatch.setattr(data, "get_game_explorer_table", fake_get_game_explorer_table)

    resp = api_client.get("/api/overview/career-highlight")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


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
def test_coaching_plan_status_endpoint_no_cached_narrative(api_client):
    resp = api_client.get("/api/overview/coaching-plan-status")
    assert resp.status_code == 200
    assert resp.json() == {"cached": False}


@pytest.mark.integration
def test_coaching_plan_status_endpoint_with_cached_narrative(api_client, monkeypatch):
    import data

    def fake_get_cached_narrative(conn, subject_type, subject_key):
        assert subject_type == "coaching"
        assert subject_key == "recommendations"
        return ("Some cached coaching text.", "2026-01-01T00:00:00")

    monkeypatch.setattr(data, "get_cached_narrative", fake_get_cached_narrative)

    resp = api_client.get("/api/overview/coaching-plan-status")
    assert resp.status_code == 200
    assert resp.json() == {"cached": True}


@pytest.mark.integration
def test_engine_status_endpoint_not_connected_by_default(api_client):
    resp = api_client.get("/api/overview/engine-status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["connected"] is False
    assert body["version"] is None
    assert isinstance(body["app_version"], str) and body["app_version"] != ""


@pytest.mark.integration
def test_engine_status_endpoint_reports_connected_engine(api_client, monkeypatch):
    import engine_status

    def fake_get_engine_status_summary():
        return {"connected": True, "version": "17.1"}

    monkeypatch.setattr(engine_status, "get_engine_status_summary", fake_get_engine_status_summary)

    resp = api_client.get("/api/overview/engine-status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["connected"] is True
    assert body["version"] == "17.1"


@pytest.mark.integration
def test_win_rate_by_color_endpoint_empty_db(api_client):
    resp = api_client.get("/api/overview/win-rate-by-color")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.integration
def test_win_rate_by_color_endpoint_returns_rows(api_client, monkeypatch):
    import pandas as pd
    import data

    def fake_get_win_rate_by_color(*args, **kwargs):
        return pd.DataFrame([
            {"player_color": "white", "n": 60, "win_pct": 58.0, "draw_pct": 4.0},
            {"player_color": "black", "n": 40, "win_pct": 50.4, "draw_pct": 3.0},
        ])

    monkeypatch.setattr(data, "get_win_rate_by_color", fake_get_win_rate_by_color)

    resp = api_client.get("/api/overview/win-rate-by-color")
    assert resp.status_code == 200
    assert resp.json() == [
        {"player_color": "white", "n": 60, "win_pct": 58.0, "draw_pct": 4.0},
        {"player_color": "black", "n": 40, "win_pct": 50.4, "draw_pct": 3.0},
    ]


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
