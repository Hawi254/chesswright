import pytest

import config as _config


@pytest.mark.integration
class TestIngestionSettings:
    def test_get_returns_current_values(self, api_client):
        resp = api_client.get("/api/settings/ingestion")
        assert resp.status_code == 200
        body = resp.json()
        assert "variantPolicy" in body
        assert "queueStrategy" in body

    def test_post_saves_and_returns_updated_values(self, api_client):
        resp = api_client.post(
            "/api/settings/ingestion",
            json={"variant_policy": "include", "queue_strategy": "chronological"},
        )
        assert resp.status_code == 200
        assert resp.json() == {"variantPolicy": "include", "queueStrategy": "chronological"}

        cfg = _config.load_config(path=str(_config.DEFAULT_CONFIG_PATH))
        assert cfg["ingestion"]["variant_policy"] == "include"
        assert cfg["ingestion"]["queue_strategy"] == "chronological"

    def test_post_rejects_unknown_variant_policy(self, api_client):
        resp = api_client.post(
            "/api/settings/ingestion",
            json={"variant_policy": "bogus", "queue_strategy": "chronological"},
        )
        assert resp.status_code == 400

    def test_reset_restores_template_defaults(self, api_client):
        api_client.post(
            "/api/settings/ingestion",
            json={"variant_policy": "include", "queue_strategy": "chronological"},
        )
        resp = api_client.post("/api/settings/ingestion/reset")
        assert resp.status_code == 200
        cfg = _config.load_config(path=str(_config.DEFAULT_CONFIG_PATH))
        template_cfg = _config.load_config()
        assert cfg["ingestion"]["variant_policy"] == template_cfg["ingestion"]["variant_policy"]
        assert cfg["ingestion"]["queue_strategy"] == template_cfg["ingestion"]["queue_strategy"]
