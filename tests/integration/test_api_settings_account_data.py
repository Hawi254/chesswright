import pathlib

import pytest

import config as _config
import db_import
import sync_chesscom


@pytest.mark.integration
class TestDbImport:
    def test_start_import_failure_returns_400(self, api_client, monkeypatch):
        def _raise(src, dest_dir):
            raise db_import.DatabaseImportError("not a valid SQLite database")

        monkeypatch.setattr(db_import, "import_database", _raise)
        resp = api_client.post("/api/settings/db-import", json={"path": "/tmp/not-a-db.db"})
        assert resp.status_code == 400
        assert "not a valid SQLite database" in resp.json()["detail"]

    def test_start_import_success_returns_pending_id_and_suggestion(self, api_client, monkeypatch, tmp_path):
        imported = tmp_path / "imported_x.db"
        imported.touch()
        monkeypatch.setattr(db_import, "import_database", lambda src, dest_dir: imported)
        monkeypatch.setattr(db_import, "suggest_player_name", lambda path: "some_player")
        resp = api_client.post("/api/settings/db-import", json={"path": "/tmp/source.db"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["suggestedUsername"] == "some_player"
        assert body["pendingId"]

    def test_confirm_unknown_pending_id_returns_404(self, api_client):
        resp = api_client.post("/api/settings/db-import/confirm", json={"pending_id": "bogus", "username": "x"})
        assert resp.status_code == 404

    def test_confirm_switches_database_and_player(self, api_client, monkeypatch, tmp_path):
        imported = tmp_path / "imported_x.db"
        imported.touch()
        monkeypatch.setattr(db_import, "import_database", lambda src, dest_dir: imported)
        monkeypatch.setattr(db_import, "suggest_player_name", lambda path: "")
        start = api_client.post("/api/settings/db-import", json={"path": "/tmp/source.db"})
        pending_id = start.json()["pendingId"]

        resp = api_client.post(
            "/api/settings/db-import/confirm",
            json={"pending_id": pending_id, "username": "new_player"},
        )
        assert resp.status_code == 200
        cfg = _config.load_config(path=str(_config.DEFAULT_CONFIG_PATH))
        assert cfg["player"]["name"] == "new_player"
        assert cfg["database"]["path"] == str(imported)

    def test_cancel_deletes_the_imported_copy(self, api_client, monkeypatch, tmp_path):
        imported = tmp_path / "imported_x.db"
        imported.touch()
        monkeypatch.setattr(db_import, "import_database", lambda src, dest_dir: imported)
        monkeypatch.setattr(db_import, "suggest_player_name", lambda path: "")
        start = api_client.post("/api/settings/db-import", json={"path": "/tmp/source.db"})
        pending_id = start.json()["pendingId"]

        resp = api_client.post("/api/settings/db-import/cancel", json={"pending_id": pending_id})
        assert resp.status_code == 200
        assert not imported.exists()


@pytest.mark.integration
class TestChesscomAccount:
    def test_status_when_not_connected(self, api_client):
        resp = api_client.get("/api/settings/chesscom")
        assert resp.status_code == 200
        assert resp.json() == {"username": None}

    def test_connect_saves_username(self, api_client):
        resp = api_client.post("/api/settings/chesscom", json={"username": "my_chesscom"})
        assert resp.status_code == 200
        assert resp.json() == {"username": "my_chesscom"}
        cfg = _config.load_config(path=str(_config.DEFAULT_CONFIG_PATH))
        assert cfg["player"]["chesscom_username"] == "my_chesscom"

    def test_disconnect_clears_username(self, api_client):
        api_client.post("/api/settings/chesscom", json={"username": "my_chesscom"})
        resp = api_client.delete("/api/settings/chesscom")
        assert resp.status_code == 200
        cfg = _config.load_config(path=str(_config.DEFAULT_CONFIG_PATH))
        assert cfg["player"].get("chesscom_username") is None

    def test_sync_without_connection_returns_400(self, api_client):
        resp = api_client.post("/api/settings/chesscom/sync")
        assert resp.status_code == 400

    def test_sync_unknown_username_returns_404(self, api_client, monkeypatch):
        api_client.post("/api/settings/chesscom", json={"username": "ghost_player"})

        def _raise(*args, **kwargs):
            raise ValueError("chess.com user 'ghost_player' not found")

        monkeypatch.setattr(sync_chesscom, "run", _raise)
        resp = api_client.post("/api/settings/chesscom/sync")
        assert resp.status_code == 404

    def test_sync_success(self, api_client, monkeypatch):
        api_client.post("/api/settings/chesscom", json={"username": "real_player"})
        captured = {}
        monkeypatch.setattr(
            sync_chesscom, "run",
            lambda *args, **kwargs: captured.setdefault("called", True),
        )
        resp = api_client.post("/api/settings/chesscom/sync")
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
        assert captured["called"] is True
