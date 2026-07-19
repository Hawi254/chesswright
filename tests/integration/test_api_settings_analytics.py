import pytest

import config as _config


@pytest.mark.integration
class TestAnalyticsSettings:
    def test_get_returns_current_values(self, api_client):
        resp = api_client.get("/api/settings/analytics")
        assert resp.status_code == 200
        body = resp.json()
        assert "utcOffsetHours" in body
        assert "minSampleSize" in body

    def test_post_saves_and_returns_updated_values(self, api_client):
        resp = api_client.post(
            "/api/settings/analytics",
            json={"utc_offset_hours": 5, "min_sample_size": 10},
        )
        assert resp.status_code == 200
        assert resp.json() == {"utcOffsetHours": 5, "minSampleSize": 10}

        cfg = _config.load_config(path=str(_config.DEFAULT_CONFIG_PATH))
        assert cfg["analytics"]["utc_offset_hours"] == 5
        assert cfg["analytics"]["min_sample_size"] == 10

    def test_post_rejects_out_of_bounds_utc_offset(self, api_client):
        resp = api_client.post(
            "/api/settings/analytics",
            json={"utc_offset_hours": 99, "min_sample_size": 10},
        )
        assert resp.status_code == 422

    def test_reset_restores_template_defaults(self, api_client):
        api_client.post(
            "/api/settings/analytics",
            json={"utc_offset_hours": 5, "min_sample_size": 10},
        )
        resp = api_client.post("/api/settings/analytics/reset")
        assert resp.status_code == 200
        cfg = _config.load_config(path=str(_config.DEFAULT_CONFIG_PATH))
        template_cfg = _config.load_config()
        assert cfg["analytics"]["utc_offset_hours"] == template_cfg["analytics"]["utc_offset_hours"]
        assert cfg["analytics"]["min_sample_size"] == template_cfg["analytics"]["min_sample_size"]
