import pytest


@pytest.mark.integration
class TestEngineProfiles:
    def test_list_starts_empty(self, api_client):
        resp = api_client.get("/api/settings/engine-profiles")
        assert resp.status_code == 200
        assert resp.json() == {"profiles": []}

    def test_save_then_list(self, api_client):
        resp = api_client.post("/api/settings/engine-profiles", json={"name": "deep-analysis"})
        assert resp.status_code == 200
        assert resp.json() == {"profiles": ["deep-analysis"]}

    def test_save_rejects_blank_name(self, api_client):
        resp = api_client.post("/api/settings/engine-profiles", json={"name": "   "})
        assert resp.status_code == 400

    def test_apply_unknown_profile_returns_404(self, api_client):
        resp = api_client.post("/api/settings/engine-profiles/does-not-exist/apply")
        assert resp.status_code == 404

    def test_apply_known_profile_returns_engine_payload(self, api_client, monkeypatch):
        import worker
        monkeypatch.setattr(worker, "validate_engine_path", lambda path: "Stockfish 16")
        api_client.post("/api/settings/engine/path", json={"path": "/usr/games/stockfish"})
        api_client.post("/api/settings/engine-profiles", json={"name": "my-profile"})
        resp = api_client.post("/api/settings/engine-profiles/my-profile/apply")
        assert resp.status_code == 200
        assert "live" in resp.json()

    def test_delete_removes_profile(self, api_client):
        api_client.post("/api/settings/engine-profiles", json={"name": "temp"})
        resp = api_client.delete("/api/settings/engine-profiles/temp")
        assert resp.status_code == 200
        assert resp.json() == {"profiles": []}
