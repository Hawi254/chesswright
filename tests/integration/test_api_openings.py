"""Integration tests for the Openings & Repertoire endpoints -- see
docs/superpowers/specs/2026-07-14-opening-repertoire-page-design.md.
"""
import pathlib
import shutil
import sqlite3
import sys

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
DASHBOARD_DIR = REPO_ROOT / "dashboard"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(DASHBOARD_DIR))


def _insert_game(db_path, game_id, opening_family="Sicilian Defense",
                  player_color="white", outcome_for_player="win"):
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO games (id, white, black, opening_family, player_color, outcome_for_player) "
        "VALUES (?, 'W', 'B', ?, ?, ?)",
        [game_id, opening_family, player_color, outcome_for_player])
    conn.commit()
    conn.close()


def _insert_move(db_path, game_id, ply, move_number, color="w", san="Nf3",
                  is_player_move=1, cpl=None, classification=None):
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO moves (game_id, ply, move_number, color, san, is_player_move, cpl, classification) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [game_id, ply, move_number, color, san, is_player_move, cpl, classification])
    conn.commit()
    conn.close()


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
class TestOpeningsTable:
    def test_empty_db_returns_empty_list(self, api_client):
        resp = api_client.get("/api/openings/table")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_populated_rows(self, api_client, migrated_db_path):
        _insert_game(migrated_db_path, "game_1")
        resp = api_client.get("/api/openings/table")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["opening_family"] == "Sicilian Defense"
        assert body[0]["player_color"] == "white"
        assert body[0]["n"] == 1
        assert body[0]["acpl"] is None  # no analyzed moves yet -- NaN, must serialize as null

    def test_ttl_cache_reset_between_tests(self, api_client, migrated_db_path, monkeypatch):
        import data
        call_count = {"n": 0}
        real_get_openings_table = data.get_openings_table

        def _counting(*args, **kwargs):
            call_count["n"] += 1
            return real_get_openings_table(*args, **kwargs)
        monkeypatch.setattr(data, "get_openings_table", _counting)

        resp1 = api_client.get("/api/openings/table")
        resp2 = api_client.get("/api/openings/table")
        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert call_count["n"] == 1  # second call served from _openings_table_cache

        import api.main as api_main
        api_main.reset_caches()
        api_client.get("/api/openings/table")
        assert call_count["n"] == 2  # cache cleared -- recomputed


@pytest.mark.integration
class TestGetOpeningNarrative:
    def test_returns_null_when_uncached(self, api_client):
        resp = api_client.get("/api/openings/Sicilian%20Defense/white/narrative")
        assert resp.status_code == 200
        assert resp.json() == {"narrative": None, "generated_at": None}

    def test_returns_cached_narrative(self, api_client):
        import data
        from api.db import get_db_connections
        sqlite_conn, _ = get_db_connections()
        data.save_narrative(sqlite_conn, "opening", "Sicilian Defense|white", "## Commentary", "claude-sonnet-4-6")

        resp = api_client.get("/api/openings/Sicilian%20Defense/white/narrative")
        assert resp.status_code == 200
        body = resp.json()
        assert body["narrative"] == "## Commentary"
        assert body["generated_at"] is not None


@pytest.mark.integration
class TestGenerateOpeningNarrative:
    def test_generate_happy_path(self, api_client, migrated_db_path, monkeypatch):
        _insert_game(migrated_db_path, "game_1")
        import claude_narrative
        monkeypatch.setattr(claude_narrative, "generate_opening_commentary",
                             lambda *a, **k: "Generated commentary")

        resp = api_client.post("/api/openings/Sicilian%20Defense/white/narrative/generate")
        assert resp.status_code == 200
        assert resp.json() == {"narrative": "Generated commentary"}

        # persisted -- a subsequent GET returns it
        resp2 = api_client.get("/api/openings/Sicilian%20Defense/white/narrative")
        assert resp2.json()["narrative"] == "Generated commentary"

    def test_returns_404_for_unknown_opening(self, api_client, migrated_db_path):
        _insert_game(migrated_db_path, "game_1")
        resp = api_client.post("/api/openings/Made%20Up%20Opening/white/narrative/generate")
        assert resp.status_code == 404

    def test_returns_503_on_missing_api_key(self, api_client, migrated_db_path, monkeypatch):
        _insert_game(migrated_db_path, "game_1")
        import claude_narrative

        def _raise(*args, **kwargs):
            raise claude_narrative.MissingApiKeyError("No Anthropic API key configured.")
        monkeypatch.setattr(claude_narrative, "generate_opening_commentary", _raise)

        resp = api_client.post("/api/openings/Sicilian%20Defense/white/narrative/generate")
        assert resp.status_code == 503
        assert "API key" in resp.json()["detail"]

    def test_returns_502_on_generic_claude_failure(self, api_client, migrated_db_path, monkeypatch):
        _insert_game(migrated_db_path, "game_1")
        import claude_narrative

        def _raise(*args, **kwargs):
            raise RuntimeError("connection reset")
        monkeypatch.setattr(claude_narrative, "generate_opening_commentary", _raise)

        resp = api_client.post("/api/openings/Sicilian%20Defense/white/narrative/generate")
        assert resp.status_code == 502
        assert "connection reset" in resp.json()["detail"]


@pytest.mark.integration
class TestRepeatedPositions:
    def test_empty_db_returns_empty_list(self, api_client, monkeypatch):
        import analytics
        monkeypatch.setattr(analytics, "ensure_repeated_positions_cache", lambda *a, **k: None)
        resp = api_client.get("/api/openings/repeated-positions")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_populated_rows(self, api_client, migrated_db_path, monkeypatch):
        import analytics
        monkeypatch.setattr(analytics, "ensure_repeated_positions_cache", lambda *a, **k: None)
        conn = sqlite3.connect(migrated_db_path)
        conn.execute(
            "INSERT INTO repeated_positions_cache (ply, zobrist_hash, n_games, win_pct, draw_pct, "
            "loss_pct, common_opening) VALUES (4, 12345, 8, 50.0, 25.0, 25.0, 'Sicilian Defense')")
        conn.commit()
        conn.close()

        resp = api_client.get("/api/openings/repeated-positions?top_n=10")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["n_games"] == 8
        assert body[0]["common_opening"] == "Sicilian Defense"

    def test_zobrist_hash_serializes_as_a_string(self, api_client, migrated_db_path, monkeypatch):
        # zobrist_hash is a 64-bit signed int -- routinely exceeds JS's
        # Number.MAX_SAFE_INTEGER (found live: -5470636736659934560
        # silently became -5470636736659934000 as a JSON number, and every
        # subsequent /api/openings/position-fen lookup 404'd). Must
        # round-trip as a string.
        import analytics
        monkeypatch.setattr(analytics, "ensure_repeated_positions_cache", lambda *a, **k: None)
        big_hash = -5470636736659934560
        conn = sqlite3.connect(migrated_db_path)
        conn.execute(
            "INSERT INTO repeated_positions_cache (ply, zobrist_hash, n_games, win_pct, draw_pct, "
            "loss_pct, common_opening) VALUES (5, ?, 8, 50.0, 25.0, 25.0, 'Sicilian Defense')",
            [big_hash])
        conn.commit()
        conn.close()

        resp = api_client.get("/api/openings/repeated-positions?top_n=10")
        assert resp.status_code == 200
        body = resp.json()
        assert body[0]["zobrist_hash"] == str(big_hash)


@pytest.mark.integration
class TestPositionFen:
    def test_404_for_unknown_position(self, api_client):
        resp = api_client.get("/api/openings/position-fen?ply=4&zobrist_hash=999")
        assert resp.status_code == 404

    def test_returns_fen_for_known_position(self, api_client, migrated_db_path):
        _insert_game(migrated_db_path, "game_1")
        conn = sqlite3.connect(migrated_db_path)
        conn.execute(
            "INSERT INTO moves (game_id, ply, move_number, color, san, fen_before, zobrist_hash) "
            "VALUES ('game_1', 1, 1, 'w', 'e4', 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1', 555)")
        conn.commit()
        conn.close()

        resp = api_client.get("/api/openings/position-fen?ply=1&zobrist_hash=555")
        assert resp.status_code == 200
        assert resp.json()["fen"].startswith("rnbqkbnr/pppppppp/8/8/4P3")

    def test_round_trips_a_hash_beyond_js_safe_integer_range(self, api_client, migrated_db_path):
        # Regression test for the same live-found bug as
        # TestRepeatedPositions.test_zobrist_hash_serializes_as_a_string --
        # the query param must accept the full string precision and match
        # the exact stored 64-bit int, not a float-rounded approximation.
        _insert_game(migrated_db_path, "game_1")
        big_hash = -5470636736659934560
        conn = sqlite3.connect(migrated_db_path)
        conn.execute(
            "INSERT INTO moves (game_id, ply, move_number, color, san, fen_before, zobrist_hash) "
            "VALUES ('game_1', 1, 1, 'w', 'e4', "
            "'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1', ?)",
            [big_hash])
        conn.commit()
        conn.close()

        resp = api_client.get(f"/api/openings/position-fen?ply=1&zobrist_hash={big_hash}")
        assert resp.status_code == 200
        assert resp.json()["fen"].startswith("rnbqkbnr/pppppppp/8/8/4P3")


@pytest.mark.integration
class TestRepertoireHoles:
    def test_empty_db_returns_empty_list(self, api_client, monkeypatch):
        import analytics
        monkeypatch.setattr(analytics, "ensure_repertoire_holes_cache", lambda *a, **k: None)
        resp = api_client.get("/api/openings/repertoire-holes")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_populated_rows_with_nan_avg_cpl_as_null(self, api_client, migrated_db_path, monkeypatch):
        import analytics
        monkeypatch.setattr(analytics, "ensure_repertoire_holes_cache", lambda *a, **k: None)
        conn = sqlite3.connect(migrated_db_path)
        conn.execute(
            "INSERT INTO repertoire_holes_cache (fen_before, n_games, n_distinct_moves, avg_cpl, "
            "approx_move_number, hole_score, most_played_san, opening) VALUES "
            "('fen1', 6, 3, NULL, 8, NULL, 'Nf3', 'Sicilian Defense')")
        conn.commit()
        conn.close()

        resp = api_client.get("/api/openings/repertoire-holes?min_appearances=3&top_n=10")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["avg_cpl"] is None
        assert body[0]["hole_score"] is None
        assert body[0]["most_played_san"] == "Nf3"


@pytest.mark.integration
class TestPlyAccuracy:
    def test_empty_db_returns_empty_list(self, api_client):
        resp = api_client.get(
            "/api/openings/ply-accuracy?opening_family=Sicilian%20Defense&player_color=white")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_populated_rows(self, api_client, migrated_db_path):
        _insert_game(migrated_db_path, "game_1")
        _insert_game(migrated_db_path, "game_2")
        _insert_game(migrated_db_path, "game_3")
        for gid in ("game_1", "game_2", "game_3"):
            _insert_move(migrated_db_path, gid, ply=1, move_number=1, cpl=20, classification="good")

        resp = api_client.get(
            "/api/openings/ply-accuracy?opening_family=Sicilian%20Defense&player_color=white&min_appearances=3")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["move_number"] == 1
        assert body[0]["n_games"] == 3
        assert body[0]["avg_cpl"] == 20.0
