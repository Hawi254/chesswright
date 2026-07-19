"""Integration tests for the Analysis Jobs page's FastAPI endpoints. See
docs/superpowers/specs/2026-07-15-analysis-jobs-page-design.md.
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

import job_runner
import joblock
import annotate
import backfill_batch_eval_cache


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


def _insert_run(conn, run_id, started_at="2026-07-08T00:00:00+00:00", ended_at=None):
    conn.execute(
        "INSERT INTO analysis_runs (id, started_at, ended_at) VALUES (?,?,?)",
        (run_id, started_at, ended_at))


def _insert_game(conn, game_id, analysis_status="pending"):
    conn.execute("""
        INSERT OR IGNORE INTO games (id, white, black, num_plies, last_analyzed_ply,
                                      analysis_status, queue_order)
        VALUES (?,?,?,?,?,?,?)
    """, (game_id, "W", "B", 1, 0, analysis_status, 0))


def _insert_move(conn, game_id, run_id, ply, eval_source, search_time_ms=None):
    _insert_game(conn, game_id)
    conn.execute("""
        INSERT INTO moves (game_id, ply, move_number, color, san, analysis_run_id,
                            eval_source, search_time_ms)
        VALUES (?,?,?,?,?,?,?,?)
    """, (game_id, ply, (ply + 1) // 2, "white" if ply % 2 else "black", "e4",
          run_id, eval_source, search_time_ms))


@pytest.mark.integration
class TestAnalysisJobStatus:
    def test_idle_shape_with_no_data(self, api_client, monkeypatch):
        monkeypatch.setattr(job_runner, "is_running", lambda: False)
        monkeypatch.setattr(job_runner, "get_state", lambda: {"status": "idle", "run_seq": 0})
        monkeypatch.setattr(joblock, "status", lambda: None)

        resp = api_client.get("/api/analysis-jobs/status")
        assert resp.status_code == 200
        assert resp.json() == {
            "status": "idle", "runSeq": 0, "completedRunId": None, "error": None,
            "run": None,
            "queue": {"waiting": 0, "analyzed": 0, "failed": 0, "awaitingAnnotation": 0},
            "telemetry": None, "lock": None,
            "maintenance": {"annotationPending": 0, "backfillPending": 0, "motifBackfillNeeded": False},
        }

    def test_queue_counts_reflect_real_games_rows(self, api_client, migrated_db, monkeypatch):
        monkeypatch.setattr(job_runner, "is_running", lambda: False)
        monkeypatch.setattr(job_runner, "get_state", lambda: {"status": "idle", "run_seq": 0})
        monkeypatch.setattr(joblock, "status", lambda: None)

        conn = migrated_db
        _insert_game(conn, "g1", "pending")
        _insert_game(conn, "g2", "in_progress")
        _insert_game(conn, "g3", "done")
        _insert_game(conn, "g4", "failed")
        conn.commit()

        resp = api_client.get("/api/analysis-jobs/status")
        assert resp.json()["queue"] == {
            "waiting": 2, "analyzed": 1, "failed": 1, "awaitingAnnotation": 0,
        }

    def test_running_shape_includes_run_and_telemetry(self, api_client, migrated_db, monkeypatch):
        conn = migrated_db
        _insert_run(conn, 7, started_at="2026-07-08T00:00:00+00:00")
        _insert_move(conn, "g1", 7, 1, "reuse")
        _insert_move(conn, "g1", 7, 2, "reuse")
        _insert_move(conn, "g1", 7, 3, "engine", search_time_ms=100)
        _insert_move(conn, "g1", 7, 4, "engine", search_time_ms=300)
        conn.commit()

        monkeypatch.setattr(job_runner, "is_running", lambda: True)
        monkeypatch.setattr(job_runner, "get_state",
                             lambda: {"status": "running", "games_done": 3, "run_seq": 5})
        monkeypatch.setattr(joblock, "status", lambda: None)

        resp = api_client.get("/api/analysis-jobs/status")
        body = resp.json()
        assert body["status"] == "running"
        assert body["run"] == {"gamesDone": 3, "runId": 7, "startedAt": "2026-07-08T00:00:00+00:00"}
        assert body["telemetry"]["reuseEvalsOn"] is True
        assert body["telemetry"]["cacheHitRate"] == pytest.approx(0.5)  # 2 reused / 4 eligible
        assert body["telemetry"]["estTimeSavedSec"] == pytest.approx(2 * 200 / 1000)  # reused * avg_engine_ms/1000
        assert body["telemetry"]["eta"] is None  # always computed client-side

    def test_running_with_no_active_run_row_yet_has_null_telemetry(self, api_client, monkeypatch):
        """Brief window right after job_runner.start() spawns the thread,
        before worker.run()'s own INSERT INTO analysis_runs has landed."""
        monkeypatch.setattr(job_runner, "is_running", lambda: True)
        monkeypatch.setattr(job_runner, "get_state",
                             lambda: {"status": "running", "games_done": 0, "run_seq": 1})
        monkeypatch.setattr(joblock, "status", lambda: None)

        resp = api_client.get("/api/analysis-jobs/status")
        body = resp.json()
        assert body["run"] == {"gamesDone": 0}
        assert body["telemetry"] is None

    def test_error_shape(self, api_client, monkeypatch):
        monkeypatch.setattr(job_runner, "is_running", lambda: False)
        monkeypatch.setattr(job_runner, "get_state",
                             lambda: {"status": "error", "error": "engine crashed", "run_seq": 2})
        monkeypatch.setattr(joblock, "status", lambda: None)

        resp = api_client.get("/api/analysis-jobs/status")
        body = resp.json()
        assert body["status"] == "error"
        assert body["error"] == "engine crashed"
        assert body["run"] is None

    def test_done_shape_reports_completed_run_id(self, api_client, monkeypatch):
        monkeypatch.setattr(job_runner, "is_running", lambda: False)
        monkeypatch.setattr(job_runner, "get_state",
                             lambda: {"status": "done", "completed_run_id": 42, "run_seq": 3})
        monkeypatch.setattr(joblock, "status", lambda: None)

        resp = api_client.get("/api/analysis-jobs/status")
        assert resp.json()["completedRunId"] == 42

    def test_lock_alive_is_reported_verbatim(self, api_client, monkeypatch):
        monkeypatch.setattr(job_runner, "is_running", lambda: False)
        monkeypatch.setattr(job_runner, "get_state", lambda: {"status": "idle", "run_seq": 0})
        monkeypatch.setattr(joblock, "status",
                             lambda: joblock.LockInfo(pid=12345, started_at="t0", alive=True))

        resp = api_client.get("/api/analysis-jobs/status")
        assert resp.json()["lock"] == {"pid": 12345, "started_at": "t0", "alive": True}

    def test_lock_stale_is_reported_verbatim(self, api_client, monkeypatch):
        monkeypatch.setattr(job_runner, "is_running", lambda: False)
        monkeypatch.setattr(job_runner, "get_state", lambda: {"status": "idle", "run_seq": 0})
        monkeypatch.setattr(joblock, "status",
                             lambda: joblock.LockInfo(pid=999, started_at="t0", alive=False))

        resp = api_client.get("/api/analysis-jobs/status")
        assert resp.json()["lock"] == {"pid": 999, "started_at": "t0", "alive": False}

    def test_maintenance_flags_reflect_business_logic_functions(self, api_client, monkeypatch):
        monkeypatch.setattr(job_runner, "is_running", lambda: False)
        monkeypatch.setattr(job_runner, "get_state", lambda: {"status": "idle", "run_seq": 0})
        monkeypatch.setattr(joblock, "status", lambda: None)
        monkeypatch.setattr(annotate, "count_games_awaiting_annotation", lambda conn: 5)
        monkeypatch.setattr(annotate, "motif_backfill_needed", lambda conn: True)
        monkeypatch.setattr(backfill_batch_eval_cache, "count_pending_groups", lambda conn: 7)

        resp = api_client.get("/api/analysis-jobs/status")
        body = resp.json()
        assert body["queue"]["awaitingAnnotation"] == 5
        assert body["maintenance"] == {
            "annotationPending": 5, "backfillPending": 7, "motifBackfillNeeded": True,
        }

    def test_reuse_evals_off_reports_cache_hit_rate_off(self, api_client, migrated_db, monkeypatch, tmp_path):
        import config as _config
        conn = migrated_db
        _insert_run(conn, 1, started_at="2026-07-08T00:00:00+00:00")
        _insert_move(conn, "g1", 1, 1, "engine", search_time_ms=100)
        conn.commit()

        monkeypatch.setattr(job_runner, "is_running", lambda: True)
        monkeypatch.setattr(job_runner, "get_state",
                             lambda: {"status": "running", "games_done": 1, "run_seq": 1})
        monkeypatch.setattr(joblock, "status", lambda: None)
        _config.set_engine_setting("reuse_evals", False)

        resp = api_client.get("/api/analysis-jobs/status")
        assert resp.json()["telemetry"]["reuseEvalsOn"] is False
        assert resp.json()["telemetry"]["cacheHitRate"] is None


@pytest.mark.integration
class TestStartStopLock:
    def test_start_success_calls_job_runner_with_config_values(self, api_client, monkeypatch):
        captured = {}
        def _fake_start(db_path, depth, multipv, threads, hash_mb, pv_max_len, engine_path,
                         max_games, max_duration_s, consecutive_failure_limit, commit_every_n_moves,
                         backlog_quota=0.0, backlog_quota_window=20):
            captured.update(db_path=db_path, depth=depth, multipv=multipv)
        monkeypatch.setattr(job_runner, "start", _fake_start)

        resp = api_client.post("/api/analysis-jobs/start")
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
        assert isinstance(captured["depth"], int)
        assert isinstance(captured["multipv"], int)

    def test_start_rejects_when_already_running_in_process(self, api_client, monkeypatch):
        def _raise(*a, **kw):
            raise RuntimeError("A batch is already running in this app.")
        monkeypatch.setattr(job_runner, "start", _raise)

        resp = api_client.post("/api/analysis-jobs/start")
        assert resp.status_code == 409
        assert resp.json()["detail"] == "A batch is already running in this app."

    def test_start_rejects_when_external_lock_held(self, api_client, monkeypatch):
        info = joblock.LockInfo(pid=555, started_at="t0", alive=True)
        def _raise(*a, **kw):
            raise joblock.LockHeldError(info)
        monkeypatch.setattr(job_runner, "start", _raise)

        resp = api_client.post("/api/analysis-jobs/start")
        assert resp.status_code == 409
        assert "555" in resp.json()["detail"]

    def test_stop_calls_job_runner_stop(self, api_client, monkeypatch):
        called = []
        monkeypatch.setattr(job_runner, "stop", lambda: called.append(True))

        resp = api_client.post("/api/analysis-jobs/stop")
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
        assert called == [True]

    def test_lock_clear_calls_joblock_force_release(self, api_client, monkeypatch):
        called = []
        monkeypatch.setattr(joblock, "force_release", lambda: called.append(True))

        resp = api_client.post("/api/analysis-jobs/lock/clear")
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
        assert called == [True]


@pytest.mark.integration
class TestSettings:
    def test_get_settings_reflects_config_values(self, api_client, tmp_path):
        import config as _config
        scratch_config = tmp_path / "config.yaml"
        _config.set_engine_setting("depth", 18, path=str(scratch_config))
        _config.set_engine_setting("multipv", 3, path=str(scratch_config))
        _config.set_engine_setting("threads", 4, path=str(scratch_config))
        _config.set_engine_setting("hash_mb", 256, path=str(scratch_config))
        _config.set_worker_setting("max_games", 50, path=str(scratch_config))
        _config.set_worker_setting("max_duration", "2h", path=str(scratch_config))
        # api_client's DEFAULT_CONFIG_PATH is already monkeypatched to a
        # different scratch file by the fixture -- write through that path
        # instead so GET reads back what this test wrote.
        import api.main as api_main
        real_path = _config.DEFAULT_CONFIG_PATH
        _config.set_engine_setting("depth", 18, path=str(real_path))
        _config.set_engine_setting("multipv", 3, path=str(real_path))
        _config.set_engine_setting("threads", 4, path=str(real_path))
        _config.set_engine_setting("hash_mb", 256, path=str(real_path))
        _config.set_worker_setting("max_games", 50, path=str(real_path))
        _config.set_worker_setting("max_duration", "2h", path=str(real_path))

        resp = api_client.get("/api/analysis-jobs/settings")
        assert resp.status_code == 200
        assert resp.json() == {
            "depth": 18, "multipv": 3, "threads": 4, "hashMb": 256,
            "maxGames": 50, "maxDuration": "2h",
        }

    def test_save_settings_persists_to_config(self, api_client):
        import config as _config
        resp = api_client.put("/api/analysis-jobs/settings", json={
            "depth": 20, "multipv": 4, "max_games": 100, "max_duration": "90m",
            "threads": 8, "hash_mb": 512,
        })
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

        cfg = _config.load_config(path=str(_config.DEFAULT_CONFIG_PATH))
        assert cfg["engine"]["depth"] == 20
        assert cfg["engine"]["multipv"] == 4
        assert cfg["engine"]["threads"] == 8
        assert cfg["engine"]["hash_mb"] == 512
        assert cfg["worker"]["max_games"] == 100
        assert cfg["worker"]["max_duration"] == "90m"

    def test_save_settings_accepts_null_max_games_and_duration(self, api_client):
        resp = api_client.put("/api/analysis-jobs/settings", json={
            "depth": 20, "multipv": 4, "max_games": None, "max_duration": None,
            "threads": 8, "hash_mb": 512,
        })
        assert resp.status_code == 200

    def test_save_settings_rejected_while_running(self, api_client, monkeypatch):
        monkeypatch.setattr(job_runner, "is_running", lambda: True)
        resp = api_client.put("/api/analysis-jobs/settings", json={
            "depth": 20, "multipv": 4, "max_games": None, "max_duration": None,
            "threads": 8, "hash_mb": 512,
        })
        assert resp.status_code == 409
        assert "read-only" in resp.json()["detail"]


@pytest.mark.integration
class TestAnnotateAndBackfill:
    def test_run_annotation_pass(self, api_client, monkeypatch):
        captured = {}
        def _fake_run(db_path, mate_cap, thresholds, brilliant_threshold, puzzle_cfg, streak_cfg, game_id):
            captured.update(db_path=db_path, game_id=game_id)
        monkeypatch.setattr(annotate, "run", _fake_run)

        resp = api_client.post("/api/analysis-jobs/annotate")
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
        assert captured["game_id"] is None  # whole-database pass, not one game

    def test_run_cache_backfill_reports_stats(self, api_client, monkeypatch):
        stats = backfill_batch_eval_cache.BackfillStats(candidates_seen=0, inserted=5, groups_seen=7, already_present=0)
        monkeypatch.setattr(backfill_batch_eval_cache, "backfill", lambda db_path: stats)

        resp = api_client.post("/api/analysis-jobs/backfill")
        assert resp.status_code == 200
        assert resp.json() == {"insertedCount": 5, "groupsSeen": 7}
