import pytest

import api_key_store


@pytest.mark.integration
class TestApiKeySettings:
    def test_status_when_no_key_configured(self, api_client, monkeypatch):
        monkeypatch.setattr(api_key_store, "get_api_key", lambda: None)
        resp = api_client.get("/api/settings/api-key")
        assert resp.status_code == 200
        assert resp.json() == {"configured": False, "masked": None, "secureBackend": resp.json()["secureBackend"]}

    def test_status_masks_a_configured_key(self, api_client, monkeypatch):
        monkeypatch.setattr(api_key_store, "get_api_key", lambda: "sk-ant-abcdef1234567890")
        resp = api_client.get("/api/settings/api-key")
        assert resp.status_code == 200
        body = resp.json()
        assert body["configured"] is True
        assert body["masked"] == "sk-ant...7890"

    def test_save_rejects_blank_key(self, api_client):
        resp = api_client.post("/api/settings/api-key", json={"key": "   "})
        assert resp.status_code == 400

    def test_save_calls_set_api_key(self, api_client, monkeypatch):
        captured = {}

        def _fake_set_api_key(value):
            captured["value"] = value
            return True

        monkeypatch.setattr(api_key_store, "set_api_key", _fake_set_api_key)
        resp = api_client.post("/api/settings/api-key", json={"key": "sk-ant-newkey"})
        assert resp.status_code == 200
        assert resp.json() == {"ok": True, "securelyStored": True}
        assert captured["value"] == "sk-ant-newkey"

    def test_delete_calls_clear_api_key(self, api_client, monkeypatch):
        captured = {"called": False}
        monkeypatch.setattr(api_key_store, "clear_api_key", lambda: captured.__setitem__("called", True))
        resp = api_client.delete("/api/settings/api-key")
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
        assert captured["called"] is True
