import pytest

import config as _config


ADVANCED_BODY = {
    "pv_max_len": 30,
    "reuse_evals": False,
    "consecutive_failure_limit": 5,
    "commit_every_n_moves": 10,
    "berserk_max_clock_fraction": 0.6,
    "backlog_quota": 0.25,
    "backlog_quota_window": 50,
    "sync_request_timeout_seconds": 60,
    "sync_chesscom_request_timeout_seconds": 45,
}


@pytest.mark.integration
class TestAdvancedSettings:
    def test_get_returns_all_nine_fields(self, api_client):
        resp = api_client.get("/api/settings/advanced")
        assert resp.status_code == 200
        body = resp.json()
        for key in (
            "pvMaxLen", "reuseEvals", "consecutiveFailureLimit", "commitEveryNMoves",
            "berserkMaxClockFraction", "backlogQuota", "backlogQuotaWindow",
            "syncRequestTimeoutSeconds", "syncChesscomRequestTimeoutSeconds",
        ):
            assert key in body

    def test_post_saves_all_nine_fields(self, api_client):
        resp = api_client.post("/api/settings/advanced", json=ADVANCED_BODY)
        assert resp.status_code == 200
        assert resp.json() == {
            "pvMaxLen": 30, "reuseEvals": False, "consecutiveFailureLimit": 5,
            "commitEveryNMoves": 10, "berserkMaxClockFraction": 0.6, "backlogQuota": 0.25,
            "backlogQuotaWindow": 50, "syncRequestTimeoutSeconds": 60,
            "syncChesscomRequestTimeoutSeconds": 45,
        }
        cfg = _config.load_config(path=str(_config.DEFAULT_CONFIG_PATH))
        assert cfg["engine"]["pv_max_len"] == 30
        assert cfg["worker"]["commit_every_n_moves"] == 10
        assert cfg["ingestion"]["backlog_quota_window"] == 50
        assert cfg["sync_chesscom"]["request_timeout_seconds"] == 45

    def test_post_rejects_out_of_bounds_field(self, api_client):
        bad_body = dict(ADVANCED_BODY, backlog_quota_window=0)
        resp = api_client.post("/api/settings/advanced", json=bad_body)
        assert resp.status_code == 422
