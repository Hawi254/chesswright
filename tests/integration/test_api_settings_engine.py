import pytest

import config as _config
import worker


@pytest.mark.integration
class TestEngineSettings:
    def test_get_returns_path_and_live_settings(self, api_client):
        resp = api_client.get("/api/settings/engine")
        assert resp.status_code == 200
        body = resp.json()
        assert "path" in body
        assert "detectedPath" in body
        assert set(body["live"].keys()) == {
            "timeSec", "depth", "threads", "hashMb", "storeThreshold", "useLichessCloudEval",
        }

    def test_set_path_rejects_invalid_engine(self, api_client, monkeypatch):
        def _raise(path):
            raise RuntimeError(f"'{path}' is not a valid UCI engine")

        monkeypatch.setattr(worker, "validate_engine_path", _raise)
        resp = api_client.post("/api/settings/engine/path", json={"path": "/not/an/engine"})
        assert resp.status_code == 400
        assert "not a valid UCI engine" in resp.json()["detail"]

    def test_set_path_saves_on_valid_engine(self, api_client, monkeypatch):
        monkeypatch.setattr(worker, "validate_engine_path", lambda path: "Stockfish 16")
        resp = api_client.post("/api/settings/engine/path", json={"path": "/usr/games/stockfish"})
        assert resp.status_code == 200
        assert resp.json()["path"] == "/usr/games/stockfish"
        cfg = _config.load_config(path=str(_config.DEFAULT_CONFIG_PATH))
        assert cfg["engine"]["path"] == "/usr/games/stockfish"

    def test_redetect_returns_404_when_nothing_found(self, api_client, monkeypatch):
        monkeypatch.setattr(worker, "find_engine_path", lambda explicit_path: None)
        resp = api_client.post("/api/settings/engine/redetect")
        assert resp.status_code == 404

    def test_redetect_saves_when_found(self, api_client, monkeypatch):
        monkeypatch.setattr(worker, "find_engine_path", lambda explicit_path: "/usr/games/stockfish")
        resp = api_client.post("/api/settings/engine/redetect")
        assert resp.status_code == 200
        assert resp.json()["path"] == "/usr/games/stockfish"

    def test_save_live_engine_settings(self, api_client):
        resp = api_client.post(
            "/api/settings/engine/live",
            json={
                "time_sec": 1.5, "depth": 25, "threads": 4, "hash_mb": 128,
                "store_threshold": 10, "use_lichess_cloud_eval": False,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["live"] == {
            "timeSec": 1.5, "depth": 25, "threads": 4, "hashMb": 128,
            "storeThreshold": 10, "useLichessCloudEval": False,
        }

    def test_save_live_engine_rejects_out_of_bounds(self, api_client):
        resp = api_client.post(
            "/api/settings/engine/live",
            json={
                "time_sec": 1.5, "depth": 999, "threads": 4, "hash_mb": 128,
                "store_threshold": 10, "use_lichess_cloud_eval": False,
            },
        )
        assert resp.status_code == 422

    def test_reset_clears_path_and_restores_live_defaults(self, api_client, monkeypatch):
        monkeypatch.setattr(worker, "validate_engine_path", lambda path: "Stockfish 16")
        api_client.post("/api/settings/engine/path", json={"path": "/usr/games/stockfish"})
        api_client.post(
            "/api/settings/engine/live",
            json={
                "time_sec": 5.0, "depth": 30, "threads": 8, "hash_mb": 512,
                "store_threshold": 40, "use_lichess_cloud_eval": False,
            },
        )
        resp = api_client.post("/api/settings/engine/reset")
        assert resp.status_code == 200
        assert resp.json()["path"] is None
        cfg = _config.load_config(path=str(_config.DEFAULT_CONFIG_PATH))
        template_cfg = _config.load_config()
        assert cfg["interactive_engine"] == template_cfg["interactive_engine"]
