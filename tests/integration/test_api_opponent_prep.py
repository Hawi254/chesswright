"""Integration tests for the Opponent Prep page's FastAPI endpoints. See
docs/superpowers/specs/2026-07-16-opponent-prep-page-design.md.
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

import opponent_prep_runner
import job_runner
import joblock


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
class TestOpponentPrepStart:
    def test_start_happy_path(self, api_client, monkeypatch):
        monkeypatch.setattr(opponent_prep_runner, "start", lambda username, n_games: None)
        resp = api_client.post("/api/opponent-prep/start", json={"username": "DrNykterstein", "n_games": 50})
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

    def test_start_returns_409_when_already_running(self, api_client, monkeypatch):
        def _raise(username, n_games):
            raise RuntimeError("An opponent analysis is already running.")
        monkeypatch.setattr(opponent_prep_runner, "start", _raise)
        resp = api_client.post("/api/opponent-prep/start", json={"username": "x", "n_games": 50})
        assert resp.status_code == 409
        assert "already running" in resp.json()["detail"]

    def test_start_returns_409_on_external_lock(self, api_client, monkeypatch):
        def _raise(username, n_games):
            raise joblock.LockHeldError(joblock.LockInfo(pid=123, started_at="now", alive=True))
        monkeypatch.setattr(opponent_prep_runner, "start", _raise)
        resp = api_client.post("/api/opponent-prep/start", json={"username": "x", "n_games": 50})
        assert resp.status_code == 409


@pytest.mark.integration
class TestOpponentPrepStatus:
    def test_idle_shape(self, api_client, monkeypatch):
        monkeypatch.setattr(opponent_prep_runner, "get_state", lambda: {"status": "idle"})
        resp = api_client.get("/api/opponent-prep/status")
        assert resp.status_code == 200
        assert resp.json() == {"status": "idle", "username": None, "step": None, "error": None}

    def test_running_shape(self, api_client, monkeypatch):
        monkeypatch.setattr(
            opponent_prep_runner, "get_state",
            lambda: {"status": "running", "username": "DrNykterstein", "step": "analyzing"})
        resp = api_client.get("/api/opponent-prep/status")
        assert resp.json() == {
            "status": "running", "username": "DrNykterstein", "step": "analyzing", "error": None,
        }


@pytest.mark.integration
class TestOpponentPrepStop:
    def test_stop_calls_runner(self, api_client, monkeypatch):
        called = []
        monkeypatch.setattr(opponent_prep_runner, "stop", lambda: called.append(True))
        resp = api_client.post("/api/opponent-prep/stop")
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
        assert called == [True]


@pytest.mark.integration
class TestOpponentPrepList:
    def test_list_returns_scouted_opponents(self, api_client, migrated_db_path, monkeypatch):
        import data
        monkeypatch.setattr(data, "list_scouted_opponents", lambda path: ["alice", "bob"])
        resp = api_client.get("/api/opponent-prep/list")
        assert resp.status_code == 200
        assert resp.json() == {"opponents": ["alice", "bob"]}


@pytest.mark.integration
class TestOpponentPrepReport:
    def test_404_when_opponent_not_scouted(self, api_client, monkeypatch):
        import data
        monkeypatch.setattr(data, "open_opponent_connections", lambda username: (None, None))
        resp = api_client.get("/api/opponent-prep/report/nobody")
        assert resp.status_code == 404

    def test_happy_path(self, api_client, migrated_db_path, monkeypatch):
        import sqlite3
        import data

        # check_same_thread=False: FastAPI's TestClient runs sync routes in a
        # worker thread, matching get_sqlite_connection()'s real production setting.
        opp_conn = sqlite3.connect(migrated_db_path, check_same_thread=False)  # reuse the migrated schema as a stand-in opponent DB
        opp_conn.execute(
            "INSERT INTO games (id, white, black, player_color, opening_family, "
            "outcome_for_player, analysis_status, utc_date) VALUES "
            "('g1','W','B','white','Italian Game','win','done','2026-01-01')")
        opp_conn.execute(
            "INSERT INTO moves (game_id, ply, move_number, color, san, is_player_move, cpl) "
            "VALUES ('g1', 1, 1, 'w', 'e4', 1, 10)")
        opp_conn.commit()

        import duckdb
        opp_duck = duckdb.connect(":memory:")
        opp_duck.execute(f"ATTACH '{migrated_db_path}' AS db (TYPE SQLITE, READ_ONLY TRUE)")

        monkeypatch.setattr(data, "open_opponent_connections",
                             lambda username: (opp_conn, opp_duck))

        resp = api_client.get("/api/opponent-prep/report/DrNykterstein")
        assert resp.status_code == 200
        body = resp.json()
        assert body["gamesAnalyzed"] == 1
        assert body["colorSplit"] == {"white": 1, "black": 0}
        assert body["dateRange"] == {"from": "2026-01-01", "to": "2026-01-01"}
        assert len(body["repertoire"]) == 0  # below the 3-game HAVING threshold, expected empty
        opp_duck.close()
        opp_conn.close()


@pytest.mark.integration
class TestOpponentPrepNotes:
    def _attach_opponent_db(self, monkeypatch, migrated_db_path):
        import sqlite3
        import duckdb
        import data

        def _open(username):
            # Each route call gets a fresh connection pair, matching real
            # open_opponent_connections() -- the routes close both
            # connections in a finally block after every request, so a
            # test that makes two requests (e.g. generate then get) would
            # hit "Cannot operate on a closed database" on the second call
            # if this returned one shared, already-closed pair instead.
            conn = sqlite3.connect(migrated_db_path, check_same_thread=False)
            duck = duckdb.connect(":memory:")
            duck.execute(f"ATTACH '{migrated_db_path}' AS db (TYPE SQLITE, READ_ONLY TRUE)")
            return conn, duck

        monkeypatch.setattr(data, "open_opponent_connections", _open)
        return _open(None)

    def test_get_returns_null_when_uncached(self, api_client, migrated_db_path, monkeypatch):
        self._attach_opponent_db(monkeypatch, migrated_db_path)
        resp = api_client.get("/api/opponent-prep/DrNykterstein/notes")
        assert resp.status_code == 200
        assert resp.json() == {"narrative": None, "generated_at": None}

    def test_get_404_when_opponent_not_scouted(self, api_client, monkeypatch):
        import data
        monkeypatch.setattr(data, "open_opponent_connections", lambda username: (None, None))
        resp = api_client.get("/api/opponent-prep/nobody/notes")
        assert resp.status_code == 404

    def test_generate_happy_path(self, api_client, migrated_db_path, monkeypatch):
        opp_conn, opp_duck = self._attach_opponent_db(monkeypatch, migrated_db_path)
        import claude_narrative
        monkeypatch.setattr(claude_narrative, "generate_scouting_notes",
                             lambda username, df, n: "Generated scouting notes")

        resp = api_client.post("/api/opponent-prep/DrNykterstein/notes/generate")
        assert resp.status_code == 200
        assert resp.json() == {"narrative": "Generated scouting notes"}

        resp2 = api_client.get("/api/opponent-prep/DrNykterstein/notes")
        assert resp2.json()["narrative"] == "Generated scouting notes"

    def test_generate_returns_503_on_missing_api_key(self, api_client, migrated_db_path, monkeypatch):
        self._attach_opponent_db(monkeypatch, migrated_db_path)
        import claude_narrative

        def _raise(username, df, n):
            raise claude_narrative.MissingApiKeyError("No Anthropic API key configured.")
        monkeypatch.setattr(claude_narrative, "generate_scouting_notes", _raise)

        resp = api_client.post("/api/opponent-prep/DrNykterstein/notes/generate")
        assert resp.status_code == 503
        assert "API key" in resp.json()["detail"]

    def test_generate_returns_502_on_generic_claude_failure(self, api_client, migrated_db_path, monkeypatch):
        self._attach_opponent_db(monkeypatch, migrated_db_path)
        import claude_narrative

        def _raise(username, df, n):
            raise RuntimeError("connection reset")
        monkeypatch.setattr(claude_narrative, "generate_scouting_notes", _raise)

        resp = api_client.post("/api/opponent-prep/DrNykterstein/notes/generate")
        assert resp.status_code == 502


@pytest.mark.integration
class TestTournamentPrepReport:
    def _attach_opponent_db(self, monkeypatch, migrated_db_path):
        import sqlite3
        import duckdb
        import data

        def _open(username):
            # Fresh connection pair per call, check_same_thread=False --
            # see TestOpponentPrepNotes._attach_opponent_db for why (routes
            # close both connections after every request; TestClient runs
            # sync routes off the test's own thread).
            conn = sqlite3.connect(migrated_db_path, check_same_thread=False)
            duck = duckdb.connect(":memory:")
            duck.execute(f"ATTACH '{migrated_db_path}' AS db (TYPE SQLITE, READ_ONLY TRUE)")
            return conn, duck

        monkeypatch.setattr(data, "open_opponent_connections", _open)
        return _open(None)

    def test_generate_returns_403_when_not_licensed(self, api_client, migrated_db_path, monkeypatch):
        self._attach_opponent_db(monkeypatch, migrated_db_path)
        import pro_gate
        monkeypatch.setattr(pro_gate, "is_pro_active", lambda: False)
        resp = api_client.post("/api/opponent-prep/DrNykterstein/tournament-report/generate")
        assert resp.status_code == 403

    def test_generate_returns_501_when_chesswright_pro_not_importable(self, api_client, migrated_db_path, monkeypatch):
        self._attach_opponent_db(monkeypatch, migrated_db_path)
        import pro_gate
        monkeypatch.setattr(pro_gate, "is_pro_active", lambda: True)
        import sys
        monkeypatch.setitem(sys.modules, "chesswright_pro", None)
        resp = api_client.post("/api/opponent-prep/DrNykterstein/tournament-report/generate")
        assert resp.status_code == 501

    def test_generate_returns_404_when_opponent_not_scouted(self, api_client, monkeypatch):
        import data
        import pro_gate
        monkeypatch.setattr(pro_gate, "is_pro_active", lambda: True)
        monkeypatch.setattr(data, "open_opponent_connections", lambda username: (None, None))
        resp = api_client.post("/api/opponent-prep/nobody/tournament-report/generate")
        assert resp.status_code == 404

    def test_generate_happy_path(self, api_client, migrated_db_path, monkeypatch):
        self._attach_opponent_db(monkeypatch, migrated_db_path)
        import pro_gate
        monkeypatch.setattr(pro_gate, "is_pro_active", lambda: True)
        from chesswright_pro import tournament_prep
        monkeypatch.setattr(tournament_prep, "generate_report",
                             lambda username, n, df, main_duck_conn: "<html>Report</html>")

        resp = api_client.post("/api/opponent-prep/DrNykterstein/tournament-report/generate")
        assert resp.status_code == 200
        assert resp.json()["report_html"] == "<html>Report</html>"
        assert resp.json()["generated_at"] is not None

    def test_download_html_happy_path(self, api_client, migrated_db_path, monkeypatch):
        self._attach_opponent_db(monkeypatch, migrated_db_path)
        import pro_gate
        monkeypatch.setattr(pro_gate, "is_pro_active", lambda: True)
        from chesswright_pro import tournament_prep
        monkeypatch.setattr(tournament_prep, "generate_report",
                             lambda username, n, df, main_duck_conn: "<html>Report</html>")
        api_client.post("/api/opponent-prep/DrNykterstein/tournament-report/generate")

        resp = api_client.get("/api/opponent-prep/DrNykterstein/tournament-report/download.html")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/html")
        assert 'filename="chesswright_prep_DrNykterstein.html"' in resp.headers["content-disposition"]
        assert resp.text == "<html>Report</html>"

    def test_download_html_404_when_uncached(self, api_client, migrated_db_path, monkeypatch):
        self._attach_opponent_db(monkeypatch, migrated_db_path)
        resp = api_client.get("/api/opponent-prep/DrNykterstein/tournament-report/download.html")
        assert resp.status_code == 404
