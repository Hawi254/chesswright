"""Integration tests for the Matchups & Opponents endpoints -- see
docs/superpowers/specs/2026-07-14-matchups-opponents-page-design.md.
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


def _insert_game(db_path, game_id, opponent_name="Foe", outcome_for_player="win",
                  rating_diff=0, site="https://lichess.org/" + "x" * 8,
                  year=2026, month=1, num_plies=40, analysis_status="pending",
                  player_color="white"):
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO games (id, white, black, opponent_name, outcome_for_player, "
        "rating_diff, site, year, month, num_plies, analysis_status, player_color) "
        "VALUES (?, 'W', 'B', ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [game_id, opponent_name, outcome_for_player, rating_diff, site,
         year, month, num_plies, analysis_status, player_color])
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
class TestMatchupsRatingForm:
    def test_empty_db_returns_zero_filled_shape(self, api_client):
        resp = api_client.get("/api/matchups/rating-form")
        assert resp.status_code == 200
        body = resp.json()
        assert body["win_rate_by_rating_diff"] == []
        assert body["giant_killing_counts"] == {
            "n_upsets": 0, "n_underdog_games": 0, "n_collapses": 0, "n_favorite_games": 0,
        }
        assert body["collapse_causes"] == {"reason": [], "piece": [], "mate": []}
        assert body["comeback_collapse"]["n_comebacks"] == 0

    def test_color_performance_nan_bucket_serializes_as_null_not_500(self, api_client, migrated_db_path):
        # Only an "even" rating_diff game exists -- get_color_performance_by_rating's
        # pivot.reindex(["underdog", "even", "favorite"]) introduces all-NaN
        # underdog/favorite rows in this case. Regression test for the same
        # allow_nan=False 500 the game_detail endpoint's own _json_safe
        # wrapping already guards against (see openings_table's precedent).
        _insert_game(migrated_db_path, "game_1", rating_diff=0, outcome_for_player="win")
        resp = api_client.get("/api/matchups/rating-form")
        assert resp.status_code == 200
        rows = {r["rating_bucket"]: r for r in resp.json()["color_performance_by_rating"]}
        assert rows["underdog"]["white"] is None
        assert rows["favorite"]["white"] is None

    def test_piece_records_are_reordered_and_named_server_side(self, api_client, migrated_db_path):
        # A collapse (300+ favorite loss) whose last player move before the
        # loss was a blunder that hung a piece (N) via an immediate recapture.
        conn = sqlite3.connect(migrated_db_path)
        conn.execute(
            "INSERT INTO games (id, white, black, outcome_for_player, rating_diff, num_plies) "
            "VALUES ('g1', 'W', 'B', 'loss', 400, 10)")
        conn.execute(
            "INSERT INTO moves (game_id, ply, move_number, color, san, piece, to_square, is_player_move, "
            "classification, cpl) VALUES ('g1', 8, 4, 'w', 'Nf3', 'N', 'f3', 1, 'blunder', 300)")
        conn.execute(
            "INSERT INTO moves (game_id, ply, move_number, color, san, is_capture, to_square, "
            "material_delta, is_player_move) VALUES ('g1', 9, 5, 'b', 'Bxf3', 1, 'f3', 300, 0)")
        conn.commit()
        conn.close()

        resp = api_client.get("/api/matchups/rating-form")
        assert resp.status_code == 200
        piece_rows = resp.json()["collapse_causes"]["piece"]
        assert len(piece_rows) == 1
        assert piece_rows[0]["hung_piece"] == "N"
        assert piece_rows[0]["piece_name"] == "Knight"

    def test_ttl_cache_reset_between_tests(self, api_client, migrated_db_path, monkeypatch):
        import data
        call_count = {"n": 0}
        real = data.get_win_rate_by_rating_diff

        def _counting(*args, **kwargs):
            call_count["n"] += 1
            return real(*args, **kwargs)
        monkeypatch.setattr(data, "get_win_rate_by_rating_diff", _counting)

        api_client.get("/api/matchups/rating-form")
        api_client.get("/api/matchups/rating-form")
        assert call_count["n"] == 1  # second call served from _matchups_static_cache

        import api.main as api_main
        api_main.reset_caches()
        api_client.get("/api/matchups/rating-form")
        assert call_count["n"] == 2


@pytest.mark.integration
class TestMatchupsNemesis:
    def test_empty_db_returns_empty_list(self, api_client):
        resp = api_client.get("/api/matchups/nemesis")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_default_min_games_uses_config_min_sample_size(self, api_client, migrated_db_path):
        # config.yaml's analytics.min_sample_size is 5 -- 4 games against
        # the same opponent must NOT appear with no min_games override.
        for i in range(4):
            _insert_game(migrated_db_path, f"g{i}", opponent_name="Rare", outcome_for_player="win")
        resp = api_client.get("/api/matchups/nemesis")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_explicit_min_games_overrides_the_config_default(self, api_client, migrated_db_path):
        for i in range(4):
            _insert_game(migrated_db_path, f"g{i}", opponent_name="Rare", outcome_for_player="win")
        resp = api_client.get("/api/matchups/nemesis?min_games=3")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["opponent_name"] == "Rare"
        assert body[0]["n"] == 4
        assert body[0]["score_pct"] == 100.0
        assert body[0]["confidence_tier"] in ("low", "medium", "high")


@pytest.mark.integration
class TestOpponentProfile:
    def test_unknown_opponent_returns_zero_games_not_error(self, api_client):
        resp = api_client.get("/api/matchups/opponent-profile?opponent_name=NoOne")
        assert resp.status_code == 200
        body = resp.json()
        assert body["n_games"] == 0
        assert body["openings"] == []

    def test_returns_populated_profile_for_known_opponent(self, api_client, migrated_db_path):
        _insert_game(migrated_db_path, "g1", opponent_name="Rival", outcome_for_player="win")
        resp = api_client.get("/api/matchups/opponent-profile?opponent_name=Rival")
        assert resp.status_code == 200
        assert resp.json()["n_games"] == 1


@pytest.mark.integration
class TestOpponentSwindleRate:
    def test_zero_losses_returns_null_rate_not_zero(self, api_client, migrated_db_path):
        _insert_game(migrated_db_path, "g1", opponent_name="Rival", outcome_for_player="win")
        resp = api_client.get("/api/matchups/opponent-swindle-rate?opponent_name=Rival")
        assert resp.status_code == 200
        assert resp.json() == {"n_losses": 0, "n_missed_swindle": 0, "swindle_rate_pct": None}

    def test_uncached_points_ledger_is_shared_via_ttl_cache(self, api_client, migrated_db_path, monkeypatch):
        import data
        call_count = {"n": 0}
        real = data.get_points_ledger

        def _counting(*args, **kwargs):
            call_count["n"] += 1
            return real(*args, **kwargs)
        monkeypatch.setattr(data, "get_points_ledger", _counting)

        api_client.get("/api/matchups/opponent-swindle-rate?opponent_name=A")
        api_client.get("/api/matchups/opponent-swindle-rate?opponent_name=B")
        assert call_count["n"] == 1  # second call served from _points_ledger_cache


@pytest.mark.integration
class TestGetOpponentNarrative:
    def test_returns_null_when_uncached(self, api_client):
        resp = api_client.get("/api/matchups/opponent-narrative?opponent_name=Rival")
        assert resp.status_code == 200
        assert resp.json() == {"narrative": None, "generated_at": None}

    def test_returns_cached_narrative(self, api_client):
        import data
        from api.db import get_db_connections
        sqlite_conn, _ = get_db_connections()
        data.save_narrative(sqlite_conn, "opponent", "Rival", "## Rivalry", "claude-sonnet-4-6")

        resp = api_client.get("/api/matchups/opponent-narrative?opponent_name=Rival")
        assert resp.status_code == 200
        body = resp.json()
        assert body["narrative"] == "## Rivalry"
        assert body["generated_at"] is not None


@pytest.mark.integration
class TestGenerateOpponentNarrative:
    def test_generate_happy_path(self, api_client, migrated_db_path, monkeypatch):
        for i in range(5):
            _insert_game(migrated_db_path, f"g{i}", opponent_name="Rival", outcome_for_player="win")
        import claude_narrative
        monkeypatch.setattr(claude_narrative, "generate_opponent_commentary",
                             lambda *a, **k: "Generated commentary")

        resp = api_client.post("/api/matchups/opponent-narrative/generate?opponent_name=Rival")
        assert resp.status_code == 200
        assert resp.json() == {"narrative": "Generated commentary"}

        resp2 = api_client.get("/api/matchups/opponent-narrative?opponent_name=Rival")
        assert resp2.json()["narrative"] == "Generated commentary"

    def test_returns_404_for_unknown_opponent(self, api_client, migrated_db_path):
        for i in range(5):
            _insert_game(migrated_db_path, f"g{i}", opponent_name="Rival", outcome_for_player="win")
        resp = api_client.post("/api/matchups/opponent-narrative/generate?opponent_name=NoOne")
        assert resp.status_code == 404

    def test_returns_503_on_missing_api_key(self, api_client, migrated_db_path, monkeypatch):
        for i in range(5):
            _insert_game(migrated_db_path, f"g{i}", opponent_name="Rival", outcome_for_player="win")
        import claude_narrative

        def _raise(*args, **kwargs):
            raise claude_narrative.MissingApiKeyError("No Anthropic API key configured.")
        monkeypatch.setattr(claude_narrative, "generate_opponent_commentary", _raise)

        resp = api_client.post("/api/matchups/opponent-narrative/generate?opponent_name=Rival")
        assert resp.status_code == 503
        assert "API key" in resp.json()["detail"]

    def test_returns_502_on_generic_claude_failure(self, api_client, migrated_db_path, monkeypatch):
        for i in range(5):
            _insert_game(migrated_db_path, f"g{i}", opponent_name="Rival", outcome_for_player="win")
        import claude_narrative

        def _raise(*args, **kwargs):
            raise RuntimeError("connection reset")
        monkeypatch.setattr(claude_narrative, "generate_opponent_commentary", _raise)

        resp = api_client.post("/api/matchups/opponent-narrative/generate?opponent_name=Rival")
        assert resp.status_code == 502
        assert "connection reset" in resp.json()["detail"]
