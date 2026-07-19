"""Integration tests for POST /api/analyse-position. See
docs/superpowers/specs/2026-07-13-game-detail-completion-design.md, Slice 1.
"""
import dataclasses
import json
import pathlib
import shutil
import sys

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
DASHBOARD_DIR = REPO_ROOT / "dashboard"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(DASHBOARD_DIR))

START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


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
    return TestClient(api_main.app)


@dataclasses.dataclass
class _FakeLiveResult:
    eval_cp: int | None
    eval_mate: int | None
    best_move_san: str | None
    pv_json: str
    depth: int
    engine_version: str = "fake-engine"


@pytest.mark.integration
def test_analyse_position_cache_hit_skips_cloud_and_engine(api_client, monkeypatch):
    import data
    import engine_status
    import lichess_cloud_eval

    monkeypatch.setattr(data, "get_position_analysis", lambda conn, fen: {
        "eval_cp": 35, "eval_mate": None, "best_move_san": "e4",
        "pv_json": json.dumps(["e4", "e5"]), "best_move_from": "e2", "best_move_to": "e4",
        "depth": 22, "source": "stored",
    })

    def _fail(*a, **k):
        raise AssertionError("should not be called on a cache hit")

    monkeypatch.setattr(lichess_cloud_eval, "fetch_cloud_eval", _fail)
    monkeypatch.setattr(engine_status, "get_engine_service", _fail)

    resp = api_client.post("/api/analyse-position", json={"fen": START_FEN})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["result"] == {
        "eval_cp": 35, "eval_mate": None, "best_move_san": "e4",
        "best_move_from": "e2", "best_move_to": "e4",
        "pv": ["e4", "e5"], "depth": 22, "source": "stored",
    }


@pytest.mark.integration
def test_analyse_position_cloud_eval_hit(api_client, monkeypatch):
    import data
    import lichess_cloud_eval

    monkeypatch.setattr(data, "get_position_analysis", lambda conn, fen: None)
    stored = {}
    monkeypatch.setattr(data, "store_position_analysis",
                         lambda conn, fen, result: stored.update(fen=fen, result=result))

    cloud_result = _FakeLiveResult(
        eval_cp=50, eval_mate=None, best_move_san="e4",
        pv_json=json.dumps(["e4"]), depth=30, engine_version="Lichess cloud",
    )
    monkeypatch.setattr(lichess_cloud_eval, "fetch_cloud_eval", lambda fen, **kw: cloud_result)

    resp = api_client.post("/api/analyse-position", json={"fen": START_FEN})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["result"]["source"] == "lichess_cloud"
    assert body["result"]["best_move_san"] == "e4"
    assert body["result"]["best_move_from"] == "e2"
    assert body["result"]["best_move_to"] == "e4"
    assert body["result"]["pv"] == ["e4"]
    assert stored["result"] is cloud_result


@pytest.mark.integration
def test_analyse_position_local_engine_hit(api_client, monkeypatch):
    import data
    import engine_status
    import lichess_cloud_eval
    import joblock

    monkeypatch.setattr(data, "get_position_analysis", lambda conn, fen: None)
    monkeypatch.setattr(lichess_cloud_eval, "fetch_cloud_eval", lambda fen, **kw: None)
    monkeypatch.setattr(joblock, "status", lambda: None)
    stored = {}
    monkeypatch.setattr(data, "store_position_analysis",
                         lambda conn, fen, result: stored.update(fen=fen, result=result))

    live_result = _FakeLiveResult(
        eval_cp=40, eval_mate=None, best_move_san="e4",
        pv_json=json.dumps(["e4", "e5"]), depth=20, engine_version="Stockfish 16",
    )

    class _FakeEngine:
        def analyse(self, fen):
            return live_result

    monkeypatch.setattr(engine_status, "get_engine_service", lambda: _FakeEngine())

    resp = api_client.post("/api/analyse-position", json={"fen": START_FEN})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["result"]["source"] == "live"
    assert body["result"]["depth"] == 20
    assert stored["result"] is live_result


@pytest.mark.integration
def test_analyse_position_no_engine(api_client, monkeypatch):
    import data
    import engine_status
    import lichess_cloud_eval
    import joblock

    monkeypatch.setattr(data, "get_position_analysis", lambda conn, fen: None)
    monkeypatch.setattr(lichess_cloud_eval, "fetch_cloud_eval", lambda fen, **kw: None)
    monkeypatch.setattr(joblock, "status", lambda: None)
    monkeypatch.setattr(engine_status, "get_engine_service", lambda: None)

    resp = api_client.post("/api/analyse-position", json={"fen": START_FEN})
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"status": "no_engine", "result": None}


@pytest.mark.integration
def test_analyse_position_batch_running_never_starts_engine(api_client, monkeypatch):
    import data
    import engine_status
    import lichess_cloud_eval
    import joblock

    monkeypatch.setattr(data, "get_position_analysis", lambda conn, fen: None)
    monkeypatch.setattr(lichess_cloud_eval, "fetch_cloud_eval", lambda fen, **kw: None)

    class _LockInfo:
        alive = True

    monkeypatch.setattr(joblock, "status", lambda: _LockInfo())

    def _fail(*a, **k):
        raise AssertionError("must not start the engine while batch analysis is running")

    monkeypatch.setattr(engine_status, "get_engine_service", _fail)

    resp = api_client.post("/api/analyse-position", json={"fen": START_FEN})
    assert resp.status_code == 200
    assert resp.json() == {"status": "batch_running", "result": None}


@pytest.mark.integration
def test_analyse_position_engine_analysis_fails(api_client, monkeypatch):
    import data
    import engine_status
    import lichess_cloud_eval
    import joblock

    monkeypatch.setattr(data, "get_position_analysis", lambda conn, fen: None)
    monkeypatch.setattr(lichess_cloud_eval, "fetch_cloud_eval", lambda fen, **kw: None)
    monkeypatch.setattr(joblock, "status", lambda: None)

    class _FakeEngine:
        def analyse(self, fen):
            return None

    monkeypatch.setattr(engine_status, "get_engine_service", lambda: _FakeEngine())

    resp = api_client.post("/api/analyse-position", json={"fen": START_FEN})
    assert resp.status_code == 200
    assert resp.json() == {"status": "analysis_failed", "result": None}


@pytest.mark.integration
def test_analyse_position_requires_fen(api_client):
    resp = api_client.post("/api/analyse-position", json={})
    assert resp.status_code == 422


@pytest.mark.integration
def test_analyse_position_cors_allows_post(api_client):
    resp = api_client.options(
        "/api/analyse-position",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert resp.status_code == 200
    assert "POST" in resp.headers.get("access-control-allow-methods", "")
