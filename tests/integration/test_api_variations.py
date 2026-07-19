"""Integration tests for the variation CRUD endpoints. See
docs/superpowers/specs/2026-07-13-game-detail-slice2-variation-mode-design.md.
"""
import pathlib
import shutil
import sys

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
DASHBOARD_DIR = REPO_ROOT / "dashboard"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(DASHBOARD_DIR))

BRANCH_FEN = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"


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


@pytest.mark.integration
def test_create_variation_persists_and_returns_id(api_client):
    import data
    from api.db import get_db_connections

    resp = api_client.post(
        "/api/games/test_game_1/variations",
        json={"branch_ply": 2, "branch_fen": BRANCH_FEN, "moves": ["g8f6"]},
    )
    assert resp.status_code == 200
    variation_id = resp.json()["id"]
    assert variation_id

    sqlite_conn, _ = get_db_connections()
    saved = data.list_variations(sqlite_conn, "test_game_1")
    assert len(saved) == 1
    assert saved[0].id == variation_id
    assert saved[0].branch_ply == 2
    assert saved[0].branch_fen == BRANCH_FEN
    assert saved[0].moves == ["g8f6"]


@pytest.mark.integration
def test_update_variation_moves_persists_new_list(api_client):
    import data
    from api.db import get_db_connections

    created = api_client.post(
        "/api/games/test_game_1/variations",
        json={"branch_ply": 2, "branch_fen": BRANCH_FEN, "moves": ["g8f6"]},
    ).json()
    variation_id = created["id"]

    resp = api_client.put(
        f"/api/variations/{variation_id}",
        json={"moves": ["g8f6", "b1c3"]},
    )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}

    sqlite_conn, _ = get_db_connections()
    saved = data.list_variations(sqlite_conn, "test_game_1")
    assert saved[0].moves == ["g8f6", "b1c3"]


@pytest.mark.integration
def test_delete_variation_removes_row(api_client):
    import data
    from api.db import get_db_connections

    created = api_client.post(
        "/api/games/test_game_1/variations",
        json={"branch_ply": 2, "branch_fen": BRANCH_FEN, "moves": ["g8f6"]},
    ).json()
    variation_id = created["id"]

    resp = api_client.delete(f"/api/variations/{variation_id}")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}

    sqlite_conn, _ = get_db_connections()
    assert data.list_variations(sqlite_conn, "test_game_1") == []


@pytest.mark.integration
def test_update_and_delete_are_silent_no_ops_for_unknown_id(api_client):
    # Matches data.py's own semantics -- these ids are never user-navigable
    # via URL, only ever produced by this session's own POST response, so
    # no 404 handling is added (see the design spec's Data flow section).
    resp = api_client.put("/api/variations/does-not-exist", json={"moves": []})
    assert resp.status_code == 200
    resp = api_client.delete("/api/variations/does-not-exist")
    assert resp.status_code == 200


@pytest.mark.integration
def test_create_variation_requires_fields(api_client):
    resp = api_client.post("/api/games/test_game_1/variations", json={})
    assert resp.status_code == 422


@pytest.mark.integration
def test_list_variations_endpoint_empty(api_client):
    resp = api_client.get("/api/games/test_game_1/variations")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.integration
def test_list_variations_endpoint_returns_newest_first(api_client):
    first = api_client.post(
        "/api/games/test_game_1/variations",
        json={"branch_ply": 2, "branch_fen": BRANCH_FEN, "moves": ["g8f6"]},
    ).json()["id"]
    second = api_client.post(
        "/api/games/test_game_1/variations",
        json={"branch_ply": 4, "branch_fen": BRANCH_FEN, "moves": ["b8c6"]},
    ).json()["id"]

    resp = api_client.get("/api/games/test_game_1/variations")
    assert resp.status_code == 200
    body = resp.json()
    assert [v["id"] for v in body] == [second, first]
    assert body[0]["branch_ply"] == 4
    assert body[0]["moves"] == ["b8c6"]
    assert body[0]["title"] is None
    assert "created_at" in body[0]
    assert "updated_at" in body[0]


@pytest.mark.integration
def test_list_variations_endpoint_scoped_to_game(api_client):
    api_client.post(
        "/api/games/test_game_1/variations",
        json={"branch_ply": 2, "branch_fen": BRANCH_FEN, "moves": ["g8f6"]},
    )
    resp = api_client.get("/api/games/other_game/variations")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.integration
def test_variation_pgn_endpoint_happy_path(api_client):
    created = api_client.post(
        "/api/games/test_game_1/variations",
        json={"branch_ply": 2, "branch_fen": BRANCH_FEN, "moves": ["g8f6"]},
    ).json()
    variation_id = created["id"]

    resp = api_client.get(f"/api/variations/{variation_id}/pgn")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/x-chess-pgn")
    assert f'filename="var_{variation_id[:8]}.pgn"' in resp.headers["content-disposition"]
    assert "Nf6" in resp.text
    assert '[Event "Chesswright variation"]' in resp.text


@pytest.mark.integration
def test_variation_pgn_endpoint_404_on_unknown_id(api_client):
    resp = api_client.get("/api/variations/does-not-exist/pgn")
    assert resp.status_code == 404


@pytest.mark.integration
def test_variation_pgn_endpoint_filename_replaces_spaces_in_title(api_client, monkeypatch):
    import data
    from api.db import get_db_connections

    created = api_client.post(
        "/api/games/test_game_1/variations",
        json={"branch_ply": 2, "branch_fen": BRANCH_FEN, "moves": ["g8f6"]},
    ).json()
    variation_id = created["id"]
    sqlite_conn, _ = get_db_connections()
    sqlite_conn.execute("UPDATE variations SET title = ? WHERE id = ?",
                        ["My Sicilian Line", variation_id])
    sqlite_conn.commit()

    resp = api_client.get(f"/api/variations/{variation_id}/pgn")
    assert resp.status_code == 200
    assert 'filename="My_Sicilian_Line.pgn"' in resp.headers["content-disposition"]


@pytest.mark.integration
def test_cors_allows_put_and_delete(api_client):
    resp = api_client.options(
        "/api/variations/some-id",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "PUT",
        },
    )
    assert resp.status_code == 200
    allowed = resp.headers.get("access-control-allow-methods", "")
    assert "PUT" in allowed
    assert "DELETE" in allowed
