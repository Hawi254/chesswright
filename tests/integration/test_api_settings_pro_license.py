import pytest

import api.routers.settings as settings_router


class _FakeProLicense:
    def __init__(self, key=None, info=None):
        self._key = key
        self._info = info
        self.deactivated = False

    def get_license_key(self):
        return self._key

    def get_license_info(self):
        return self._info

    def deactivate(self):
        self.deactivated = True

    def activate(self, key):
        if key == "valid-key":
            self._key = key
            return True, "License activated."
        return False, "Invalid license key."


@pytest.mark.integration
class TestProLicense:
    def test_status_when_pro_not_installed(self, api_client, monkeypatch):
        monkeypatch.setattr(settings_router, "pro_license", None)
        resp = api_client.get("/api/settings/pro-license")
        assert resp.status_code == 200
        assert resp.json() == {"available": False}

    def test_status_when_pro_installed_but_no_key(self, api_client, monkeypatch):
        monkeypatch.setattr(settings_router, "pro_license", _FakeProLicense())
        resp = api_client.get("/api/settings/pro-license")
        assert resp.status_code == 200
        body = resp.json()
        assert body == {"available": True, "configured": False, "masked": None, "purchaseEmail": None}

    def test_status_masks_a_configured_key(self, api_client, monkeypatch):
        fake = _FakeProLicense(key="cwpro-abcdefghij1234", info={"purchase_email": "buyer@example.com"})
        monkeypatch.setattr(settings_router, "pro_license", fake)
        resp = api_client.get("/api/settings/pro-license")
        body = resp.json()
        assert body["configured"] is True
        assert body["masked"] == "cwpro-ab...1234"
        assert body["purchaseEmail"] == "buyer@example.com"

    def test_activate_success(self, api_client, monkeypatch):
        monkeypatch.setattr(settings_router, "pro_license", _FakeProLicense())
        resp = api_client.post("/api/settings/pro/activate", json={"key": "valid-key"})
        assert resp.status_code == 200
        assert resp.json() == {"ok": True, "message": "License activated."}

    def test_activate_failure_returns_400(self, api_client, monkeypatch):
        monkeypatch.setattr(settings_router, "pro_license", _FakeProLicense())
        resp = api_client.post("/api/settings/pro/activate", json={"key": "wrong-key"})
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Invalid license key."

    def test_activate_when_not_installed_returns_404(self, api_client, monkeypatch):
        monkeypatch.setattr(settings_router, "pro_license", None)
        resp = api_client.post("/api/settings/pro/activate", json={"key": "x"})
        assert resp.status_code == 404

    def test_deactivate_success(self, api_client, monkeypatch):
        fake = _FakeProLicense(key="cwpro-abcdefghij1234")
        monkeypatch.setattr(settings_router, "pro_license", fake)
        resp = api_client.post("/api/settings/pro/deactivate")
        assert resp.status_code == 200
        assert fake.deactivated is True
