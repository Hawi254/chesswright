"""Integration tests for GET /api/batch-impact/summary -- see
docs/superpowers/specs/2026-07-16-batch-impact-page-design.md.
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


def _insert_run(db_path, run_id, games_analyzed=1):
    conn = sqlite3.connect(db_path)
    conn.execute("""
        INSERT INTO analysis_runs (id, started_at, ended_at, games_analyzed, plies_analyzed)
        VALUES (?, ?, ?, ?, ?)
    """, (run_id, f"2026-07-0{run_id}T10:00:00", f"2026-07-0{run_id}T10:05:00", games_analyzed, 10))
    conn.commit()
    conn.close()


def _insert_game(db_path, game_id):
    conn = sqlite3.connect(db_path)
    conn.execute("INSERT INTO games (id, white, black) VALUES (?, 'me', 'them')", (game_id,))
    conn.commit()
    conn.close()


def _insert_move(db_path, game_id, ply, cpl, classification, analysis_run_id, motif=None):
    conn = sqlite3.connect(db_path)
    conn.execute("""
        INSERT INTO moves (game_id, ply, move_number, color, san, is_player_move,
                            cpl, classification, analysis_run_id, motif)
        VALUES (?, ?, ?, 'w', 'e4', 1, ?, ?, ?, ?)
    """, (game_id, ply, (ply + 1) // 2, cpl, classification, analysis_run_id, motif))
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
class TestBatchImpactSummary:
    def test_empty_db_returns_empty_shape(self, api_client):
        resp = api_client.get("/api/batch-impact/summary")
        assert resp.status_code == 200
        body = resp.json()
        assert body["runs"] == []
        assert body["range"] == {"runA": None, "runB": None}
        assert body["headline"] is None
        assert body["pendingAnnotation"] is False
        assert body["records"] == []
        assert body["newBlunders"] == []

    def test_default_range_omits_params_and_picks_previous_run(self, api_client, migrated_db_path):
        _insert_run(migrated_db_path, 1)
        _insert_run(migrated_db_path, 2)
        _insert_game(migrated_db_path, "g1")
        _insert_move(migrated_db_path, "g1", 2, 20, "good", 1)
        _insert_move(migrated_db_path, "g1", 4, 30, "good", 2)
        resp = api_client.get("/api/batch-impact/summary")
        assert resp.status_code == 200
        assert resp.json()["range"] == {"runA": 1, "runB": 2}

    def test_default_range_with_single_run_falls_back_to_start(self, api_client, migrated_db_path):
        _insert_run(migrated_db_path, 1)
        resp = api_client.get("/api/batch-impact/summary")
        assert resp.json()["range"] == {"runA": None, "runB": 1}

    def test_explicit_start_sentinel(self, api_client, migrated_db_path):
        _insert_run(migrated_db_path, 1)
        _insert_run(migrated_db_path, 2)
        _insert_game(migrated_db_path, "g1")
        _insert_move(migrated_db_path, "g1", 2, 20, "good", 1)
        resp = api_client.get("/api/batch-impact/summary?run_a=start&run_b=1")
        assert resp.status_code == 200
        assert resp.json()["range"] == {"runA": None, "runB": 1}

    def test_reversed_params_get_swapped(self, api_client, migrated_db_path):
        _insert_run(migrated_db_path, 1)
        _insert_run(migrated_db_path, 2)
        resp = api_client.get("/api/batch-impact/summary?run_a=2&run_b=1")
        assert resp.status_code == 200
        assert resp.json()["range"] == {"runA": 1, "runB": 2}

    def test_unknown_run_b_returns_404(self, api_client, migrated_db_path):
        _insert_run(migrated_db_path, 1)
        resp = api_client.get("/api/batch-impact/summary?run_b=999")
        assert resp.status_code == 404

    def test_pending_annotation_when_run_b_not_yet_annotated(self, api_client, migrated_db_path):
        _insert_run(migrated_db_path, 1)
        _insert_run(migrated_db_path, 2)
        _insert_game(migrated_db_path, "g1")
        _insert_move(migrated_db_path, "g1", 2, 20, "good", 1)
        conn = sqlite3.connect(migrated_db_path)
        conn.execute("""
            INSERT INTO moves (game_id, ply, move_number, color, san, is_player_move,
                                cpl, classification, analysis_run_id)
            VALUES ('g1', 4, 2, 'w', 'e4', 1, NULL, NULL, 2)
        """)
        conn.commit()
        conn.close()
        resp = api_client.get("/api/batch-impact/summary?run_a=1&run_b=2")
        body = resp.json()
        assert body["pendingAnnotation"] is True
        assert body["headline"] is None

    def test_headline_and_new_blunders_shape(self, api_client, migrated_db_path):
        _insert_run(migrated_db_path, 1)
        _insert_run(migrated_db_path, 2)
        _insert_game(migrated_db_path, "g1")
        _insert_move(migrated_db_path, "g1", 2, 20, "good", 1)
        _insert_move(migrated_db_path, "g1", 4, 90, "blunder", 2, motif="fork")
        resp = api_client.get("/api/batch-impact/summary?run_a=1&run_b=2")
        body = resp.json()
        assert body["headline"]["acplBefore"] == pytest.approx(20.0)
        assert body["headline"]["acplAfter"] == pytest.approx(55.0)
        assert body["headline"]["newBlunders"] == 1
        assert body["headline"]["topMotif"] == "fork"
        assert body["newBlunders"] == [{"gameId": "g1", "ply": 4, "san": "e4", "cpl": 90, "motif": "fork"}]

    def test_records_in_range_finds_middle_run_but_not_the_trivial_first(self, api_client, migrated_db_path):
        """run1 is the first-ever annotated run in the whole account's
        history -- trivially "best" against nothing, so it must NOT be
        flagged even though it's inside a Start-anchored range (mirrors
        get_batch_record_flags's own "no trivial first record" principle).
        run2 genuinely improves on run1, so only run2 is a record; run3 is
        worse than run2, so it is not."""
        _insert_run(migrated_db_path, 1)
        _insert_run(migrated_db_path, 2)
        _insert_run(migrated_db_path, 3)
        _insert_game(migrated_db_path, "g1")
        _insert_move(migrated_db_path, "g1", 2, 50, "good", 1)   # ACPL 50
        _insert_move(migrated_db_path, "g1", 4, 10, "good", 2)   # ACPL 10 -- new record
        _insert_move(migrated_db_path, "g1", 6, 30, "good", 3)   # ACPL 30 -- not a record
        resp = api_client.get("/api/batch-impact/summary?run_a=start&run_b=3")
        body = resp.json()
        acpl_records = [r for r in body["records"] if r["metric"] == "acpl"]
        assert [r["runId"] for r in acpl_records] == [2]
        assert acpl_records[0]["priorBest"] == pytest.approx(50.0)

    def test_trend_is_unfiltered_by_the_selected_range(self, api_client, migrated_db_path):
        _insert_run(migrated_db_path, 1)
        _insert_run(migrated_db_path, 2)
        _insert_run(migrated_db_path, 3)
        _insert_game(migrated_db_path, "g1")
        _insert_move(migrated_db_path, "g1", 2, 20, "good", 1)
        _insert_move(migrated_db_path, "g1", 4, 20, "good", 2)
        _insert_move(migrated_db_path, "g1", 6, 20, "good", 3)
        resp = api_client.get("/api/batch-impact/summary?run_a=1&run_b=2")
        assert [r["runId"] for r in resp.json()["trend"]] == [1, 2, 3]
