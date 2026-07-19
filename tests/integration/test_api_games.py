"""Integration tests for the Game Explorer + Game Detail endpoints. See
docs/superpowers/specs/2026-07-13-game-explorer-detail-design.md.
"""
import pathlib
import shutil
import sys

import pandas as pd
import pytest
from fastapi.testclient import TestClient

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
    return TestClient(api_main.app)


def _explorer_row(**overrides):
    row = {
        "game_id": "abc123", "utc_date": "2026-01-01", "opponent_name": "Lichess Foe",
        "opponent_rating": 1500, "player_color": "white", "outcome_for_player": "win",
        "time_control_category": "blitz", "opening_family": "Sicilian Defense",
        "rating_diff": 20, "site": "https://lichess.org/abc123", "analysis_status": "done",
        "is_comeback": True, "is_giant_killing": False, "is_brilliant_find": False,
        "is_blunder_fest": False, "is_nail_biter": False, "badge_count": 1, "drama_score": 105,
    }
    row.update(overrides)
    return row


@pytest.mark.integration
def test_games_explorer_endpoint_empty_db(api_client):
    resp = api_client.get("/api/games/explorer")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.integration
def test_games_explorer_endpoint_lichess_url_and_platform(api_client, monkeypatch):
    import chess_display
    import data

    def fake_get_game_explorer_table(*args, **kwargs):
        return pd.DataFrame([
            _explorer_row(),
            _explorer_row(game_id="def456", opponent_name="Chess.com Foe",
                          site=chess_display.CHESSCOM_SITE_HEADER, is_comeback=False,
                          badge_count=0, drama_score=0),
        ])

    monkeypatch.setattr(data, "get_game_explorer_table", fake_get_game_explorer_table)

    resp = api_client.get("/api/games/explorer")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2

    lichess_row = next(r for r in body if r["game_id"] == "abc123")
    assert lichess_row["lichess_url"] == "https://lichess.org/abc123"
    assert lichess_row["platform"] == "Lichess"

    chesscom_row = next(r for r in body if r["game_id"] == "def456")
    assert chesscom_row["lichess_url"] == ""
    assert chesscom_row["platform"] == "Chess.com"


@pytest.mark.integration
def test_games_explorer_endpoint_ttl_cache(api_client, monkeypatch):
    import data

    call_count = {"n": 0}

    def fake_get_game_explorer_table(*args, **kwargs):
        call_count["n"] += 1
        return pd.DataFrame([_explorer_row()])

    monkeypatch.setattr(data, "get_game_explorer_table", fake_get_game_explorer_table)

    resp1 = api_client.get("/api/games/explorer")
    resp2 = api_client.get("/api/games/explorer")
    assert resp1.status_code == 200 == resp2.status_code
    assert resp1.json() == resp2.json()
    assert call_count["n"] == 1


@pytest.mark.integration
def test_game_detail_endpoint_not_found(api_client, monkeypatch):
    import data

    def fake_get_game_detail(*args, **kwargs):
        raise IndexError()

    monkeypatch.setattr(data, "get_game_detail", fake_get_game_detail)

    resp = api_client.get("/api/games/does-not-exist")
    assert resp.status_code == 404


@pytest.mark.integration
def test_game_detail_endpoint_returns_header_moves_and_win_prob(api_client, monkeypatch):
    import data

    header = pd.Series({
        "game_id": "abc123", "utc_date": "2026-01-01", "opponent_name": "TestOpponent",
        "opponent_rating": 1500, "player_rating": 1520, "player_color": "white",
        "outcome_for_player": "win", "time_control_category": "blitz",
        "opening_family": "King's Pawn", "rating_diff": 20, "game_end_type": "checkmate",
        "analysis_status": "done", "last_analyzed_ply": 2, "site": "https://lichess.org/abc123",
    })
    moves = pd.DataFrame([
        {"ply": 1, "san": "e4", "is_player_move": 1, "classification": "good", "cpl": 0,
         "sharpness": 0.1, "is_brilliant_candidate": False, "is_puzzle_trigger": False,
         "fen_before": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
         "win_prob_before": 0.5, "win_prob_after": 0.55, "motif": None},
        {"ply": 2, "san": "e5", "is_player_move": 0, "classification": "good", "cpl": 0,
         "sharpness": 0.1, "is_brilliant_candidate": False, "is_puzzle_trigger": False,
         "fen_before": "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1",
         "win_prob_before": 0.45, "win_prob_after": 0.60, "motif": None},
    ])

    def fake_get_game_detail(*args, **kwargs):
        return header, moves

    monkeypatch.setattr(data, "get_game_detail", fake_get_game_detail)

    resp = api_client.get("/api/games/abc123")
    assert resp.status_code == 200
    body = resp.json()

    assert body["header"]["opponent_name"] == "TestOpponent"
    # No matching row in the (empty, unmocked) explorer table for this DB
    # -- badge lookup degrades to all-False/empty-url rather than crashing.
    assert body["header"]["is_comeback"] is False
    assert body["header"]["lichess_url"] == ""

    assert body["moves"][0]["fen_after"] == \
        "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"
    # No pawn can actually capture en passant here, so python-chess
    # correctly omits the target square (`-`, not `e6`) per current FEN
    # semantics -- found live; the plan's hardcoded fixture had `e6`.
    assert body["moves"][1]["fen_after"] == \
        "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2"

    assert body["win_prob"] == [
        {"ply": 1, "player_win_prob": 0.55},
        {"ply": 2, "player_win_prob": 0.4},
    ]


@pytest.mark.integration
def test_game_detail_endpoint_sanitizes_nan_to_null(api_client, monkeypatch):
    # Found live against the real dev chess.db: unanalyzed moves have NaN
    # in classification/cpl/win_prob_before/win_prob_after/motif (pandas'
    # missing-value marker), and starlette's default JSONResponse sets
    # allow_nan=False -- json.dumps raises ValueError instead of silently
    # emitting invalid JSON, so this crashed with a 500 for any real game
    # with an unanalyzed tail, not just an edge case.
    import data

    header = pd.Series({
        "game_id": "abc123", "utc_date": "2026-01-01", "opponent_name": "TestOpponent",
        "opponent_rating": 1500, "player_rating": 1520, "player_color": "white",
        "outcome_for_player": "win", "time_control_category": "blitz",
        "opening_family": "King's Pawn", "rating_diff": 20, "game_end_type": "checkmate",
        "analysis_status": "partial", "last_analyzed_ply": 1, "site": "https://lichess.org/abc123",
    })
    moves = pd.DataFrame([
        {"ply": 1, "san": "e4", "is_player_move": 1, "classification": "good", "cpl": 0.0,
         "sharpness": 0.1, "is_brilliant_candidate": False, "is_puzzle_trigger": False,
         "fen_before": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
         "win_prob_before": 0.5, "win_prob_after": 0.55, "motif": None},
        {"ply": 2, "san": "e5", "is_player_move": 0, "classification": None, "cpl": float("nan"),
         "sharpness": float("nan"), "is_brilliant_candidate": False, "is_puzzle_trigger": False,
         "fen_before": "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1",
         "win_prob_before": float("nan"), "win_prob_after": float("nan"), "motif": None},
    ])

    def fake_get_game_detail(*args, **kwargs):
        return header, moves

    monkeypatch.setattr(data, "get_game_detail", fake_get_game_detail)

    resp = api_client.get("/api/games/abc123")
    assert resp.status_code == 200
    body = resp.json()
    assert body["moves"][1]["classification"] is None
    assert body["moves"][1]["cpl"] is None
    assert body["moves"][1]["win_prob_before"] is None
    assert body["moves"][1]["win_prob_after"] is None
