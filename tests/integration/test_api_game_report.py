"""Integration tests for the Game Report endpoints -- pro-status probe,
cached-report GET, generate POST, and the two file-download GETs. See
docs/superpowers/specs/2026-07-14-game-detail-slice5-game-report-design.md.
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


def _insert_game(db_path, game_id, opponent_name="kingslayer99", utc_date="2026-07-14"):
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO games (id, white, black, opponent_name, utc_date) VALUES (?, 'W', 'B', ?, ?)",
        [game_id, opponent_name, utc_date])
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
class TestProStatus:
    def test_reports_true_when_pro_active(self, api_client, monkeypatch):
        import pro_gate
        monkeypatch.setattr(pro_gate, "is_pro_active", lambda: True)
        resp = api_client.get("/api/pro-status")
        assert resp.status_code == 200
        assert resp.json() == {"active": True}

    def test_reports_false_when_pro_inactive(self, api_client, monkeypatch):
        import pro_gate
        monkeypatch.setattr(pro_gate, "is_pro_active", lambda: False)
        resp = api_client.get("/api/pro-status")
        assert resp.status_code == 200
        assert resp.json() == {"active": False}


@pytest.mark.integration
class TestGetGameReport:
    def test_returns_null_when_uncached(self, api_client):
        resp = api_client.get("/api/games/game_1/report")
        assert resp.status_code == 200
        assert resp.json() == {"report_text": None, "generated_at": None}

    def test_returns_cached_report(self, api_client):
        import data
        from api.db import get_db_connections
        sqlite_conn, _ = get_db_connections()
        data.save_narrative(sqlite_conn, "game_report", "game_1", "## Report", "claude-sonnet-4-6")

        resp = api_client.get("/api/games/game_1/report")
        assert resp.status_code == 200
        body = resp.json()
        assert body["report_text"] == "## Report"
        assert body["generated_at"] is not None


@pytest.mark.integration
class TestGenerateGameReport:
    def test_generate_happy_path(self, api_client, migrated_db_path, monkeypatch):
        _insert_game(migrated_db_path, "game_1")
        import pro_gate
        monkeypatch.setattr(pro_gate, "is_pro_active", lambda: True)
        import data
        from chesswright_pro import game_report

        # generate_report()'s real contract (Task 1) is persist-then-return
        # -- the endpoint re-reads the cache afterward to pick up the
        # server-side generated_at timestamp, so the stub must persist too,
        # not just return text.
        def _fake_generate_report(sqlite_conn, game_id, header, moves):
            data.save_narrative(sqlite_conn, "game_report", game_id,
                                "## Generated report", "claude-sonnet-4-6")
            return "## Generated report"
        monkeypatch.setattr(game_report, "generate_report", _fake_generate_report)

        resp = api_client.post("/api/games/game_1/report/generate")
        assert resp.status_code == 200
        body = resp.json()
        assert body["report_text"] == "## Generated report"
        assert body["generated_at"] is not None

    def test_generate_returns_403_when_not_licensed(self, api_client, monkeypatch):
        import pro_gate
        monkeypatch.setattr(pro_gate, "is_pro_active", lambda: False)

        resp = api_client.post("/api/games/game_1/report/generate")
        assert resp.status_code == 403

    def test_generate_returns_501_when_chesswright_pro_not_importable(self, api_client, monkeypatch):
        import pro_gate
        monkeypatch.setattr(pro_gate, "is_pro_active", lambda: True)
        import sys
        # Standard "simulate an uninstalled package" trick: a None entry in
        # sys.modules makes any subsequent `import chesswright_pro` (and
        # `from chesswright_pro import ...`) raise ImportError immediately,
        # without needing to patch __import__ itself or touch the real
        # editable-installed package on disk. monkeypatch restores the real
        # entry (or removes it) after the test.
        monkeypatch.setitem(sys.modules, "chesswright_pro", None)

        resp = api_client.post("/api/games/game_1/report/generate")
        assert resp.status_code == 501

    def test_generate_returns_404_for_unknown_game(self, api_client, monkeypatch):
        import pro_gate
        monkeypatch.setattr(pro_gate, "is_pro_active", lambda: True)

        resp = api_client.post("/api/games/does-not-exist/report/generate")
        assert resp.status_code == 404

    def test_generate_returns_503_on_missing_api_key(self, api_client, migrated_db_path, monkeypatch):
        _insert_game(migrated_db_path, "game_1")
        import pro_gate
        monkeypatch.setattr(pro_gate, "is_pro_active", lambda: True)
        import claude_narrative
        from chesswright_pro import game_report

        def _raise(*args, **kwargs):
            raise claude_narrative.MissingApiKeyError("No Anthropic API key configured.")
        monkeypatch.setattr(game_report, "generate_report", _raise)

        resp = api_client.post("/api/games/game_1/report/generate")
        assert resp.status_code == 503
        assert "API key" in resp.json()["detail"]

    def test_generate_returns_502_on_generic_claude_failure(self, api_client, migrated_db_path, monkeypatch):
        _insert_game(migrated_db_path, "game_1")
        import pro_gate
        monkeypatch.setattr(pro_gate, "is_pro_active", lambda: True)
        from chesswright_pro import game_report

        def _raise(*args, **kwargs):
            raise RuntimeError("connection reset")
        monkeypatch.setattr(game_report, "generate_report", _raise)

        resp = api_client.post("/api/games/game_1/report/generate")
        assert resp.status_code == 502
        assert "connection reset" in resp.json()["detail"]


@pytest.mark.integration
class TestDownloadGameReportMarkdown:
    def test_happy_path(self, api_client, migrated_db_path):
        import data
        from api.db import get_db_connections
        _insert_game(migrated_db_path, "game_1", opponent_name="kingslayer99", utc_date="2026-07-14")
        sqlite_conn, _ = get_db_connections()
        data.save_narrative(sqlite_conn, "game_report", "game_1", "## Report body", "claude-sonnet-4-6")

        resp = api_client.get("/api/games/game_1/report/download.md")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/markdown")
        assert 'filename="chesswright_report_kingslayer99_2026-07-14.md"' in resp.headers["content-disposition"]
        assert resp.text == "## Report body"

    def test_404_when_uncached(self, api_client, migrated_db_path):
        _insert_game(migrated_db_path, "game_1")
        resp = api_client.get("/api/games/game_1/report/download.md")
        assert resp.status_code == 404

    def test_404_for_unknown_game(self, api_client):
        resp = api_client.get("/api/games/does-not-exist/report/download.md")
        assert resp.status_code == 404

    def test_filename_replaces_spaces_in_opponent_name(self, api_client, migrated_db_path):
        import data
        from api.db import get_db_connections
        _insert_game(migrated_db_path, "game_1", opponent_name="king slayer 99", utc_date="2026-07-14")
        sqlite_conn, _ = get_db_connections()
        data.save_narrative(sqlite_conn, "game_report", "game_1", "## Report", "claude-sonnet-4-6")

        resp = api_client.get("/api/games/game_1/report/download.md")
        assert 'filename="chesswright_report_king_slayer_99_2026-07-14.md"' in resp.headers["content-disposition"]


@pytest.mark.integration
class TestDownloadGameReportHtml:
    def test_happy_path(self, api_client, migrated_db_path):
        import data
        from api.db import get_db_connections
        _insert_game(migrated_db_path, "game_1", opponent_name="kingslayer99", utc_date="2026-07-14")
        sqlite_conn, _ = get_db_connections()
        data.save_narrative(sqlite_conn, "game_report", "game_1", "## Report body", "claude-sonnet-4-6")

        resp = api_client.get("/api/games/game_1/report/download.html")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/html")
        assert 'filename="chesswright_report_kingslayer99_2026-07-14.html"' in resp.headers["content-disposition"]
        assert "Report body" in resp.text
        assert "kingslayer99" in resp.text

    def test_404_when_uncached(self, api_client, migrated_db_path):
        _insert_game(migrated_db_path, "game_1")
        resp = api_client.get("/api/games/game_1/report/download.html")
        assert resp.status_code == 404

    def test_404_for_unknown_game(self, api_client):
        resp = api_client.get("/api/games/does-not-exist/report/download.html")
        assert resp.status_code == 404
